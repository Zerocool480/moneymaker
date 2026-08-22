"""Season race Monte Carlo — the F5 engine.

Correctness rules from ALGORITHMS s4, all enforced here:
- SHARED DRAWS: one outcome per (golfer, event) per trial. Every event is
  simulated once and every manager holding that golfer reads the same payout
  array, so mirror picks cancel and same-golfer threats correlate.
- EXCLUSIVE CHAMPION: per event, ONE categorical winner draw over the tracked
  win probabilities plus a rest-of-field bucket; non-winners fall to
  conditional (no-W) curves. Runner-up drawn likewise with TRUE solo-2nd
  marginals (regression-tested — forcing a larger share once inflated
  threats by 3 points).
- Amateurs earn $0 whatever the draw says (they can still "win" the event
  and deny the purse to everyone else's pick).
"""
import numpy as np
import pandas as pd

from .ev import SPLIT2, SPLIT2140, bucket_probs
from .payouts import BUCKETS, BUCKET_ORDER

_W, _RU = BUCKET_ORDER.index("W"), BUCKET_ORDER.index("2")


def _curve_row(curves, key):
    r = curves.loc[curves["key"] == key]
    return None if r.empty else r.iloc[0]


def simulate_event_payouts(rng, curves, tracked: list[str], purse: float,
                           has_cut: bool, n: int,
                           split2=SPLIT2, split2140=SPLIT2140,
                           win_scale: dict | None = None) -> dict:
    """One event, simulated once for everyone. Returns key -> (n,) payouts.

    curves: DataFrame with key/win/top_5/top_10/top_20/make_cut (+ amateur).
    tracked: golfer keys anyone in the league holds for this event.
    win_scale: optional key -> multiplier on win prob (sensitivity only).
    """
    rows, keys = [], []
    for k in tracked:
        r = _curve_row(curves, k)
        if r is not None:
            rows.append(r); keys.append(k)
    T = len(keys)
    if T == 0:
        return {}

    wins = np.array([float(r["win"]) for r in rows])
    if win_scale:
        for i, k in enumerate(keys):
            wins[i] *= win_scale.get(k, 1.0)
    wins = np.clip(wins, 0.0, 1.0)
    solo2 = np.array([max(0.0, (float(r["top_5"]) - float(r["win"]))) * split2
                      for r in rows])
    amateur = np.array([bool(a) if pd.notna(a) else False
                        for a in (r.get("amateur", False) for r in rows)])

    # Winner: exclusive categorical over tracked wins + rest-of-field mass.
    pw = np.append(wins, max(0.0, 1.0 - wins.sum()))
    pw = pw / pw.sum()
    winner = rng.choice(T + 1, size=n, p=pw)

    # Runner-up: TRUE solo-2nd marginals + rest-of-field; conditional redraw
    # where it collides with the winner (rest-of-field never collides — it
    # stands for many different players).
    p2 = np.append(solo2, max(0.0, 1.0 - solo2.sum()))
    p2 = p2 / p2.sum()
    runner = rng.choice(T + 1, size=n, p=p2)
    for _ in range(10):
        clash = (runner == winner) & (runner < T)
        if not clash.any():
            break
        runner[clash] = rng.choice(T + 1, size=int(clash.sum()), p=p2)
    else:
        runner[(runner == winner) & (runner < T)] = T

    lo = np.array([BUCKETS[b][0] for b in BUCKET_ORDER]) * purse
    hi = np.array([BUCKETS[b][1] for b in BUCKET_ORDER]) * purse
    out = {}
    for i, (k, r) in enumerate(zip(keys, rows)):
        p = bucket_probs(float(r["win"]), float(r["top_5"]), float(r["top_10"]),
                         float(r["top_20"]), float(r["make_cut"]), has_cut,
                         split2=split2, split2140=split2140)
        p = p.copy()
        p[_W] = 0.0; p[_RU] = 0.0  # conditional no-W (and no-solo-2nd) curve
        s = p.sum()
        if s <= 0:
            p = np.zeros_like(p); p[-1] = 1.0  # degenerate row -> MC
        else:
            p = p / s
        idx = rng.choice(len(BUCKET_ORDER), size=n, p=p)
        pay = lo[idx] + rng.random(n) * (hi[idx] - lo[idx])
        pay[winner == i] = BUCKETS["W"][0] * purse
        pay[runner == i] = BUCKETS["2"][0] * purse
        if amateur[i]:
            pay = np.zeros(n)  # amateurs cash $0 regardless of finish
        out[k] = pay
    return out


