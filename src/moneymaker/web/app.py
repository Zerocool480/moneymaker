"""Money Maker Engine web UI v3 — "SUNDAY BROADCAST" (docs/DESIGN_SPEC.md).

Three primitives everywhere: the tower (GAP/INT leaderboards), the
lower-third (the gold Money Line macro), the score bug (persistent ticker).
Every number comes from the same engine paths the CLI uses; this layer
shapes context dicts and chart geometry for the Jinja templates.
"""
import datetime
import io
import os
import time

import numpy as np
import pandas as pd
from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import choice, opponents as opp, race as race_mod, store
from ..cli import _is_strong, _plans, _remaining
from ..ev import BUCKET_ORDER, BUCKETS, board as ev_board, bucket_probs
from ..names import _PURSE_SUFFIX
from ..payouts import ladder
from ..sequencer import solve as seq_solve
from ..simulate import strokes_final_round

HERE = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(HERE, "templates"))

PRIZES_OVERALL = [4000, 2200, 1500, 1000, 700, 400]
PRIZES_SEGMENT = [750, 400, 250]
MINUS = "−"


def _money(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    v = float(v)
    sign = MINUS if v < 0 else ""
    return f"{sign}${abs(v):,.0f}"


def _money_signed(v):
    if v is None:
        return "—"
    return ("+" if v >= 0 else MINUS) + f"${abs(float(v)):,.0f}"


def _money_short(v):
    if v is None:
        return "—"
    v = float(v)
    a = abs(v)
    s = MINUS if v < 0 else ""
    if a >= 1e6:
        return f"{s}${a / 1e6:.2f}M".replace(".00M", "M")
    if a >= 1e3:
        return f"{s}${a / 1e3:.0f}k"
    return f"{s}${a:,.0f}"


def _money_od(v):
    """Odometer: leading magnitude group dimmed. Heroes/tiles only.
    Accepts a number or an already-formatted money string."""
    s = v if isinstance(v, str) else _money(v)
    if "," not in s:
        return f'<span class="od">{s}</span>'
    head, tail = s.split(",", 1)
    return (f'<span class="od"><span class="od-dim">{head},</span>'
            f'{tail}</span>')


def _p_label(p, decimals=1):
    """Sub-resolution ladder: <0.1% and structural zero read honestly."""
    if p is None:
        return "—"
    p = float(p)
    if p == 0:
        return "— no path"
    if p < 0.001:
        return "<0.1%"
    return f"{100 * p:.{decimals}f}%"


def _ev_name(name):
    return _PURSE_SUFFIX.sub("", str(name)).strip()


templates.env.filters.update({
    "money": _money, "money_signed": _money_signed, "money_short": _money_short,
    "money_od": _money_od, "p_label": _p_label, "ev_name": _ev_name,
    "pct": lambda v: f"{100 * float(v):.1f}%",
    "pct0": lambda v: f"{100 * float(v):.0f}%",
})

_model_cache: dict = {}
_sim_cache: dict = {}


def _path(xs, ys):
    """SVG path string from parallel coordinate lists."""
    if len(xs) == 0:
        return ""
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))


