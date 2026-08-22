"""Opponent tendency mining (ALGORITHMS s7). The predict_pick heuristic below
predicted 5/8 rival picks in a measured 2026 week — do not retune it without
a backtest. Mining wires the metrics to real pick history in the store."""
from dataclasses import dataclass

import pandas as pd

from . import store
from .ev import board as ev_board


def _purse(event_row, default=1e7) -> float:
    p = event_row["purse"]
    return float(p) if p is not None and pd.notna(p) and p > 0 else default


@dataclass
class Profile:
    manager: str
    chalk_rate: float = 0.0        # picked event's top-EV available
    form_chase_rate: float = 0.0   # picked prior week's top-10 finisher
    mirror_rate: float = 0.0       # matched self's pick
    hoard_score: float = 0.0       # elite names held past best spots
    events_measured: int = 0


def predict_pick(profile: Profile, their_board):
    """their_board: list[(ev, key, is_prior_week_hot)] desc by ev.
    2026-validated heuristic: chalk unless a hot name sits within 15% EV
    and the rival is a form-chaser."""
    if not their_board:
        return None
    top = their_board[0]
    for ev, key, hot in their_board[:5]:
        if hot and ev >= top[0] * 0.85 and profile.form_chase_rate > 0.4:
            return key
    return top[1]


def hot_keys(picks, event_seq: int, top_n: int = 10) -> set:
    """Prior-week 'hot list': golfers in the top-N of settled earnings at the
    event before event_seq. Proxy built from picked golfers only — the sheet
    doesn't carry full leaderboards (documented limitation, phase 1)."""
    prev = picks[(picks["seq"] < event_seq) & picks["earnings"].notna()]
    if prev.empty:
        return set()
    last_seq = prev["seq"].max()
    week = (prev[prev["seq"] == last_seq]
            .groupby("key")["earnings"].max().sort_values(ascending=False))
    return set(week.head(top_n).index)


def mine_profiles(conn, season: int) -> dict[str, Profile]:
    """Build a Profile per rival from stored pick history (+ preds history
    where it exists — chalk_rate only counts events with stored preds)."""
    picks = store.picks_df(conn, season)
    if picks.empty:
        return {}
    self_rows = picks[picks["is_self"] == 1]
    self_by_event = self_rows.groupby("event_id")["key"].agg(set).to_dict()
    preds_events = set(store.events_with_preds(conn, season))
    events = store.events_df(conn, season).set_index("event_id")

    # Elite pool for hoarding: top-8 win prob at the latest preds pull.
    elite = set()
    if preds_events:
        latest_eid = max(preds_events, key=lambda e: events.loc[e, "seq"])
        p = store.latest_preds(conn, latest_eid)
        elite = set(p.sort_values("win", ascending=False).head(8)["key"])

    out = {}
    for mgr, mine in picks.groupby("manager"):
        is_self = bool(mine["is_self"].iloc[0])
        mirror = chalk = chalk_n = form = n = 0
        used_before: set = set()
        for eid, rows in mine.sort_values("seq").groupby("event_id", sort=False):
            keys = set(rows["key"])
            seq = int(rows["seq"].iloc[0])
            n += 1
            if not is_self and self_by_event.get(eid) and \
                    keys & self_by_event[eid]:
                mirror += 1
            if keys & hot_keys(picks, seq):
                form += 1
            if eid in preds_events:
                preds = store.latest_preds(conn, eid)
                erow = events.loc[eid]
                b = ev_board(preds, _purse(erow), used_before,
                             has_cut=bool(erow["has_cut"]))
                if len(b) and b.iloc[0]["key"] in keys:
                    chalk += 1
                chalk_n += 1
            used_before |= keys
        hoard = len(elite - used_before) / len(elite) if elite else 0.0
        out[mgr] = Profile(
            manager=mgr,
            chalk_rate=chalk / chalk_n if chalk_n else 0.0,
            form_chase_rate=form / n if n else 0.0,
            mirror_rate=mirror / n if n else 0.0,
            hoard_score=hoard,
            events_measured=n)
    return out


def predicted_picks(conn, season: int, event_row, preds,
                    profiles: dict[str, Profile] | None = None,
                    extra_used: dict | None = None) -> dict:
    """manager -> [predicted golfer keys] for one event (majors: as many
    slots as picks_per_manager). Locked picks (already on the sheet for this
    event) are used verbatim; everyone else gets the profile-weighted argmax
    over their remaining board, then next-best for extra major slots.

    extra_used: manager -> keys already projected at OTHER remaining events,
    so a multi-week projection never spends a golfer twice (one-and-done)."""
    profiles = profiles or mine_profiles(conn, season)
    locked = store.event_picks(conn, season, event_row["event_id"])
    picks = store.picks_df(conn, season)
    hot = hot_keys(picks, int(event_row["seq"]))
    ineligible = store.ineligible_keys(conn, event_row, preds)
    slots = int(event_row["picks_per_manager"] or 1)
    out = {}
    for mgr in store.managers_list(conn):
        if locked.get(mgr):
            out[mgr] = locked[mgr]
            continue
        used = store.used_set(conn, season, mgr) | \
            (extra_used or {}).get(mgr, set())
        b = ev_board(preds, _purse(event_row), used,
                     has_cut=bool(event_row["has_cut"]),
                     ineligible=set(ineligible))
        their_board = [(r["exp"], r["key"], r["key"] in hot)
                       for _, r in b.head(12).iterrows()]
        prof = profiles.get(mgr, Profile(manager=mgr))
        first = predict_pick(prof, their_board)
        if first is None:
            out[mgr] = []
            continue
        lineup = [first]
        for _, key, _ in their_board:      # extra major slots: next best EV
            if len(lineup) >= slots:
                break
            if key not in lineup:
                lineup.append(key)
        out[mgr] = lineup
    return out