def simulate_race(standings: dict, plans: dict, event_curves: dict,
                  purses: dict, has_cut: dict, self_name: str,
                  n: int = 100_000, seed: int = 1,
                  split2=SPLIT2, split2140=SPLIT2140,
                  win_scale: dict | None = None) -> dict:
    """Race across remaining events on one board.

    standings: manager -> current $ total (the board being simulated).
    plans: event -> {manager: [golfer keys]} (locked picks or projections).
    event_curves / purses / has_cut: per-event inputs keyed like plans.
    Returns finish distribution for self, per-rival P(pass), EV added, and
    the raw totals matrix for downstream conditioning.
    """
    rng = np.random.default_rng(seed)
    managers = list(standings)
    totals = {m: np.full(n, float(standings[m])) for m in managers}
    ev_added = {m: 0.0 for m in managers}

    for ev_key, mgr_picks in plans.items():
        curves = event_curves[ev_key]
        tracked = sorted({k for picks in mgr_picks.values() for k in picks})
        pays = simulate_event_payouts(
            rng, curves, tracked, purses[ev_key], has_cut[ev_key], n,
            split2=split2, split2140=split2140, win_scale=win_scale)
        for m, picks in mgr_picks.items():
            if m not in totals:
                continue
            for k in picks:
                if k in pays:
                    totals[m] += pays[k]
                    ev_added[m] += float(pays[k].mean())

    self_total = totals[self_name]
    rivals = {m: t for m, t in totals.items() if m != self_name}
    ahead = np.zeros(n, np.int32)
    passes = {}
    for m, t in rivals.items():
        beat = t > self_total
        passes[m] = float(beat.mean())
        ahead += beat.astype(np.int32)
    finish = ahead + 1
    dist = {k: float((finish == k).mean())
            for k in range(1, min(len(managers), 12) + 1)}
    return {"dist": dist, "passes": passes, "finish": finish,
            "ev_added": ev_added, "totals": totals,
            "p_first": float((finish == 1).mean()),
            "p_top3": float((finish <= 3).mean()),
            "p_top6": float((finish <= 6).mean())}


def sensitivity_band(standings, plans, event_curves, purses, has_cut,
                     self_name, metric: str = "p_first",
                     n: int = 30_000, seed: int = 2,
                     key_rival: str | None = None) -> dict:
    """ALGORITHMS s4 band: bucket splits +-0.05 and key-rival win +-50%.
    Returns {scenario: metric value} including the base case."""
    def run(split2=SPLIT2, split2140=SPLIT2140, win_scale=None):
        return simulate_race(standings, plans, event_curves, purses, has_cut,
                             self_name, n=n, seed=seed, split2=split2,
                             split2140=split2140, win_scale=win_scale)[metric]

    out = {"base": run(),
           "splits_low": run(split2=SPLIT2 - .05, split2140=SPLIT2140 - .05),
           "splits_high": run(split2=SPLIT2 + .05, split2140=SPLIT2140 + .05)}
    if key_rival:
        rival_keys = {k for ev in plans.values()
                      for k in ev.get(key_rival, [])}
        out["rival_win_up"] = run(win_scale={k: 1.5 for k in rival_keys})
        out["rival_win_down"] = run(win_scale={k: 0.5 for k in rival_keys})
    out["band"] = (min(out.values()), max(out.values()))
    return out
