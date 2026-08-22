"""Replay a season per docs/BACKTEST_PLAN.md.

Per event, using ONLY information available at that pick deadline. Selection
is CONTENT-based (filenames never matter): the season-final workbook is the
one with the most progressed pick history, and each event's used set is the
picks recorded at strictly-earlier events — exactly what was known at lock.
Majors compare like with like: engine and actual EVs both cover every slot.
"""
import json
import os

import numpy as np
import pandas as pd

from . import choice, league, opponents as opp, store
from .datagolf import load_preds_csv
from .ev import board as ev_board


def _workbooks(league_dir):
    return sorted(os.path.join(league_dir, f) for f in os.listdir(league_dir)
                  if f.endswith(".xlsx") and not f.startswith("~"))


def _progress(sel, groups) -> int:
    """Highest event seq with any pick recorded in this workbook."""
    last = -1
    for g in groups:
        if any(e for e in league.group_picks(sel, g).values()):
            last = g["seq"]
    return last


def _resolve_preds_event(conn, season, frag):
    """Map a preds FILENAME to a sheet event. Filenames carry noise
    ('..._preds_ch_model_2'), so after the direct substring try, fall back to
    reverse containment — the event name inside the filename — preferring the
    longest name ('genesis scottish' must beat 'genesis')."""
    from .names import norm_event
    try:
        return store.resolve_event(conn, season, frag)
    except KeyError:
        pass
    nfrag = norm_event(frag)
    rows = conn.execute("SELECT * FROM events WHERE season=? ORDER BY seq",
                        (season,)).fetchall()
    hits = [r for r in rows
            if norm_event(r["name"]) and norm_event(r["name"]) in nfrag]
    if not hits:
        return None
    return max(hits, key=lambda r: len(norm_event(r["name"])))


def replay(league_dir: str, preds_dir: str, season: int,
           manager: str | None = None, out_json: str | None = None,
           purse_overrides: dict | None = None):
    """purse_overrides: event-name fragment -> purse in DOLLARS, for events
    whose sheet title carries no purse suffix (the majors)."""
    books = _workbooks(league_dir)
    if not books:
        raise FileNotFoundError(f"no workbooks in {league_dir}")

    parsed = []
    for b in books:
        sel, _ = league.load_selections(b)
        groups = league.group_events(league.event_columns(sel))
        parsed.append((b, sel, groups, _progress(sel, groups)))
    final_wb, final_sel, final_groups, _ = max(parsed, key=lambda t: t[3])

    conn = store.connect(":memory:")
    store.ingest_league(conn, final_wb, season)
    for frag, purse in (purse_overrides or {}).items():
        erow = store.resolve_event(conn, season, frag)
        conn.execute("UPDATE events SET purse=? WHERE event_id=?",
                     (purse, erow["event_id"]))
    if manager:
        store.set_self(conn, manager)
    manager = manager or store.self_manager(conn)
    if not manager:
        raise ValueError("pass --manager (no is_self manager in final workbook)")

    rows = []
    for f in sorted(os.listdir(preds_dir)):
        if not f.endswith(".csv"):
            continue
        frag = os.path.splitext(f)[0].replace("_", " ").replace("-", " ")
        erow = _resolve_preds_event(conn, season, frag)
        if erow is None:
            rows.append({"event": frag, "note": "no matching sheet event"})
            continue
        preds = load_preds_csv(os.path.join(preds_dir, f))

        # Used set at lock = picks at strictly earlier events, taken from the
        # final workbook (immune to workbook selection and never leaks the
        # event's own pick). The nearest-prior workbook is reported for
        # transparency only.
        used = set()
        for g in final_groups:
            if g["seq"] < erow["seq"]:
                for slot, raw in league.group_picks(
                        final_sel, g).get(manager, []):
                    used.add(store.norm(raw))
        prior = [t for t in parsed if t[3] < erow["seq"]]
        deadline = max(prior, key=lambda t: t[3])[0] if prior else None

        purse = erow["purse"] or 1e7
        has_cut = bool(preds.attrs.get("has_cut", True))
        ineligible = store.ineligible_keys(conn, erow, preds)
        b_df = ev_board(preds, purse, used, has_cut=has_cut,
                        ineligible=set(ineligible))
        slots = int(erow["picks_per_manager"] or 1)
        engine_keys = list(b_df["key"].head(slots))
        engine_ev = float(b_df["exp"].head(slots).sum())

        actual = store.event_picks(conn, season, erow["event_id"]).get(manager, [])
        actual_ev = float(b_df.loc[b_df["key"].isin(actual), "exp"].sum())
        realized = conn.execute(
            "SELECT SUM(p.earnings) FROM picks p JOIN managers m "
            "ON m.manager_id=p.manager_id WHERE p.season=? AND p.event_id=? "
            "AND m.name=?", (season, erow["event_id"], manager)).fetchone()[0]

        rows.append({
            "event": erow["name"], "seq": erow["seq"],
            "deadline_workbook": os.path.basename(deadline) if deadline
            else "(pre-season)",
            "engine_pick": ", ".join(engine_keys) or None,
            "engine_ev": engine_ev,
            "actual_pick": ", ".join(actual) or None,
            "actual_ev": actual_ev,
            "realized": float(realized) if realized is not None else None,
        })

    df = pd.DataFrame(rows)
    ok = df.dropna(subset=["engine_ev"]) if "engine_ev" in df else df
    summary = {
        "manager": manager,
        "final_workbook": os.path.basename(final_wb),
        "sum_ev_engine": float(ok["engine_ev"].sum()) if len(ok) else 0.0,
        "sum_ev_actual": float(ok["actual_ev"].sum()) if len(ok) else 0.0,
        "sum_realized": float(ok["realized"].dropna().sum())
        if "realized" in ok else 0.0,
    }
    summary["accept_sum_ev"] = summary["sum_ev_engine"] >= summary["sum_ev_actual"]
    if out_json:
        os.makedirs(os.path.dirname(os.path.abspath(out_json)), exist_ok=True)
        with open(out_json, "w") as fh:
            json.dump({"summary": summary, "events": rows}, fh, indent=2)
    return df, summary


