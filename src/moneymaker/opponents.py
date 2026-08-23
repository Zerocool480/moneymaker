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
    dead_hoard: tuple = ()         # unspent LIV names with no major left


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


# ---- posture-aware prediction (step 1 of the rival-modeling upgrade) ----
# A rival's race position shapes their pick: in the money -> protect (floor),
# within reach -> chase (win%-blend), out of it -> moonshot (pure win%).
# Scoring reuses the SAME posture math the proven board uses (ev.board),
# so nothing here is new math — only new conditioning. Walk-forward
# evaluated against 2026 via `mm eval-opponents` before becoming a default.

SEGMENT_PAID, OVERALL_PAID = 3, 6   # money lines (2026 prize structure)
REACH = 0.11                         # ~runner-up share of remaining purse


def money_gap(standings: dict, mgr: str, paid: int) -> float | None:
    """Dollars to the LAST paid position (<=0 means in the money by that
    cushion). None when the manager or the board is unknown.
    NOTE: this is the POSTURE quantity (how far from contention). For the
    user-facing "cushion above the line", use money_cushion — being passed
    by another paid manager costs nothing; the line that matters is the
    first UNPAID seat."""
    if not standings or mgr not in standings:
        return None
    totals = sorted(standings.values(), reverse=True)
    line = totals[min(paid, len(totals)) - 1]
    return line - standings[mgr]


def money_cushion(standings: dict, mgr: str, paid: int):
    """(cushion_dollars, ref_rank, ref_name) — the DISPLAY semantics of the
    money line. In the money: cushion (>0) over the first UNPAID seat
    (rank paid+1), named. Out of the money: deficit (<0) to the LAST PAID
    seat, named. None when unknowable."""
    if not standings or mgr not in standings:
        return None
    ranked = sorted(standings.items(), key=lambda kv: -kv[1])
    names = [m for m, _ in ranked]
    my_rank = names.index(mgr) + 1
    if my_rank <= paid:
        ref_idx = paid            # first unpaid seat (0-based index paid)
        if ref_idx >= len(ranked):
            return (standings[mgr], my_rank, None)   # everyone is paid
    else:
        ref_idx = paid - 1        # last paid seat
    ref_name, ref_total = ranked[ref_idx]
    return (standings[mgr] - ref_total, ref_idx + 1, ref_name)


def posture_for(mgr: str, overall: dict, segment: dict,
                purse_left_overall: float, purse_left_segment: float) -> str:
    """'leading' | 'trailing' | 'longshot'. The overall race dominates
    (prizes >> segment); the segment race governs when overall is gone."""
    for standings, paid, purse_left in (
            (overall, OVERALL_PAID, purse_left_overall),
            (segment, SEGMENT_PAID, purse_left_segment)):
        gap = money_gap(standings, mgr, paid)
        if gap is None:
            continue
        if gap <= 0:
            return "leading"
        if gap <= REACH * purse_left:
            return "trailing"
    return "longshot"


def rank_candidates(profile: Profile, their_board, posture: str | None = None):
    """Ordered golfer keys, most likely first. their_board rows:
    (exp, key, hot, win, floor); posture None reproduces the validated
    baseline exactly (EV order + form-chaser hot override)."""
    if not their_board:
        return []
    if posture == "leading":
        score = lambda r: (r[0] + r[4]) / 2          # protect: EV/floor blend
    elif posture == "trailing":
        score = lambda r: r[0] * (1 + 8.0 * r[3])    # chase: win%-blend
    elif posture == "longshot":
        score = lambda r: (r[3], r[0])               # moonshot: pure win%
    else:
        score = lambda r: r[0]                       # baseline: raw EV
    ranked = sorted(their_board, key=score, reverse=True)
    keys = [r[1] for r in ranked]
    if profile.form_chase_rate > 0.4:
        top_score = score(ranked[0])
        for r in ranked[:5]:
            if r[2] and _ge_85pct(score(r), top_score):
                keys.remove(r[1])
                keys.insert(0, r[1])
                break
    return keys


def _ge_85pct(s, top) -> bool:
    if isinstance(s, tuple):                          # longshot tuple scores
        s, top = s[0], top[0]
    return s >= top * 0.85


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

    # Dead hoards (ALGORITHMS s8): an unspent LIV name is dead money once no
    # major remains among unsettled events — flag it, don't count it as held
    # firepower.
    settled = {int(r[0]) for r in conn.execute(
        "SELECT DISTINCT event_id FROM picks WHERE season=? AND "
        "earnings IS NOT NULL", (season,))}
    majors_left = any(e for e in events.itertuples()
                      if e.field_type == "major" and e.Index not in settled)
    liv = store.liv_keys(conn)

    preds_cache = {eid: store.latest_preds(conn, eid) for eid in preds_events}
    hot_cache: dict[int, set] = {}
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
            if seq not in hot_cache:
                hot_cache[seq] = hot_keys(picks, seq)
            if keys & hot_cache[seq]:
                form += 1
            if eid in preds_events:
                preds = preds_cache[eid]
                erow = events.loc[eid]
                inel = store.ineligible_keys(conn, erow, preds)
                b = ev_board(preds, _purse(erow), used_before,
                             has_cut=bool(erow["has_cut"]),
                             ineligible=set(inel))
                if len(b) and b.iloc[0]["key"] in keys:
                    chalk += 1
                chalk_n += 1
            used_before |= keys
        dead = tuple(sorted(liv - used_before)) if not majors_left else ()
        live_elite = elite - set(dead)
        hoard = (len(live_elite - used_before) / len(live_elite)
                 if live_elite else 0.0)
        out[mgr] = Profile(
            manager=mgr,
            chalk_rate=chalk / chalk_n if chalk_n else 0.0,
            form_chase_rate=form / n if n else 0.0,
            mirror_rate=mirror / n if n else 0.0,
            hoard_score=hoard,
            events_measured=n,
            dead_hoard=dead)
    return out