def create_app(db: str | None = None, season: int | None = None) -> FastAPI:
    app = FastAPI(title="Money Maker Engine")
    app.state.db = db
    app.state.season = season
    app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")),
              name="static")

    def _conn():
        return store.connect(app.state.db)

    def _season(conn):
        if app.state.season:
            return int(app.state.season)
        row = conn.execute("SELECT MAX(season) FROM events").fetchone()
        return int(row[0]) if row and row[0] else datetime.date.today().year

    def _fingerprint(conn, season):
        n_picks = conn.execute("SELECT COUNT(*) FROM picks WHERE season=?",
                               (season,)).fetchone()[0]
        last_pull = conn.execute("SELECT MAX(pulled_at) FROM predictions"
                                 ).fetchone()[0]
        return (app.state.db, season, n_picks, last_pull)

    def _cached(conn, season, key, fn):
        k = (key, *_fingerprint(conn, season))
        if k not in _model_cache:
            _model_cache[k] = fn()
        return _model_cache[k]

    def _get_profiles(conn, season):
        return _cached(conn, season, "profiles",
                       lambda: opp.mine_profiles(conn, season))

    def _get_beta(conn, season):
        def fit():
            b = choice.fit_from_store(conn, season, _get_profiles(conn, season))
            return b if b is not None else choice.DEFAULT_BETA
        return _cached(conn, season, "beta", fit)

    def _purse(erow) -> float:
        p = erow["purse"]
        return float(p) if p is not None and not pd.isna(p) and p > 0 else 1e7

    # ------------------------------------------------------ league state
    def _league(conn, season):
        """Cumulative $ by event seq for every manager + weekly ranks."""
        def build():
            picks = store.picks_df(conn, season)
            settled = picks.dropna(subset=["earnings"])
            if settled.empty:
                return {"cum": None, "picks": picks}
            per = settled.groupby(["seq", "manager"])["earnings"].sum() \
                .unstack(fill_value=0.0)
            cum = per.sort_index().cumsum()
            ranks = cum.rank(axis=1, ascending=False, method="min")
            return {"cum": cum, "ranks": ranks, "picks": picks}
        return _cached(conn, season, "league", build)

    def _last_sim(season, board):
        return _sim_cache.get(("last", app.state.db, season, board))

    def _base_ctx(request, conn, season, page):
        events = store.events_df(conn, season)
        with_preds = set(store.events_with_preds(conn, season))
        self_name = store.self_manager(conn)
        ctx = {
            "request": request, "page": page, "season": season,
            "self_name": self_name, "onboarded": len(events) > 0,
            "events": events.to_dict("records"),
            "pred_events": [e for e in events.to_dict("records")
                            if e["event_id"] in with_preds],
        }
        # ---- the score bug (ticker): always renderable, never blocking
        ticker = None
        try:
            overall = store.latest_standings(conn, season, "overall")
            if self_name and overall and self_name in overall:
                names = list(overall)
                rank = names.index(self_name) + 1
                cushion = opp.money_cushion(overall, self_name,
                                            opp.OVERALL_PAID)
                seg_txt = None
                cur_seg = None
                remaining = _remaining(conn, season)
                nxt = remaining[0] if remaining else None
                if nxt is not None:
                    cur_seg = nxt["segment"]
                if cur_seg:
                    seg = store.latest_standings(conn, season,
                                                 f"segment{cur_seg}")
                    if seg and self_name in seg:
                        seg_txt = (cur_seg, list(seg).index(self_name) + 1)
                sim = _last_sim(season, "overall")
                ticker = {
                    "rank": rank, "n": len(names), "cushion": cushion,
                    "seg": seg_txt,
                    "next_event": _ev_name(nxt["name"]) if nxt is not None
                    else None,
                    "p_money": sim.get("p_money") if sim else None,
                    "p_money_w": sim.get("p_money_w") if sim else None,
                }
        except Exception:
            ticker = None
        ctx["ticker"] = ticker
        return ctx

    # ---------------------------------------------------------- dashboard
    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, board: str = "overall"):
        conn = _conn()
        season = _season(conn)
        ctx = _base_ctx(request, conn, season, "dashboard")
        self_name = ctx["self_name"]
        standings = store.latest_standings(conn, season, board)
        paid = opp.OVERALL_PAID if board == "overall" else opp.SEGMENT_PAID
        prizes = PRIZES_OVERALL if board == "overall" else PRIZES_SEGMENT
        lg = _league(conn, season)

        ranked = list(standings.items())
        totals = [v for _, v in ranked]
        # ONE line, ONE meaning: the reference is the first UNPAID seat —
        # the hero cushion, the GAP column, and the strip all anchor to it.
        has_line = len(totals) > paid
        line_total = totals[paid] if has_line else None

        # weekly deltas
        deltas = {}
        if lg["cum"] is not None and len(lg["cum"]) >= 2 and board == "overall":
            prev, last = lg["ranks"].iloc[-2], lg["ranks"].iloc[-1]
            for m in standings:
                if m in prev and m in last:
                    deltas[m] = int(prev[m] - last[m])

        rows, self_rank = [], None
        prev_total = None
        for i, (m, v) in enumerate(ranked):
            if m == self_name:
                self_rank = i + 1
            gap_line = (v - line_total) if line_total is not None else None
            rows.append({
                "rank": i + 1, "manager": m, "total": v,
                "delta": deltas.get(m),
                "gap_line": gap_line,
                "intv": (prev_total - v) if prev_total is not None else None,
                "ladder_pct": max(-1.0, min(1.0, gap_line / 2e6))
                if gap_line is not None else 0.0,
                "is_self": m == self_name, "paid": i < paid,
                "prize": prizes[i] if i < len(prizes) else None,
            })
            prev_total = v

        cushion = opp.money_cushion(standings, self_name, paid) \
            if self_name and standings else None
        # named rank-gap up (to the seat above)
        up_gap = None
        if self_rank and self_rank > 1:
            um, uv = ranked[self_rank - 2]
            up_gap = (standings[self_name] - uv, self_rank - 1, um)

        # money strip geometry (full-bleed: positions in %, text in HTML)
        strip = None
        if len(totals) >= 8 and self_name in standings:
            lo = np.percentile(totals, 8)
            hi = max(totals)
            span = (hi - lo) or 1.0
            xp = lambda v: max(0.0, min(100.0, 100 * (v - lo) / span))
            strip = {
                "ticks": [{"x": xp(v), "cls": ("you" if m == self_name else
                                               "paid" if i < paid else "field"),
                           "mgr": m, "rank": i + 1, "total": v,
                           "gap": (v - line_total) if line_total else None}
                          for i, (m, v) in enumerate(ranked)],
                "line_x": xp(line_total) if line_total else None,
                "you_x": xp(standings[self_name]),
                "lo": lo, "hi": hi,
            }

        # rail: cumulative sparkline + rank trajectory
        spark = None
        if lg["cum"] is not None and self_name in lg["cum"].columns:
            cum = lg["cum"]
            xs = np.linspace(0, 100, len(cum))
            top = float(cum.max().max()) or 1.0
            yp = lambda v: 104 - 96 * (v / top)
            sixth = cum.apply(lambda r: r.nlargest(min(paid, len(r))).iloc[-1],
                              axis=1)
            r = lg["ranks"][self_name]
            ryp = lambda v: 6 + 58 * (min(v, 12) - 1) / 11
            spark = {
                "self_d": _path(xs, [yp(v) for v in cum[self_name]]),
                "line_d": _path(xs, [yp(v) for v in sixth]),
                "end_total": float(cum[self_name].iloc[-1]),
                "rank_d": _path(xs, [ryp(v) for v in r]),
                "band_top": ryp(1), "band_bot": ryp(min(paid, 12)),
                "end_rank": int(r.iloc[-1]),
                "weeks": len(cum),
            }

        # segment mini-tower
        seg_rows, seg_no = [], None
        remaining = _remaining(conn, season)
        nxt = remaining[0] if remaining else None
        if nxt is not None and nxt["segment"]:
            seg_no = int(nxt["segment"])
            seg = store.latest_standings(conn, season, f"segment{seg_no}")
            seg_ranked = list(seg.items())
            keep = set(list(seg)[:5]) | {self_name}
            sline = seg_ranked[opp.SEGMENT_PAID - 1][1] \
                if len(seg_ranked) >= opp.SEGMENT_PAID else None
            for i, (m, v) in enumerate(seg_ranked):
                if m in keep:
                    seg_rows.append({
                        "rank": i + 1, "manager": m, "total": v,
                        "gap_line": (v - sline) if sline else None,
                        "is_self": m == self_name,
                        "paid": i < opp.SEGMENT_PAID,
                        "prize": PRIZES_SEGMENT[i]
                        if i < len(PRIZES_SEGMENT) else None})

        my_next_pick = None
        if nxt is not None and self_name:
            picks = store.event_picks(conn, season, nxt["event_id"])
            mine = picks.get(self_name)
            if mine:
                disp = {}
                try:
                    p = store.latest_preds(conn, nxt["event_id"])
                    disp = dict(zip(p["key"], p["display_name"]))
                except Exception:
                    pass
                my_next_pick = ", ".join(disp.get(k, k) for k in mine)

        sim = _last_sim(season, "overall")
        ctx.update({
            "board": board,
            "boards": ["overall"] + [f"segment{i}" for i in range(1, 5)],
            "standings": rows, "self_rank": self_rank,
            "self_delta": deltas.get(self_name),
            "n_managers": len(rows), "paid": paid, "has_line": has_line,
            "cushion": cushion, "up_gap": up_gap,
            "events_left": len(remaining),
            "max_add": (0.18 * _purse(nxt)) if nxt is not None else None,
            "p_money": sim.get("p_money") if sim else None,
            "p_money_w": sim.get("p_money_w") if sim else None,
            "strip": strip, "spark": spark,
            "seg_rows": seg_rows, "seg_no": seg_no,
            "next_event": dict(nxt) if nxt is not None else None,
            "my_next_pick": my_next_pick,
        })
        return templates.TemplateResponse(request, "dashboard.html", ctx)

    # --------------------------------------------------------------- pick
    def _board_ctx(conn, season, ctx, event, posture):
        target = event or (ctx["pred_events"][-1]["name"]
                           if ctx["pred_events"] else None)
        if not target:
            return None
        erow = store.resolve_event(conn, season, target)
        preds = store.latest_preds(conn, erow["event_id"])
        self_name = ctx["self_name"]
        used = store.used_set(conn, season, self_name) if self_name else set()
        inel = store.ineligible_keys(conn, erow, preds)
        b = ev_board(preds, _purse(erow), used, has_cut=bool(erow["has_cut"]),
                     ineligible=set(inel), posture=posture)
        lg = _league(conn, season)
        n_mgr = max(len(store.managers_list(conn)), 1)
        used_counts = lg["picks"].groupby("key")["manager"].nunique() \
            if len(lg["picks"]) else pd.Series(dtype=int)
        # money-line rivals' locked picks at this event
        overall = store.latest_standings(conn, season, "overall")
        line_rivals = set(list(overall)[:opp.OVERALL_PAID + 3]) - {self_name}
        locked = store.event_picks(conn, season, erow["event_id"])
        locked_by: dict = {}
        for m, ks in locked.items():
            if m == self_name:
                continue
            for k in ks:
                locked_by.setdefault(k, []).append(m)

        rows = []
        max_ev = float(b["exp"].max()) if len(b) else 1.0
        for _, r in b.head(30).iterrows():
            uses = int(used_counts.get(r["key"], 0))
            ev_rank = len(rows) + 1
            rows.append({
                **r.to_dict(),
                "ev_pct": 100 * r["exp"] / max_ev if max_ev else 0,
                "floor_pct": 100 * r["floor"] / max_ev if max_ev else 0,
                "league_use": uses / n_mgr,
                "leverage": uses / n_mgr < 0.10 and ev_rank <= 8,
                "locked_line": [m for m in locked_by.get(r["key"], [])
                                if m in line_rivals],
                "delta_score": r["score"] - r["exp"],
            })
        n_am = int(preds["amateur"].astype(bool).sum()) \
            if "amateur" in preds.columns else 0
        my_locked = locked.get(self_name, []) if self_name else []
        return {
            "event_row": dict(erow), "purse": _purse(erow),
            "pulled_at": (preds.attrs.get("pulled_at") or "")[:10],
            "used_count": len(used), "inel_count": len(inel),
            "board_rows": rows, "max_ev": max_ev,
            "field_n": len(preds), "n_amateurs": n_am,
            "posture": posture, "my_locked": my_locked,
        }

    @app.get("/pick", response_class=HTMLResponse)
    def pick(request: Request, event: str = None, posture: str = "neutral"):
        conn = _conn()
        season = _season(conn)
        ctx = _base_ctx(request, conn, season, "pick")
        bctx = _board_ctx(conn, season, ctx, event, posture) \
            if ctx["pred_events"] else None
        if bctx:
            ctx.update(bctx)
        else:
            ctx.update({"event_row": None, "board_rows": [],
                        "posture": posture})
        if request.headers.get("HX-Request") and bctx:
            return templates.TemplateResponse(request,
                                              "partials/board.html", ctx)
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
                         row["top_20"], row["make_cut"], bool(erow["has_cut"]))
        mids = [(BUCKETS[bk][0] + BUCKETS[bk][1]) / 2 * purse
                for bk in BUCKET_ORDER]
        labels = {"W": "Win", "2": "Solo 2nd", "35": "3rd–5th",
                  "610": "6th–10th", "1120": "11th–20th", "2140": "21st–40th",
                  "41C": "41st–cut", "MC": "Missed cut"}
        self_name = store.self_manager(conn)
        overall = store.latest_standings(conn, season, "overall")
        cushion = opp.money_cushion(overall, self_name, opp.OVERALL_PAID) \
            if self_name and overall else None
        chase = cushion is not None and cushion[0] < 0
        need = abs(cushion[0]) if chase else None
        buckets = [{"label": labels[bk], "p": float(pp), "pay": mid,
                    "ev": float(pp) * mid,
                    "covers": bool(need and mid >= need)}
                   for bk, pp, mid in zip(BUCKET_ORDER, p, mids)]
        max_ev = max((x["ev"] for x in buckets), default=1.0)
        total = sum(x["ev"] for x in buckets)
        locked_by = []
        for m, ks in store.event_picks(conn, season,
                                       erow["event_id"]).items():
            if key in ks and m != self_name:
                r_ = (list(overall).index(m) + 1) if m in overall else None
                locked_by.append((m, r_))
        return templates.TemplateResponse(request, "partials/why.html", {
            "request": request, "row": row.to_dict(),
            "event": _ev_name(erow["name"]), "event_raw": erow["name"],
            "buckets": buckets, "max_ev": max_ev, "total_ev": total,
            "locked_by": locked_by, "key": key})

    def _conditioned(conn, season, erow, key, n=8000):
        """P(money) etc. with self's pick at this event forced to `key`."""
        self_name = store.self_manager(conn)
        standings = store.latest_standings(conn, season, "overall")
        rows = _remaining(conn, season)
        beta = _get_beta(conn, season)
        profiles = _get_profiles(conn, season)
        plans, plan_probs, curves, purses, cuts = _plans(
            conn, season, rows, profiles, beta, self_name)
        name = erow["name"]
        slots = int(erow["picks_per_manager"] or 1)
        lineup = [key]
        my = plans.get(name, {}).get(self_name, [])
        for k in my:
            if len(lineup) >= slots:
                break
            if k != key:
                lineup.append(k)
        plans.setdefault(name, {})[self_name] = lineup
        res = race_mod.simulate_race(standings, plans, curves, purses, cuts,
                                     self_name, n=n,
                                     plan_probs=plan_probs or None)
        paid = opp.OVERALL_PAID
        pm = float(sum(v for k_, v in res["dist"].items() if k_ <= paid))
        eprize = float(sum(res["dist"].get(i + 1, 0) * PRIZES_OVERALL[i]
                           for i in range(len(PRIZES_OVERALL))))
        return {"p_money": pm, "prize": eprize}

    @app.post("/pick/compare", response_class=HTMLResponse)
    def pick_compare(request: Request, event: str = Form(...),
                     keys: str = Form(...)):
        conn = _conn()
        season = _season(conn)
        erow = store.resolve_event(conn, season, event)
        klist = [k for k in keys.split("|") if k][:3]
        preds = store.latest_preds(conn, erow["event_id"])
        disp = dict(zip(preds["key"], preds["display_name"]))
        results = []
        base = None
        for k in klist:
            ck = ("cmp", *_fingerprint(conn, season), erow["event_id"], k)
            if ck not in _model_cache:
                _model_cache[ck] = _conditioned(conn, season, erow, k)
            results.append({"key": k, "name": disp.get(k, k),
                            **_model_cache[ck]})
        if results:
            base = min(r["p_money"] for r in results)
        return templates.TemplateResponse(request, "partials/compare.html", {
            "request": request, "results": results, "base": base,
            "event": erow["name"]})

    @app.post("/api/lock")
    def api_lock(event: str = Form(...), key: str = Form(...)):
        conn = _conn()
        season = _season(conn)
        self_name = store.self_manager(conn)
        if not self_name:
            return JSONResponse({"ok": False, "error": "no self manager"},
                                status_code=400)
        erow = store.resolve_event(conn, season, event)
        mid = store.manager_id(conn, self_name)
        gid = store.golfer_id(conn, key)
        slots = int(erow["picks_per_manager"] or 1)
        have = conn.execute(
            "SELECT COUNT(*) FROM picks WHERE season=? AND event_id=? AND "
            "manager_id=?", (season, erow["event_id"], mid)).fetchone()[0]
        if have >= slots:
            return JSONResponse({"ok": False, "error": "all slots locked"},
                                status_code=409)
        conn.execute(
            "INSERT OR REPLACE INTO picks(season, event_id, manager_id, slot,"
            " golfer_id) VALUES(?,?,?,?,?)",
            (season, erow["event_id"], mid, have, gid))
        conn.commit()
        store.journal_add(conn, season, "lock",
                          f"locked {key} via web UI", erow["event_id"])
        return JSONResponse({"ok": True, "slot": have + 1, "of": slots})

    # --------------------------------------------------------- race outlook
    def _race_result(conn, season, board, n, sensitivity, point):
        self_name = store.self_manager(conn)
        segment = int(board[-1]) if board.startswith("segment") else None
        paid = opp.OVERALL_PAID if board == "overall" else opp.SEGMENT_PAID
        prizes = PRIZES_OVERALL if board == "overall" else PRIZES_SEGMENT
        standings = store.latest_standings(conn, season, board) or \
            {m: 0.0 for m in store.managers_list(conn)}
        rows = _remaining(conn, season, segment)
        if not rows or not self_name:
            return None
        beta = None if point else _get_beta(conn, season)
        profiles = _get_profiles(conn, season)
        plans, plan_probs, curves, purses, cuts = _plans(
            conn, season, rows, profiles, beta, self_name)
        res = race_mod.simulate_race(standings, plans, curves, purses, cuts,
                                     self_name, n=n,
                                     plan_probs=plan_probs or None)
        p_money = float(sum(v for k, v in res["dist"].items() if k <= paid))
        se = float(np.sqrt(max(p_money * (1 - p_money), 1e-9) / n))
        eprize = float(sum(res["dist"].get(i + 1, 0) * prizes[i]
                           for i in range(len(prizes))))
        my_total = standings.get(self_name, 0.0)
        ahead, behind, out_of_reach = [], [], []
        golfers = {}
        for name_, plan in plans.items():
            for m, ks in plan.items():
                golfers.setdefault(m, []).extend(ks)
        my_golfers = set(golfers.get(self_name, []))
        for m, p in res["passes"].items():
            gap = standings.get(m, 0.0) - my_total
            their = golfers.get(m, [])
            shared = bool(set(their) & my_golfers)
            row = {"manager": m, "p_ahead": p, "gap": gap,
                   "golfers": their[:2], "shared": shared,
                   "gap_pct": max(-1, min(1, gap / 2e6)),
                   "straddle": (gap > 0) != ((gap + res["ev_added"].get(m, 0)
                                             - res["ev_added"].get(
                                                 self_name, 0)) > 0)}
            if gap > 0:
                (out_of_reach if p >= 0.99 else ahead).append(row)
            else:
                (out_of_reach if p <= 0.01 else behind).append(row)
        key_ = lambda r: (0 if abs(r["gap"]) < 1.2e6 else 1,
                          abs(r["p_ahead"] - 0.5))
        ahead.sort(key=key_)
        behind.sort(key=key_)
        dist_rows = [{"k": k, "p": v} for k, v in res["dist"].items()
                     if k <= 12]
        tail = float(sum(v for k, v in res["dist"].items() if k > 12))
        prev = _sim_cache.get(("last", app.state.db, season, board))
        out = {
            "board": board, "paid": paid, "n": n,
            "p_money": p_money, "p_money_w": se,
            "p_first": res["p_first"], "e_prize": eprize,
            "d_money": (p_money - prev["p_money"]) if prev else None,
            "dist": dist_rows, "tail": tail,
            "maxp": max((d["p"] for d in dist_rows), default=1.0),
            "ahead": ahead[:12], "behind": behind[:12],
            "n_out": len(out_of_reach),
            "out_names": ", ".join(r["manager"] for r in out_of_reach[:3]),
            "point": point,
            "events": [_ev_name(r["name"]) for r in rows],
        }
        if sensitivity:
            kr = ahead[0]["manager"] if ahead else None
            b = race_mod.sensitivity_band(
                standings, plans, curves, purses, cuts, self_name,
                metric="p_first" if board == "overall" else "p_top3",
                key_rival=kr, plan_probs=plan_probs or None)
            lo, hi = b.pop("band")
            out["band"] = {"lo": lo, "hi": hi, "rival": kr,
                           "rows": list(b.items())}
        _sim_cache[("last", app.state.db, season, board)] = out
        return out

    @app.get("/race", response_class=HTMLResponse)
    def race(request: Request, board: str = "overall"):
        conn = _conn()
        season = _season(conn)
        ctx = _base_ctx(request, conn, season, "race")
        ctx.update({"board": board,
                    "boards": ["overall"] + [f"segment{i}"
                                             for i in range(1, 5)],
                    "cached": _sim_cache.get(("last", app.state.db, season,
                                              board))})
        return templates.TemplateResponse(request, "race.html", ctx)

    @app.post("/race/run", response_class=HTMLResponse)
    def race_run(request: Request, board: str = Form("overall"),
                 n: int = Form(20000), sensitivity: bool = Form(False),
                 point: bool = Form(False)):
        conn = _conn()
        season = _season(conn)
        n = max(2000, min(int(n), 300_000))
        out = _race_result(conn, season, board, n, sensitivity, point)
        if out is None:
            return templates.TemplateResponse(
                request, "partials/ghost.html",
                {"request": request,
                 "caption": "ingest predictions — the projection desk "
                            "lands here"})
        return templates.TemplateResponse(request, "partials/race_result.html",
                                          {"request": request, **out})

    # --------------------------------------------------------- sunday sweat
    def _sunday_event(conn, season, ctx):
        """The event being sweated: locked picks, nothing settled, preds."""
        self_name = ctx["self_name"]
        best = None
        for e in ctx["pred_events"]:
            picks = store.event_picks(conn, season, e["event_id"])
            if self_name and picks.get(self_name):
                settled = conn.execute(
                    "SELECT COUNT(*) FROM picks WHERE season=? AND event_id=?"
                    " AND earnings IS NOT NULL",
                    (season, e["event_id"])).fetchone()[0]
                if not settled:
                    best = e
        return best or (ctx["pred_events"][-1] if ctx["pred_events"] else None)

    @app.get("/sunday", response_class=HTMLResponse)
    def sunday(request: Request):
        conn = _conn()
        season = _season(conn)
        ctx = _base_ctx(request, conn, season, "sunday")
        ev = _sunday_event(conn, season, ctx) if ctx["pred_events"] else None
        ctx["default_event"] = ev["name"] if ev else None
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
        asof = None
        round_warn = None
        if source == "live":
            from ..datagolf import DataGolfAPI
            try:
                ls = DataGolfAPI().live_stats()
                asof = str(ls["last_updated"].iloc[0])[:16]
            except RuntimeError as e:
                return templates.TemplateResponse(
                    request, "partials/ghost.html",
                    {"request": request, "caption": str(e)})
            rnd = pd.to_numeric(ls.get("stat_round"), errors="coerce").max()
            if pd.notna(rnd) and int(rnd) != 3:
                round_warn = (f"live feed is at round {int(rnd)} — the "
                              "final-round model assumes 54 holes done")
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
            return templates.TemplateResponse(
                request, "partials/ghost.html",
                {"request": request, "caption": "self manager missing from "
                                                "standings"})
        st = totals[self_name]
        paid = opp.OVERALL_PAID
        ahead_ct = np.zeros(n, np.int32)
        for m, t in totals.items():
            if m != self_name:
                ahead_ct += (t > st).astype(np.int32)
        finish = ahead_ct + 1
        p_money = float((finish <= paid).mean())
        se = float(np.sqrt(max(p_money * (1 - p_money), 1e-9) / n))
        exp_rank = float(finish.mean())
        now_rank = 1 + sum(1 for m, v in standings.items()
                           if m != self_name and v > standings[self_name])
        e_prize = float(sum((finish == i + 1).mean() * PRIZES_OVERALL[i]
                            for i in range(len(PRIZES_OVERALL))))
        disp = dict(zip(preds["key"], preds["display_name"]))
        pos_disp = {store.norm(r["player_name"]): int(r["to_par"])
                    for _, r in pos_df.iterrows()}

        # my golfer cards + sweat strip on the primary holding
        holdings = []
        for k in picks.get(self_name, []):
            holdings.append({
                "key": k, "name": disp.get(k, k),
                "to_par": pos_disp.get(k),
                "proj": float(pay[k].mean()) if k in pay else 0.0,
                "in_field": k in pay})
        sweat = None
        primary = max(holdings, key=lambda h: h["proj"], default=None)
        if primary and primary["key"] in pay:
            pk = primary["key"]
            idx = players.index(pk)
            order = np.argsort(tot, axis=1, kind="stable")
            fin_pos = np.empty_like(order)
            np.put_along_axis(fin_pos, order,
                              np.arange(tot.shape[1])[None, :], axis=1)
            my_fin = fin_pos[:, idx] + 1
            lad = ladder(purse, len(players))
            self_start = float(standings[self_name])
            rivals_exp = {m: float(totals[m].mean()) for m in totals
                          if m != self_name}
            cols, band = [], []
            top_show = min(len(players), 30)
            for f in range(1, top_show + 1):
                pf = float((my_fin == f).mean())
                total_f = self_start + \
                    sum(h["proj"] for h in holdings if h["key"] != pk) + \
                    (lad[f - 1] if f <= len(lad) else 0.0)
                rank_f = 1 + sum(1 for v in rivals_exp.values()
                                 if v > total_f)
                cols.append({"f": f, "p": pf})
                if rank_f <= paid:
                    band.append(f)
            markers = []
            for m, v in sorted(standings.items(), key=lambda kv: -kv[1]):
                if m == self_name or v <= self_start:
                    continue
                gap = v - self_start
                covers = np.where(lad > gap)[0]
                if len(covers):
                    fneed = int(covers.max()) + 1
                    p_pass = float((st > totals[m]).mean())
                    if 0.02 < p_pass < 0.98 and fneed <= top_show:
                        markers.append({"rival": m, "f": fneed,
                                        "pays": float(lad[covers.max()]),
                                        "p": p_pass})
            sweat = {"cols": cols, "maxp": max((c["p"] for c in cols),
                                              default=1.0),
                     "band_lo": min(band) if band else None,
                     "band_hi": max(band) if band else None,
                     "markers": markers[:6], "golfer": primary["name"]}

        lad = ladder(purse, len(players))
        self_start = float(standings[self_name])
        attack, defense = [], []
        for m, v in sorted(standings.items(), key=lambda kv: -kv[1]):
            if m == self_name:
                continue
            their = [disp.get(k, k) for k in picks.get(m, [])]
            their_pos = [pos_disp.get(k) for k in picks.get(m, [])]
            if v > self_start:
                gap = v - self_start
                covers = np.where(lad > gap)[0]
                p_pass = float((st > totals[m]).mean())
                attack.append({
                    "manager": m, "gap": gap, "p": p_pass,
                    "needs": f"solo-{covers.max() + 1}" if len(covers)
                    else "out of range",
                    "pays": float(lad[covers.max()]) if len(covers) else None,
                    "golfers": list(zip(their, their_pos)),
                    "heat": abs(p_pass - 0.5)})
            else:
                gap = self_start - v
                covers = np.where(lad > gap)[0]
                p_they = float((totals[m] > st).mean())
                if p_they > 0.005:
                    my_rank_now = now_rank
                    defense.append({
                        "manager": m, "gap": gap, "p": p_they,
                        "needs": f"solo-{covers.max() + 1}" if len(covers)
                        else "—",
                        "golfers": list(zip(their, their_pos)),
                        "alarm": p_they > 0.40,
                        "knocks_out": my_rank_now <= paid and
                        (now_rank + 1) > paid})
        attack.sort(key=lambda r: r["heat"])
        defense.sort(key=lambda r: -r["p"])
        reach = [a for a in attack if 0.02 < a["p"]]
        out_r = [a["manager"] for a in attack if a["p"] <= 0.02]
        am_notes = [(m, disp.get(k, k)) for m, ks in picks.items()
                    for k in ks if k in amateurs]

        return templates.TemplateResponse(request, "partials/sunday_card.html", {
            "request": request, "event": _ev_name(erow["name"]),
            "now_rank": now_rank, "now_prize":
                PRIZES_OVERALL[now_rank - 1] if now_rank <=
                len(PRIZES_OVERALL) else None,
            "p_money": p_money, "p_money_w": se,
            "exp_rank": exp_rank, "e_prize": e_prize,
            "holdings": holdings, "sweat": sweat,
            "round_warn": round_warn,
            "attack": reach[:8], "n_out": len(out_r),
            "out_names": ", ".join(out_r[:3]),
            "defense": defense[:8], "amateurs": am_notes,
            "n_players": len(players), "asof": asof, "paid": paid})

    # ------------------------------------------------------------ season map
    @app.get("/season", response_class=HTMLResponse)
    def season_map(request: Request):
        conn = _conn()
        season = _season(conn)
        ctx = _base_ctx(request, conn, season, "season")
        self_name = ctx["self_name"]
        lg = _league(conn, season)
        picks = lg["picks"]
        mine = picks[picks["manager"] == self_name] if self_name \
            else picks[:0]
        by_event = {int(e): g for e, g in mine.groupby("event_id")}
        with_preds = set(store.events_with_preds(conn, season))
        max_purse = max((_purse(e) for e in map(dict, ctx["events"])),
                        default=1e7)
        max_earn = max((float(g["earnings"].max())
                        for g in by_event.values()
                        if g["earnings"].notna().any()), default=1.0) or 1.0
        rows = []
        here_done = False
        for e in ctx["events"]:
            g = by_event.get(e["event_id"])
            pick_txt = ", ".join(g["display_name"]) if g is not None else None
            settled = g is not None and g["earnings"].notna().any()
            earned = float(g["earnings"].sum()) if settled else None
            status = ("settled" if settled else
                      "locked" if pick_txt else
                      "next" if not here_done and
                      e["event_id"] in with_preds else "upcoming")
            if status in ("next",):
                here_done = True
            rows.append({**e, "pick": pick_txt, "earned": earned,
                         "status": status, "strong": _is_strong(e),
                         "r": 4 + 6 * (_purse(e) / max_purse),
                         "earn_pct": (earned / max_earn) if earned else 0.0})
        # trophy footers per segment
        segs = {}
        for s in sorted({r["segment"] for r in rows if r["segment"]}):
            seg_stand = store.latest_standings(conn, season, f"segment{s}")
            fin = list(seg_stand).index(self_name) + 1 \
                if self_name in seg_stand else None
            tot = sum(r["earned"] or 0 for r in rows if r["segment"] == s)
            done = all(r["status"] == "settled" for r in rows
                       if r["segment"] == s)
            segs[s] = {"total": tot, "rank": fin, "done": done,
                       "paid": PRIZES_SEGMENT[fin - 1]
                       if fin and fin <= len(PRIZES_SEGMENT) and done
                       else None}
        # hoard strip: best unused by latest preds win
        hoard = []
        try:
            if ctx["pred_events"]:
                eid = ctx["pred_events"][-1]["event_id"]
                p = store.latest_preds(conn, eid)
                used = store.used_set(conn, season, self_name) \
                    if self_name else set()
                avail = p[~p["key"].isin(used)].nlargest(8, "win")
                hoard = list(avail["display_name"])
        except Exception:
            pass
        ctx.update({"schedule": rows, "segs": segs, "hoard": hoard})
        return templates.TemplateResponse(request, "season.html", ctx)

    @app.post("/season/plan", response_class=HTMLResponse)
    def season_plan(request: Request, posture: str = Form("neutral"),
                    reserve: str = Form(""), top_k: int = Form(8)):
        conn = _conn()
        season = _season(conn)
        self_name = store.self_manager(conn)
        rows = _remaining(conn, season)
        if not self_name or not rows:
            return templates.TemplateResponse(
                request, "partials/ghost.html",
                {"request": request,
                 "caption": "ingest predictions — the season plan lands here"})
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
                label = _ev_name(erow["name"]) if slots == 1 else \
                    f"{_ev_name(erow['name'])} · slot {len(locked) + s + 1}"
                boards[label] = pool
                labels[label] = disp
        best = seq_solve(boards, top_k=top_k)
        if not best:
            return HTMLResponse("<p class='empty'>no feasible assignment — "
                                "widen top-k</p>")
        tot, asg = best
        plan = [{"slot": lab, "golfer": labels[lab].get(asg[lab], asg[lab]),
                 "ev": dict((k, v) for v, k in boards[lab]).get(asg[lab], 0.0)}
                for lab in boards]
        return templates.TemplateResponse(request, "partials/season_plan.html",
                                          {"request": request, "plan": plan,
                                           "total": tot, "posture": posture})

    # --------------------------------------------------------------- history
    @app.get("/history", response_class=HTMLResponse)
    def history(request: Request):
        conn = _conn()
        season = _season(conn)
        ctx = _base_ctx(request, conn, season, "history")
        self_name = ctx["self_name"]
        lg = _league(conn, season)
        chart = None
        if lg["cum"] is not None and self_name in lg["cum"].columns:
            cum = lg["cum"]
            paid = opp.OVERALL_PAID
            xs = np.linspace(40, 1180, len(cum))
            top = float(cum.max().max()) or 1.0
            yp = lambda v: 290 - 260 * (v / top)
            sixth = cum.apply(lambda r: r.nlargest(min(paid, len(r))).iloc[-1],
                              axis=1)
            first = cum.max(axis=1)
            cross = None
            above = cum[self_name] >= sixth
            for i, a in enumerate(above):
                if a and (i == 0 or not above.iloc[i - 1]):
                    cross = i
            chart = {
                "self_d": _path(xs, [yp(v) for v in cum[self_name]]),
                "line_d": _path(xs, [yp(v) for v in sixth]),
                "first_d": _path(xs, [yp(v) for v in first]),
                "end_self": float(cum[self_name].iloc[-1]),
                "end_line": float(sixth.iloc[-1]),
                "end_first": float(first.iloc[-1]),
                "y_self": yp(float(cum[self_name].iloc[-1])),
                "y_line": yp(float(sixth.iloc[-1])),
                "y_first": yp(float(first.iloc[-1])),
                "cross_x": float(xs[cross]) if cross is not None else None,
                "weeks": len(cum),
            }
        picks = lg["picks"]
        mine = picks[(picks["manager"] == self_name)
                     & picks["earnings"].notna()] if self_name else picks[:0]
        my_rows = mine.to_dict("records")
        my_total = float(mine["earnings"].sum()) if len(mine) else 0.0
        profiles = []
        try:
            overall = store.latest_standings(conn, season, "overall")
            profs = _get_profiles(conn, season)
            order = [m for m in overall if m != self_name] or list(profs)
            if self_name in overall:
                si = list(overall).index(self_name)
                order.sort(key=lambda m: abs(list(overall).index(m) - si)
                           if m in overall else 99)
            for m in order[:12]:
                if m in profs:
                    p = profs[m]
                    profiles.append({**vars(p),
                                     "rank": (list(overall).index(m) + 1)
                                     if m in overall else None})
        except Exception:
            pass
        journal = store.journal_df(conn, season)
        ctx.update({"chart": chart, "my_picks": my_rows,
                    "my_total": my_total, "profiles": profiles,
                    "journal": journal.to_dict("records")
                    if len(journal) else []})
        return templates.TemplateResponse(request, "history.html", ctx)

    return app


app = create_app()