# ------------------- opponent-model walk-forward evaluation -------------------

def _asof_used(conn, season: int, before_seq: int) -> dict:
    """manager -> set of keys picked at events strictly before before_seq."""
    out: dict[str, set] = {}
    for r in conn.execute(
            "SELECT m.name, g.key FROM picks p"
            " JOIN events e ON e.event_id=p.event_id"
            " JOIN managers m ON m.manager_id=p.manager_id"
            " JOIN golfers g ON g.golfer_id=p.golfer_id"
            " WHERE p.season=? AND e.seq<?", (season, before_seq)):
        out.setdefault(r[0], set()).add(r[1])
    return out


def eval_opponents(league_dir: str, preds_dir: str, season: int,
                   manager: str | None = None,
                   purse_overrides: dict | None = None):
    """Walk-forward test of rival-pick prediction: for every archived event,
    predict each manager's pick using ONLY deadline-time information, with
    (a) the validated baseline heuristic and (b) the posture-aware variant.
    Returns (per-event DataFrame, summary dict). Rivals-only is the headline
    metric — the self manager picked WITH an engine and is atypical."""
    books = _workbooks(league_dir)
    parsed = []
    for b in books:
        sel, _ = league.load_selections(b)
        groups = league.group_events(league.event_columns(sel))
        parsed.append((b, sel, groups, _progress(sel, groups)))
    final_wb = max(parsed, key=lambda t: t[3])[0]

    fin = store.connect(":memory:")
    store.ingest_league(fin, final_wb, season)
    for frag, purse in (purse_overrides or {}).items():
        erow = store.resolve_event(fin, season, frag)
        fin.execute("UPDATE events SET purse=? WHERE event_id=?",
                    (purse, erow["event_id"]))
    if manager:
        store.set_self(fin, manager)
    self_name = manager or store.self_manager(fin)

    csvs = []
    for f in sorted(os.listdir(preds_dir)):
        if not f.endswith(".csv"):
            continue
        frag = os.path.splitext(f)[0].replace("_", " ").replace("-", " ")
        erow = _resolve_preds_event(fin, season, frag)
        if erow is not None:
            csvs.append((erow["seq"], f, erow))
    csvs.sort()

    rows, details, train_rows = [], [], []
    for seq, fname, erow in csvs:
        preds = load_preds_csv(os.path.join(preds_dir, fname))
        prior = [t for t in parsed if t[3] < seq]
        dl_wb = max(prior, key=lambda t: t[3])[0] if prior else parsed[0][0]

        dl = store.connect(":memory:")
        store.ingest_league(dl, dl_wb, season)
        for frag, purse in (purse_overrides or {}).items():
            try:
                e2 = store.resolve_event(dl, season, frag)
                dl.execute("UPDATE events SET purse=? WHERE event_id=?",
                           (purse, e2["event_id"]))
            except KeyError:
                pass
        if self_name:
            try:
                store.set_self(dl, self_name)
            except Exception:
                pass
        # prior preds give the profile miner chalk history where it exists
        for pseq, pf, _ in csvs:
            if pseq < seq:
                pe = _resolve_preds_event(dl, season, os.path.splitext(pf)[0]
                                          .replace("_", " ").replace("-", " "))
                if pe is not None:
                    store.ingest_preds_frame(
                        dl, load_preds_csv(os.path.join(preds_dir, pf)),
                        pe["event_id"], "csv")

        profiles = opp.mine_profiles(dl, season)
        dl_picks = store.picks_df(dl, season)
        hot = opp.hot_keys(dl_picks, int(seq))
        overall = store.latest_standings(dl, season, "overall")
        seg_board = store.latest_standings(
            dl, season, f"segment{erow['segment']}") if erow["segment"] else {}
        pl_overall = opp.purse_left(dl, season, int(seq))
        pl_segment = opp.purse_left(dl, season, int(seq),
                                    int(erow["segment"] or 0) or None)
        used_asof = _asof_used(fin, season, int(seq))
        actual = store.event_picks(fin, season, erow["event_id"])
        purse = erow["purse"] or 1e7
        has_cut = bool(preds.attrs.get("has_cut", True))

        pop = choice.popularity(fin, season, int(seq))
        beta = choice.fit(train_rows) if train_rows else None
        used_default_beta = beta is None
        if beta is None:
            beta = choice.DEFAULT_BETA
        beta_ev = None
        if train_rows:
            ev_rows = [(X[:, :1], c) for X, c in train_rows]
            beta_ev = choice.fit(ev_rows, beta0=np.array([1.5]))
        if beta_ev is None:
            beta_ev = np.array([choice.DEFAULT_BETA[0]])

        n = b1 = b3 = p1 = p3 = c1 = c3 = 0
        lls, ev_lls, unif_lls = [], [], []
        postures = {}
        new_rows = []
        for mgr in store.managers_list(fin):
            act = set(actual.get(mgr, []))
            if not act:
                continue
            board = ev_board(preds, purse, used_asof.get(mgr, set()),
                             has_cut=has_cut).head(60)
            tb = [(r["exp"], r["key"], r["key"] in hot, r["win"], r["floor"])
                  for _, r in board.head(12).iterrows()]
            prof = profiles.get(mgr, opp.Profile(manager=mgr))
            base = opp.rank_candidates(prof, tb, None)
            posture = opp.posture_for(mgr, overall, seg_board,
                                      pl_overall, pl_segment)
            post = opp.rank_candidates(prof, tb, posture)
            postures[posture] = postures.get(posture, 0) + 1

            keys = list(board["key"])
            X = choice.feature_matrix(board, hot, prof, pop)
            proba = choice.predict_proba(beta, X)
            ranked = [keys[i] for i in proba.argsort()[::-1]]
            proba_ev = choice.predict_proba(beta_ev, X[:, :1])
            is_self = mgr == self_name
            for k in act:                       # log-loss per slot decision
                if k in keys:
                    i = keys.index(k)
                    if not is_self:
                        lls.append(-np.log(max(proba[i], 1e-12)))
                        ev_lls.append(-np.log(max(proba_ev[i], 1e-12)))
                        unif_lls.append(np.log(len(keys)))
                    new_rows.append((X, i))
            if not is_self:
                n += 1
                b1 += base[:1] != [] and base[0] in act
                b3 += bool(set(base[:3]) & act)
                p1 += post[:1] != [] and post[0] in act
                p3 += bool(set(post[:3]) & act)
                c1 += ranked[:1] != [] and ranked[0] in act
                c3 += bool(set(ranked[:3]) & act)
            details.append({"event": erow["name"], "manager": mgr,
                            "posture": posture, "actual": ", ".join(act),
                            "base_top1": base[0] if base else None,
                            "post_top1": post[0] if post else None,
                            "choice_top1": ranked[0] if ranked else None,
                            "is_self": is_self})
        train_rows.extend(new_rows)
        rows.append({"event": erow["name"], "rivals": n,
                     "base_top1": b1 / n if n else 0.0,
                     "base_top3": b3 / n if n else 0.0,
                     "post_top1": p1 / n if n else 0.0,
                     "post_top3": p3 / n if n else 0.0,
                     "choice_top1": c1 / n if n else 0.0,
                     "choice_top3": c3 / n if n else 0.0,
                     "choice_ll": float(np.mean(lls)) if lls else None,
                     "ev_ll": float(np.mean(ev_lls)) if ev_lls else None,
                     "unif_ll": float(np.mean(unif_lls)) if unif_lls else None,
                     "cold_start": used_default_beta,
                     "postures": postures})

    df = pd.DataFrame(rows)
    tot = df["rivals"].sum()
    warm = df[~df["cold_start"]]
    wtot = warm["rivals"].sum()
    summary = {
        "rival_predictions": int(tot),
        "baseline_top1": float((df["base_top1"] * df["rivals"]).sum() / tot),
        "baseline_top3": float((df["base_top3"] * df["rivals"]).sum() / tot),
        "postured_top1": float((df["post_top1"] * df["rivals"]).sum() / tot),
        "postured_top3": float((df["post_top3"] * df["rivals"]).sum() / tot),
        "choice_top1": float((df["choice_top1"] * df["rivals"]).sum() / tot),
        "choice_top3": float((df["choice_top3"] * df["rivals"]).sum() / tot),
        # log-loss comparison on FITTED weeks only (cold start excluded)
        "choice_ll": float((warm["choice_ll"] * warm["rivals"]).sum() / wtot)
        if wtot else None,
        "ev_ll": float((warm["ev_ll"] * warm["rivals"]).sum() / wtot)
        if wtot else None,
        "unif_ll": float((warm["unif_ll"] * warm["rivals"]).sum() / wtot)
        if wtot else None,
    }
    return df, summary, pd.DataFrame(details)
