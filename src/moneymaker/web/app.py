"""Local web UI (PRODUCT_SPEC §6) — FastAPI + HTMX over the proven engine.

Every number on screen comes from the same code paths the CLI uses; this
layer only shapes dicts for templates. Launch: `mm web`.
"""
import io
import os
import time

import numpy as np
import pandas as pd
from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import choice, opponents as opp, race as race_mod, store
from ..cli import _is_strong, _plans, _remaining
from ..ev import BUCKET_ORDER, BUCKETS, board as ev_board, bucket_probs
from ..payouts import ladder
from ..sequencer import solve as seq_solve
from ..simulate import strokes_final_round

HERE = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(HERE, "templates"))
templates.env.filters["money"] = lambda v: f"${v:,.0f}" if v is not None and \
    not (isinstance(v, float) and np.isnan(v)) else "—"
templates.env.filters["pct"] = lambda v: f"{100 * v:.1f}%"
templates.env.filters["pct0"] = lambda v: f"{100 * v:.0f}%"

_sim_cache: dict = {}
_model_cache: dict = {}


def create_app(db: str | None = None, season: int | None = None) -> FastAPI:
    app = FastAPI(title="Money Maker Engine")
    app.state.db = db
    app.state.season = season
    app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")),
              name="static")

    def _conn():
        return store.connect(app.state.db)

    def _fingerprint(conn, season):
        """Cheap cache key that changes on any ingest."""
        n_picks = conn.execute("SELECT COUNT(*) FROM picks WHERE season=?",
                               (season,)).fetchone()[0]
        last_pull = conn.execute("SELECT MAX(pulled_at) FROM predictions"
                                 ).fetchone()[0]
        return (app.state.db, season, n_picks, last_pull)

    def _get_profiles(conn, season):
        key = ("profiles", *_fingerprint(conn, season))
        if key not in _model_cache:
            _model_cache[key] = opp.mine_profiles(conn, season)
        return _model_cache[key]

    def _get_beta(conn, season):
        """Fitted choice-model beta (falls back to the documented prior).
        Fitting walks the whole season — cache until the next ingest."""
        key = ("beta", *_fingerprint(conn, season))
        if key not in _model_cache:
            beta = choice.fit_from_store(conn, season,
                                         _get_profiles(conn, season))
            _model_cache[key] = beta if beta is not None else \
                choice.DEFAULT_BETA
        return _model_cache[key]

    def _season(conn):
        if app.state.season:
            return int(app.state.season)
        row = conn.execute("SELECT MAX(season) FROM events").fetchone()
        import datetime
        return int(row[0]) if row and row[0] else datetime.date.today().year

    def _base_ctx(request, conn, season, page):
        events = store.events_df(conn, season)
        with_preds = set(store.events_with_preds(conn, season))
        return {
            "request": request, "page": page, "season": season,
            "self_name": store.self_manager(conn),
            "onboarded": len(events) > 0,
            "events": events.to_dict("records"),
            "pred_events": [e for e in events.to_dict("records")
                            if e["event_id"] in with_preds],
        }

    def _purse(erow) -> float:
        p = erow["purse"]
        return float(p) if p is not None and not pd.isna(p) and p > 0 else 1e7

    # ------------------------------------------------------------ dashboard
    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, board: str = "overall"):
        conn = _conn()
        season = _season(conn)
        ctx = _base_ctx(request, conn, season, "dashboard")
        standings = store.latest_standings(conn, season, board)
        self_name = ctx["self_name"]
        paid = opp.OVERALL_PAID if board == "overall" else opp.SEGMENT_PAID
        rows, self_rank = [], None
        totals = list(standings.items())
        for i, (m, v) in enumerate(totals):
            if m == self_name:
                self_rank = i + 1
            rows.append({"rank": i + 1, "manager": m, "total": v,
                         "is_self": m == self_name, "paid": i < paid})
        gap_money = opp.money_gap(standings, self_name, paid) \
            if self_name else None
        remaining = _remaining(conn, season)
        seg_left = None
        pot_left = 0.0
        try:
            min_seq = min((r["seq"] for r in remaining), default=None)
            if min_seq is not None:
                pot_left = opp.purse_left(conn, season, int(min_seq))
        except Exception:
            pass
        ctx.update({
            "board": board,
            "boards": ["overall"] + [f"segment{i}" for i in range(1, 5)],
            "standings": rows, "self_rank": self_rank,
            "gap_money": gap_money, "paid": paid,
            "remaining": [dict(r) for r in remaining],
            "pot_left": pot_left, "n_managers": len(rows),
        })
        return templates.TemplateResponse(request, "dashboard.html", ctx)

    # ----------------------------------------------------------- pick screen
    @app.get("/pick", response_class=HTMLResponse)
    def pick(request: Request, event: str = None, posture: str = "neutral"):
        conn = _conn()
        season = _season(conn)
        ctx = _base_ctx(request, conn, season, "pick")
        ctx.update({"board_rows": [], "event_row": None, "posture": posture,
                    "rivals": [], "pulled_at": None})
        if not ctx["pred_events"]:
            return templates.TemplateResponse(request, "pick.html", ctx)
        target = event or ctx["pred_events"][-1]["name"]
        erow = store.resolve_event(conn, season, target)
        preds = store.latest_preds(conn, erow["event_id"])
        self_name = ctx["self_name"]
        used = store.used_set(conn, season, self_name) if self_name else set()
        inel = store.ineligible_keys(conn, erow, preds)
        b = ev_board(preds, _purse(erow), used, has_cut=bool(erow["has_cut"]),
                     ineligible=set(inel), posture=posture)
        ctx.update({
            "event_row": dict(erow), "purse": _purse(erow),
            "pulled_at": preds.attrs.get("pulled_at"),
            "used_count": len(used), "inel_count": len(inel),
            "board_rows": b.head(25).to_dict("records"),
        })
        # rival read: nearest rivals by overall standing + their likely picks
        try:
            standings = store.latest_standings(conn, season, "overall")
            beta = _get_beta(conn, season)
            dists = opp.pick_distributions(conn, season, erow, preds, beta,
                                           _get_profiles(conn, season))
            locked = store.event_picks(conn, season, erow["event_id"])
            disp = dict(zip(preds["key"], preds["display_name"]))
            order = [m for m in standings if m != self_name]
            if self_name in standings:
                si = list(standings).index(self_name)
                order.sort(key=lambda m: abs(list(standings).index(m) - si))
            rivals = []
            for m in order[:10]:
                if locked.get(m):
                    rivals.append({"manager": m, "locked": True,
                                   "picks": [(disp.get(k, k), None)
                                             for k in locked[m]]})
                elif m in dists:
                    lineups, probs = dists[m]
                    rivals.append({"manager": m, "locked": False,
                                   "picks": [(disp.get(lu[0], lu[0]), p)
                                             for lu, p in
                                             list(zip(lineups, probs))[:3]]})
            ctx["rivals"] = rivals
        except Exception:
            pass
        return templates.TemplateResponse(request, "pick.html", ctx)

    @app.get("/pick/why", response_class=HTMLResponse)
    def pick_why(request: Request, event: str, key: str):
        conn = _conn()
        season = _season(conn)
        erow = store.resolve_event(conn, season, event)
        preds = store.latest_preds(conn, erow["event_id"])
        row = preds[preds["key"] == key].iloc[0]
        purse = _purse(erow)
        p = bucket_probs(row["win"], row["top_5"], row["top_10"],
                         row["top_20"], row["make_cut"],
                         bool(erow["has_cut"]))
        mids = [(BUCKETS[bk][0] + BUCKETS[bk][1]) / 2 * purse
                for bk in BUCKET_ORDER]
        labels = {"W": "Win", "2": "Solo 2nd", "35": "3rd–5th",
                  "610": "6th–10th", "1120": "11th–20th",
                  "2140": "21st–40th", "41C": "41st–cut", "MC": "Missed cut"}
        buckets = [{"label": labels[bk], "p": float(pp), "pay": mid,
                    "ev": float(pp) * mid}
                   for bk, pp, mid in zip(BUCKET_ORDER, p, mids)]
        maxp = max((x["p"] for x in buckets), default=1.0)
        return templates.TemplateResponse(request, "partials/why.html", {
            "request": request, "row": row.to_dict(), "event": erow["name"],
            "buckets": buckets, "maxp": maxp,
            "total_ev": sum(x["ev"] for x in buckets)})

    # ------------------------------------------------------------- race odds
    @app.get("/race", response_class=HTMLResponse)
    def race(request: Request, board: str = "overall"):
        conn = _conn()
        season = _season(conn)
        ctx = _base_ctx(request, conn, season, "race")
        ctx.update({"board": board,
                    "boards": ["overall"] + [f"segment{i}" for i in range(1, 5)]})
        return templates.TemplateResponse(request, "race.html", ctx)

    @app.post("/race/run", response_class=HTMLResponse)
    def race_run(request: Request, board: str = Form("overall"),
                 n: int = Form(20000), sensitivity: bool = Form(False),
                 point: bool = Form(False)):
        conn = _conn()
        season = _season(conn)
        self_name = store.self_manager(conn)
        if not self_name:
            return HTMLResponse("<p class='empty'>Set your manager first: "
                                "<code>mm set-self NAME</code></p>")
        segment = int(board[-1]) if board.startswith("segment") else None
        standings = store.latest_standings(conn, season, board) or \
            {m: 0.0 for m in store.managers_list(conn)}
        rows = _remaining(conn, season, segment)
        if not rows:
            return HTMLResponse("<p class='empty'>No remaining events with "
                                "predictions on this board.</p>")
        n = max(2000, min(int(n), 300_000))
        key = (app.state.db, season, board, n, sensitivity, point,
               max(r["event_id"] for r in rows))
        if key in _sim_cache and time.time() - _sim_cache[key][0] < 600:
            return HTMLResponse(_sim_cache[key][1])
        if point:
            beta, note = None, "rival picks: point projections"
        else:
            beta = _get_beta(conn, season)
            note = "rival picks: sampled from the fitted choice model"
        profiles = _get_profiles(conn, season)
        plans, plan_probs, curves, purses, cuts = _plans(
            conn, season, rows, profiles, beta, self_name)
        res = race_mod.simulate_race(standings, plans, curves, purses, cuts,
                                     self_name, n=n,
                                     plan_probs=plan_probs or None)
        dist = [{"k": k, "p": v} for k, v in res["dist"].items() if v > 0.002]
        maxp = max((d["p"] for d in dist), default=1.0)
        threats = []
        for m, p in sorted(res["passes"].items(), key=lambda kv: -kv[1])[:15]:
            threats.append({"manager": m, "p": p,
                            "gap": standings.get(m, 0)
                            - standings.get(self_name, 0),
                            "ev": res["ev_added"].get(m, 0)})
        band = None
        if sensitivity:
            kr = threats[0]["manager"] if threats else None
            b = race_mod.sensitivity_band(
                standings, plans, curves, purses, cuts, self_name,
                metric="p_first" if board == "overall" else "p_top3",
                key_rival=kr, plan_probs=plan_probs or None)
            lo, hi = b.pop("band")
            band = {"lo": lo, "hi": hi, "rival": kr,
                    "rows": list(b.items())}
        html = templates.TemplateResponse(request, "partials/race_result.html", {
            "request": request, "res": res, "dist": dist, "maxp": maxp,
            "threats": threats, "note": note, "events": [r["name"] for r in rows],
            "n": n, "band": band, "board": board,
        }).body.decode()
        _sim_cache[key] = (time.time(), html)
        return HTMLResponse(html)

    # ------------------------------------------------------------ season map
    @app.get("/season", response_class=HTMLResponse)
    def season_map(request: Request):
        conn = _conn()
        season = _season(conn)
        ctx = _base_ctx(request, conn, season, "season")
        self_name = ctx["self_name"]
        picks = store.picks_df(conn, season)
        mine = picks[picks["manager"] == self_name] if self_name else picks[:0]
        by_event = {int(e): g for e, g in mine.groupby("event_id")}
        with_preds = set(store.events_with_preds(conn, season))
        rows = []
        for e in ctx["events"]:
            g = by_event.get(e["event_id"])
            pick_txt = ", ".join(g["display_name"]) if g is not None else None
            earned = float(g["earnings"].sum()) if g is not None and \
                g["earnings"].notna().any() else None
            status = ("settled" if earned is not None else
                      "locked" if pick_txt else
                      "ready" if e["event_id"] in with_preds else "upcoming")
            rows.append({**e, "pick": pick_txt, "earned": earned,
                         "status": status,
                         "strong": _is_strong(e)})
        ctx["schedule"] = rows
        return templates.TemplateResponse(request, "season.html", ctx)

    @app.post("/season/plan", response_class=HTMLResponse)
    def season_plan(request: Request, posture: str = Form("neutral"),
                    reserve: str = Form(""), top_k: int = Form(8)):
        conn = _conn()
        season = _season(conn)
        self_name = store.self_manager(conn)
        rows = _remaining(conn, season)
        if not self_name or not rows:
            return HTMLResponse("<p class='empty'>Need a self manager and "
                                "remaining events with predictions.</p>")
        used = store.used_set(conn, season, self_name)
        reserved = {store.norm(r.strip()) for r in reserve.split(",")
                    if r.strip()}
        boards, labels = {}, {}
        for erow in rows:
            locked = store.event_picks(conn, season, erow["event_id"]).get(
                self_name, [])
            slots = int(erow["picks_per_manager"] or 1)
            if len(locked) >= slots:
                continue
            preds = store.latest_preds(conn, erow["event_id"])
            inel = store.ineligible_keys(conn, erow, preds)
            b = ev_board(preds, _purse(erow), used,
                         has_cut=bool(erow["has_cut"]), reserved=reserved,
                         ineligible=set(inel), posture=posture)
            if not _is_strong(erow):
                b = b[~b["reserved"]]
            pool = list(zip(b["score"].head(top_k), b["key"].head(top_k)))
            disp = dict(zip(b["key"], b["display_name"]))
            for s in range(slots - len(locked)):
                label = erow["name"] if slots == 1 else \
                    f"{erow['name']} (slot {len(locked) + s + 1})"
                boards[label] = pool
                labels[label] = disp
        best = seq_solve(boards, top_k=top_k)
        if not best:
            return HTMLResponse("<p class='empty'>No feasible assignment — "
                                "widen top-k.</p>")
        tot, asg = best
        out = [{"slot": lab, "golfer": labels[lab].get(asg[lab], asg[lab]),
                "ev": dict((k, v) for v, k in boards[lab]).get(asg[lab], 0.0)}
               for lab in boards]
        return templates.TemplateResponse(request, "partials/season_plan.html", {
            "request": request, "plan": out, "total": tot,
            "posture": posture})

    # ------------------------------------------------------------ sunday card
    @app.get("/sunday", response_class=HTMLResponse)
    def sunday(request: Request):
        conn = _conn()
        season = _season(conn)
        ctx = _base_ctx(request, conn, season, "sunday")
        return templates.TemplateResponse(request, "sunday.html", ctx)

    @app.post("/sunday/run", response_class=HTMLResponse)
    async def sunday_run(request: Request, event: str = Form(...),
                         source: str = Form("live"),
                         positions: UploadFile | None = None,
                         n: int = Form(50000)):
        conn = _conn()
        season = _season(conn)
        self_name = store.self_manager(conn)
        erow = store.resolve_event(conn, season, event)
        preds = store.latest_preds(conn, erow["event_id"])
        purse = _purse(erow)
        if source == "live":
            from ..datagolf import DataGolfAPI
            try:
                ls = DataGolfAPI().live_stats()
            except RuntimeError as e:
                return HTMLResponse(f"<p class='empty'>{e}</p>")
            ls["to_par"] = pd.to_numeric(ls["total"], errors="coerce")
            alive = ~ls["position"].astype(str).str.upper().isin(
                ("CUT", "WD", "DQ", "DNS"))
            pos_df = ls.loc[alive & ls["to_par"].notna(),
                            ["player_name", "to_par"]]
        else:
            raw = await positions.read()
            pos_df = pd.read_csv(io.BytesIO(raw))
        winp = dict(zip(preds["key"], preds["win"]))
        floor_wp = max(min(winp.values(), default=1e-3) * 0.5, 1e-4)
        pos54, wp = {}, {}
        for _, r in pos_df.iterrows():
            k = store.norm(r["player_name"])
            pos54[k] = int(r["to_par"])
            wp[k] = float(winp.get(k, floor_wp))
        n = max(5000, min(int(n), 300_000))
        pay, tot, players = strokes_final_round(pos54, wp, purse, n=n)
        amateurs = set(preds.loc[preds["amateur"].astype(bool), "key"]) \
            if "amateur" in preds.columns else set()
        for k in amateurs & set(pay):
            pay[k] = np.zeros(n)
        standings = store.latest_standings(conn, season, "overall") or \
            {m: 0.0 for m in store.managers_list(conn)}
        picks = store.event_picks(conn, season, erow["event_id"])
        zero = np.zeros(n)
        totals = {m: np.full(n, float(v)) for m, v in standings.items()}
        for m in totals:
            for k in picks.get(m, []):
                totals[m] = totals[m] + pay.get(k, zero)
        if self_name not in totals:
            return HTMLResponse("<p class='empty'>Self manager missing from "
                                "standings.</p>")
        st = totals[self_name]
        ahead = np.zeros(n, np.int32)
        passes = {}
        for m, t in totals.items():
            if m == self_name:
                continue
            beat = t > st
            passes[m] = float(beat.mean())
            ahead += beat.astype(np.int32)
        finish = ahead + 1
        dist = [{"k": k, "p": float((finish == k).mean())}
                for k in range(1, len(standings) + 1)]
        dist = [d for d in dist if d["p"] > 0.004]
        maxp = max((d["p"] for d in dist), default=1.0)
        lad = ladder(purse, len(players))
        self_start = float(standings.get(self_name, 0.0))
        thresholds = []
        for m, start in sorted(standings.items(), key=lambda kv: -kv[1]):
            if m == self_name or start <= self_start:
                continue
            gap = start - self_start
            covers = np.where(lad > gap)[0]
            thresholds.append({
                "manager": m, "gap": gap,
                "needs": (f"solo-{covers.max() + 1}" if len(covers)
                          else "out of ladder range"),
                "pays": float(lad[covers.max()]) if len(covers) else None,
                "p_pass": float((st > totals[m]).mean())})
        am_notes = [(m, k) for m, ks in picks.items() for k in ks
                    if k in amateurs]
        disp = dict(zip(preds["key"], preds["display_name"]))
        mine = [disp.get(k, k) for k in picks.get(self_name, [])]
        return templates.TemplateResponse(request, "partials/sunday_card.html", {
            "request": request, "event": erow["name"], "mine": mine,
            "dist": dist, "maxp": maxp, "thresholds": thresholds,
            "amateurs": [(m, disp.get(k, k)) for m, k in am_notes],
            "n_players": len(players)})

    # --------------------------------------------------------------- history
    @app.get("/history", response_class=HTMLResponse)
    def history(request: Request):
        conn = _conn()
        season = _season(conn)
        ctx = _base_ctx(request, conn, season, "history")
        journal = store.journal_df(conn, season)
        ctx["journal"] = journal.to_dict("records") if len(journal) else []
        picks = store.picks_df(conn, season)
        self_name = ctx["self_name"]
        mine = picks[picks["manager"] == self_name] if self_name else picks[:0]
        ctx["my_picks"] = mine.to_dict("records")
        ctx["my_total"] = float(mine["earnings"].dropna().sum()) \
            if len(mine) else 0.0
        try:
            profs = _get_profiles(conn, season)
            ctx["profiles"] = sorted(
                (vars(p) for p in profs.values()),
                key=lambda p: -p["mirror_rate"])
        except Exception:
            ctx["profiles"] = []
        return templates.TemplateResponse(request, "history.html", ctx)

    return app


app = create_app()
