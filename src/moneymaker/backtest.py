"""Replay a season per docs/BACKTEST_PLAN.md.

Per event, using ONLY information available at that pick deadline. Selection
is CONTENT-based (filenames never matter): the season-final workbook is the
one with the most progressed pick history, and each event's used set is the
picks recorded at strictly-earlier events — exactly what was known at lock.
Majors compare like with like: engine and actual EVs both cover every slot.
"""
import json
import os

import pandas as pd

from . import league, store
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


def replay(league_dir: str, preds_dir: str, season: int,
           manager: str | None = None, out_json: str | None = None):
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
        try:
            erow = store.resolve_event(conn, season, frag)
        except KeyError:
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