def pick_distributions(conn, season: int, event_row, preds, beta,
                       profiles: dict[str, Profile] | None = None,
                       extra_used: dict | None = None,
                       top_k: int = 8) -> dict:
    """manager -> (lineups, probs): a calibrated distribution over each
    unlocked manager's plausible lineups for one event, for the race sim to
    SAMPLE (choice.py model). Locked managers get their lineup at prob 1.
    Majors: each candidate primary pick is completed with next-best EV."""
    from . import choice
    profiles = profiles or mine_profiles(conn, season)
    locked = store.event_picks(conn, season, event_row["event_id"])
    picks = store.picks_df(conn, season)
    hot = hot_keys(picks, int(event_row["seq"]))
    pop = choice.popularity(conn, season, int(event_row["seq"]))
    ineligible = store.ineligible_keys(conn, event_row, preds)
    slots = int(event_row["picks_per_manager"] or 1)
    out = {}
    for mgr in store.managers_list(conn):
        already = list(locked.get(mgr, []))
        if len(already) >= slots:
            out[mgr] = ([already], [1.0])
            continue
        used = store.used_set(conn, season, mgr) | set(already) | \
            (extra_used or {}).get(mgr, set())
        b = ev_board(preds, _purse(event_row), used,
                     has_cut=bool(event_row["has_cut"]),
                     ineligible=set(ineligible)).head(30)
        if not len(b):
            continue
        X = choice.feature_matrix(b, hot, profiles.get(mgr), pop)
        p = choice.predict_proba(beta, X)
        order = p.argsort()[::-1][:top_k]
        keys = list(b["key"])
        probs = p[order]
        probs = probs / probs.sum()
        lineups = []
        for i in order:
            lineup = list(already) + [keys[i]]
            for k in keys:                   # fill extra major slots
                if len(lineup) >= slots:
                    break
                if k not in lineup:
                    lineup.append(k)
            lineups.append(lineup)
        out[mgr] = (lineups, list(probs))
    return out


def purse_left(conn, season: int, from_seq: int, segment: int | None = None,
               default_purse: float = 1e7) -> float:
    """Total purse still on the table from from_seq onward (majors with no
    parsed purse count at the default)."""
    rows = conn.execute(
        "SELECT purse, picks_per_manager FROM events WHERE season=? AND "
        "seq>=? AND (? IS NULL OR segment=?)",
        (season, from_seq, segment, segment)).fetchall()
    return sum((r["purse"] or default_purse) for r in rows) or default_purse


def predicted_picks(conn, season: int, event_row, preds,
                    profiles: dict[str, Profile] | None = None,
                    extra_used: dict | None = None,
                    posture_aware: bool = False) -> dict:
    """manager -> [predicted golfer keys] for one event (majors: as many
    slots as picks_per_manager). Locked picks (already on the sheet for this
    event) are used verbatim; everyone else gets the profile-weighted argmax
    over their remaining board, then next-best for extra major slots.

    posture_aware conditions each rival's ranking on their race position.
    Default OFF: the 2026 walk-forward eval (mm eval-opponents) scored it a
    statistical wash vs the validated baseline (23.3% vs 23.2% top-1 over
    850 rival-weeks; only the endgame BMW week improved). Re-evaluate with
    2027's fuller preds archive before flipping this on.
    extra_used: manager -> keys already projected at OTHER remaining events,
    so a multi-week projection never spends a golfer twice (one-and-done)."""
    profiles = profiles or mine_profiles(conn, season)
    locked = store.event_picks(conn, season, event_row["event_id"])
    picks = store.picks_df(conn, season)
    hot = hot_keys(picks, int(event_row["seq"]))
    ineligible = store.ineligible_keys(conn, event_row, preds)
    slots = int(event_row["picks_per_manager"] or 1)
    if posture_aware:
        overall = store.latest_standings(conn, season, "overall")
        seg_board = store.latest_standings(
            conn, season, f"segment{event_row['segment']}") \
            if event_row["segment"] else {}
        pl_overall = purse_left(conn, season, int(event_row["seq"]))
        pl_segment = purse_left(conn, season, int(event_row["seq"]),
                                int(event_row["segment"] or 0) or None)
    out = {}
    for mgr in store.managers_list(conn):
        already = list(locked.get(mgr, []))
        if len(already) >= slots:
            out[mgr] = already
            continue
        used = store.used_set(conn, season, mgr) | set(already) | \
            (extra_used or {}).get(mgr, set())
        b = ev_board(preds, _purse(event_row), used,
                     has_cut=bool(event_row["has_cut"]),
                     ineligible=set(ineligible))
        their_board = [(r["exp"], r["key"], r["key"] in hot, r["win"],
                        r["floor"]) for _, r in b.head(12).iterrows()]
        prof = profiles.get(mgr, Profile(manager=mgr))
        posture = posture_for(mgr, overall, seg_board, pl_overall,
                              pl_segment) if posture_aware else None
        ranked = rank_candidates(prof, their_board, posture)
        lineup = list(already)             # partial major lock: keep, extend
        for key in ranked:                 # top slot + next-best extras
            if len(lineup) >= slots:
                break
            if key not in lineup:
                lineup.append(key)
        out[mgr] = lineup
    return out
