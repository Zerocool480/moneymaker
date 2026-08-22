"""Regression tests for the ALGORITHMS s4 correctness rules."""
import numpy as np
import pandas as pd

from moneymaker.race import sensitivity_band, simulate_event_payouts, simulate_race

PURSE = 10e6


def curves(rows):
    return pd.DataFrame(rows, columns=["key", "win", "top_5", "top_10",
                                       "top_20", "make_cut", "amateur"])


TWO_STARS = curves([("x", .40, .55, .65, .75, .90, False),
                    ("y", .40, .55, .65, .75, .90, False)])


def test_exclusive_champion_one_winner_per_trial():
    rng = np.random.default_rng(3)
    pays = simulate_event_payouts(rng, TWO_STARS, ["x", "y"], PURSE, True,
                                  n=40_000)
    wx = pays["x"] == .18 * PURSE
    wy = pays["y"] == .18 * PURSE
    assert not (wx & wy).any()          # champion is exclusive
    assert abs(wx.mean() - .40) < .01   # true win marginals preserved
    assert abs(wy.mean() - .40) < .01


def test_runner_up_true_solo2_marginals():
    # ALGORITHMS s4: forcing a larger share once inflated threats by 3 pts.
    c = curves([("x", .10, .30, .40, .55, .85, False),
                ("y", .05, .20, .30, .45, .80, False)])
    rng = np.random.default_rng(4)
    pays = simulate_event_payouts(rng, c, ["x", "y"], PURSE, True, n=200_000)
    solo2_x = (.30 - .10) * 0.30
    solo2_y = (.20 - .05) * 0.30
    assert abs((pays["x"] == .109 * PURSE).mean() - solo2_x) < .008
    assert abs((pays["y"] == .109 * PURSE).mean() - solo2_y) < .008
    # runner-up is exclusive too
    assert not ((pays["x"] == .109 * PURSE) & (pays["y"] == .109 * PURSE)).any()


def test_amateur_pays_zero_but_blocks_the_win():
    c = curves([("am", .50, .60, .70, .80, .95, True),
                ("pro", .10, .30, .45, .60, .90, False)])
    rng = np.random.default_rng(5)
    pays = simulate_event_payouts(rng, c, ["am", "pro"], PURSE, True, n=30_000)
    assert pays["am"].max() == 0.0                    # amateurs cash $0
    assert abs((pays["pro"] == .18 * PURSE).mean() - .10) < .01  # win NOT
    # redistributed: the amateur still occupies the champion slot


def test_mirror_picks_cancel_exactly():
    plans = {"E": {"me": ["x"], "mirror": ["x"], "other": ["y"]}}
    res = simulate_race({"me": 100.0, "mirror": 100.0, "other": 0.0},
                        plans, {"E": TWO_STARS}, {"E": PURSE}, {"E": True},
                        "me", n=20_000, seed=6)
    assert res["passes"]["mirror"] == 0.0
    assert np.array_equal(res["totals"]["me"], res["totals"]["mirror"])


def test_shared_golfer_threats_correlate():
    # The 2026 "Clark riders": two rivals on the same golfer pass together
    # or not at all — never independently.
    plans = {"E": {"me": ["safe"], "r1": ["star"], "r2": ["star"]}}
    c = curves([("star", .30, .45, .55, .65, .85, False),
                ("safe", .0, .01, .02, .05, .50, False)])
    res = simulate_race({"me": 1e6, "r1": 0.0, "r2": 0.0}, plans, {"E": c},
                        {"E": PURSE}, {"E": True}, "me", n=20_000, seed=7)
    p1, p2 = res["passes"]["r1"], res["passes"]["r2"]
    both = float((np.array(res["totals"]["r1"] > res["totals"]["me"]) &
                  np.array(res["totals"]["r2"] > res["totals"]["me"])).mean())
    assert p1 == p2
    assert abs(both - p1) < 1e-12       # perfectly correlated, not p1*p2
    assert 0.05 < p1 < 0.95             # threat is real in this setup


def test_race_multi_event_accumulates_and_ranks():
    plans = {"E1": {"me": ["x"], "r": ["y"]},
             "E2": {"me": ["a"], "r": ["b"]}}
    c2 = curves([("a", .10, .25, .35, .50, .85, False),
                 ("b", .10, .25, .35, .50, .85, False)])
    res = simulate_race({"me": 0.0, "r": 0.0}, plans,
                        {"E1": TWO_STARS, "E2": c2},
                        {"E1": PURSE, "E2": PURSE}, {"E1": True, "E2": True},
                        "me", n=10_000, seed=8)
    assert abs(sum(res["dist"].values()) - 1) < 1e-9
    assert res["ev_added"]["me"] > 0
    assert 0 < res["passes"]["r"] < 1


def test_sensitivity_band_brackets_base():
    plans = {"E": {"me": ["x"], "r": ["y"]}}
    band = sensitivity_band({"me": 1e6, "r": 0.0}, plans, {"E": TWO_STARS},
                            {"E": PURSE}, {"E": True}, "me",
                            metric="p_first", n=8_000, key_rival="r")
    lo, hi = band["band"]
    assert lo <= band["base"] <= hi
    assert {"splits_low", "splits_high", "rival_win_up",
            "rival_win_down"} <= set(band)
    # a 50% win-prob rival haircut cannot make things worse for me
    assert band["rival_win_down"] >= band["rival_win_up"] - 1e-9
