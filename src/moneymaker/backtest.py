"""Replay a season per docs/BACKTEST_PLAN.md.

Per event, using ONLY information available at that pick deadline: the
nearest-prior workbook supplies every manager's used set; the event's
DataGolf CSV supplies the board. Engine pick vs actual pick vs realized
earnings, with SumEV acceptance totals. Deadline workbook selection is
content-based (no filename dates needed): the workbook with the most
progressed pick history that still has NO picks for the event.
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
    final = books[-1]

    conn = store.connect(":memory:")
    store.ingest_league(conn, final, season)
    if manager:
        store.set_self(conn, manager)
    manager = manager or store.self_manager(conn)
    if not manager:
        raise ValueError("pass --manager (no is_self manager in final workbook)")

    parsed = []
    for b in books:
        sel, _ = league.load_selections(b)
        groups = league.group_events(league.event_columns(sel))
        parsed.append((b, sel, groups, _progress(sel, groups)))

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

        # Deadline snapshot: most progressed workbook with no picks yet here.
        # By construction it holds only pre-deadline picks, so its full pick
        # set for the manager IS the used set at lock time.
        candidates = [(b, sel) for b, sel, groups, prog in parsed
                      if prog < erow["seq"]]
        wb, sel = candidates[-1] if candidates else parsed[0][:2]
        try:
            used = league.used_set(sel, manager)
        except KeyError:
            used = set()

        purse = erow["purse"] or 1e7
        has_cut = bool(preds.attrs.get("has_cut", True))
        ineligible = store.ineligible_keys(conn, erow, preds)
        b_df = ev_board(preds, purse, used, has_cut=has_cut,
                        ineligible=set(ineligible))
        engine = b_df.iloc[0] if len(b_df) else None

        actual = store.event_picks(conn, season, erow["event_id"]).get(manager, [])
        actual_key = actual[0] if actual else None
        a_row = b_df[b_df["key"] == actual_key]
        realized = conn.execute(
            "SELECT SUM(p.earnings) FROM picks p JOIN managers m "
            "ON m.manager_id=p.manager_id WHERE p.season=? AND p.event_id=? "
            "AND m.name=?", (season, erow["event_id"], manager)).fetchone()[0]

        rows.append({
            "event": erow["name"], "seq": erow["seq"],
            "deadline_workbook": os.path.basename(wb),
            "engine_pick": engine["key"] if engine is not None else None,
            "engine_ev": float(engine["exp"]) if engine is not None else 0.0,
            "actual_pick": actual_key,
            "actual_ev": float(a_row["exp"].iloc[0]) if len(a_row) else 0.0,
            "realized": float(realized) if realized is not None else None,
        })

    df = pd.DataFrame(rows)
    ok = df.dropna(subset=["engine_ev"]) if "engine_ev" in df else df
    summary = {
        "manager": manager,
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
