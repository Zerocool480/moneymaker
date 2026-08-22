import numpy as np
from moneymaker.simulate import strokes_final_round, finish_distribution

def test_strokes_leader_favored_and_payouts_conserve():
    pos = {"leader": -12, "chaser": -8, "packA": -6, "packB": -4}
    wp = {"leader": .02, "chaser": .015, "packA": .02, "packB": .01}
    pay, tot, players = strokes_final_round(pos, wp, 20e6, n=20000, seed=7)
    win_leader = np.mean(tot[:, 0] == tot.min(axis=1))
    assert win_leader > 0.5  # 4 ahead with 18 to play
    dist, passes, fin = finish_distribution(
        pay["chaser"], {"L": pay["leader"] + 0}, always_ahead=0)
    assert abs(sum(dist.values()) - 1) < 1e-6
