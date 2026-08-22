"""Whole-season assignment: one golfer per remaining slot, all distinct,
max total EV. Constraints per ALGORITHMS s6."""
import itertools

def solve(per_event_boards: dict, top_k: int = 8, constraint=None):
    """per_event_boards: event -> list[(ev, key)] sorted desc.
    constraint: optional fn(assignment_dict) -> bool. Brute force over top-k."""
    events = list(per_event_boards)
    pools = [per_event_boards[e][:top_k] for e in events]
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
