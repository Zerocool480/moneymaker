"""Whole-season assignment: one golfer per remaining slot, all distinct,
max total EV. Constraints per ALGORITHMS s6 ("brute force top-k/event or
Hungarian"). Hungarian (scipy linear_sum_assignment) is the default — it
solves the full-season slate in milliseconds; brute force remains for small
problems with a custom constraint fn, which Hungarian cannot encode."""
import itertools

import numpy as np
from scipy.optimize import linear_sum_assignment

BRUTE_CAP = 5_000_000


def _brute(per_event_boards, top_k, constraint):
    events = list(per_event_boards)
    pools = [per_event_boards[e][:top_k] for e in events]
    if int(np.prod([max(len(p), 1) for p in pools])) > BRUTE_CAP:
        raise ValueError(
            f"brute force over {len(events)} slots exceeds {BRUTE_CAP:,} "
            "combinations — drop the custom constraint (Hungarian solves any "
            "size), pass fewer events, or lower top_k.")
    best = None
    for combo in itertools.product(*pools):
        keys = [c[1] for c in combo]
        if len(set(keys)) < len(keys):
            continue
        asg = dict(zip(events, keys))
        if constraint and not constraint(asg):
            continue
        tot = sum(c[0] for c in combo)
        if best is None or tot > best[0]:
            best = (tot, asg)
    return best


def _hungarian(per_event_boards, top_k):
    events = list(per_event_boards)
    pools = {e: per_event_boards[e][:top_k] for e in events}
    golfers = sorted({k for pool in pools.values() for _, k in pool})
    if len(golfers) < len(events):
        return None
    gi = {k: j for j, k in enumerate(golfers)}
    BIG = 1e15
    cost = np.full((len(events), len(golfers)), BIG)
    for i, e in enumerate(events):
        for ev, k in pools[e]:
            cost[i, gi[k]] = -float(ev)
    rows, cols = linear_sum_assignment(cost)
    if any(cost[i, j] >= BIG for i, j in zip(rows, cols)):
        return None                       # some slot got no eligible golfer
    asg = {events[i]: golfers[j] for i, j in zip(rows, cols)}
    tot = float(-cost[rows, cols].sum())
    return tot, asg


def solve(per_event_boards: dict, top_k: int = 8, constraint=None):
    """per_event_boards: event -> list[(ev, key)] sorted desc.
    constraint: optional fn(assignment_dict) -> bool (forces brute force).
    Returns (total_ev, {event: key}) or None if infeasible."""
    if constraint:
        return _brute(per_event_boards, top_k, constraint)
    return _hungarian(per_event_boards, top_k)
