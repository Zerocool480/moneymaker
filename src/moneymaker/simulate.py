"""Final-round strokes simulator + finish distribution helpers.
Correctness rules in ALGORITHMS s5: integer strokes, tie-averaged ladders.
The bucket race Monte Carlo (s4: shared draws, exclusive champion) lives in
race.py — each event is simulated ONCE and every manager holding a golfer
reads the same payout array, which is the shared-draw invariant."""
import numpy as np
from .payouts import ladder

def strokes_final_round(pos54: dict, winprob: dict, purse: float,
                        n=400_000, sd=2.85, tails="t", seed=1):
    """pos54: key -> to-par after 54; winprob: key -> pre-tournament win prob.
    Returns (pay: key->array, totals array, players list)."""
    rng = np.random.default_rng(seed)
    players = list(pos54); P = len(players)
    lw = np.array([np.log(max(winprob[p], 1e-6)) for p in players])
    sg = 0.62 * (lw - lw.mean())
    eps = (rng.standard_t(8, size=(n, P)) * sd / np.sqrt(8/6)) if tails == "t" \
          else rng.normal(0, sd, (n, P))
    r4 = np.rint(-sg + eps).astype(np.int32)
    tot = np.array([pos54[p] for p in players], np.int32)[None, :] + r4
    L = ladder(purse, P); cumL = np.concatenate([[0], np.cumsum(L)])
    order = np.argsort(tot, axis=1, kind="stable")
    S = np.take_along_axis(tot, order, axis=1)
    C = np.ones((n, P), bool); C[:, 1:] = S[:, 1:] != S[:, :-1]
    idx = np.arange(P)[None, :]
    start = np.maximum.accumulate(np.where(C, idx, 0), axis=1)
    Cn = np.concatenate([C[:, 1:], np.ones((n, 1), bool)], axis=1)
    endr = np.minimum.accumulate(np.where(Cn, idx, P-1)[:, ::-1], axis=1)[:, ::-1]
    gm = (cumL[endr + 1] - cumL[start]) / (endr - start + 1)
    pay = np.empty((n, P)); np.put_along_axis(pay, order, gm, axis=1)
    return {p: pay[:, i] for i, p in enumerate(players)}, tot, players

def finish_distribution(self_total, rival_totals: dict, always_ahead: int = 0):
    """rival_totals: name -> array of (their haul + gap-to-self).
    Returns (finish-position probs, per-rival P(pass), finish array)."""
    n = len(self_total)
    ahead = np.full(n, always_ahead, np.int16)
    passes = {}
    for name, v in rival_totals.items():
        a = v > self_total
        passes[name] = float(a.mean()); ahead += a.astype(np.int16)
    finish = ahead + 1
    top = len(rival_totals) + always_ahead + 1   # full support, sums to 1
    dist = {k: float((finish == k).mean()) for k in range(1, top + 1)}
    return dist, passes, finish
