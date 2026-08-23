from conftest import SEASON

from moneymaker import opponents as opp
from moneymaker import store


def test_predict_pick_chalk_by_default():
    prof = opp.Profile(manager="r", form_chase_rate=0.1)
    board = [(100.0, "top", False), (95.0, "hot", True)]
    assert opp.predict_pick(prof, board) == "top"


def test_predict_pick_form_chaser_takes_hot_name_within_15pct():
    prof = opp.Profile(manager="r", form_chase_rate=0.6)
    board = [(100.0, "top", False), (90.0, "hot", True)]
    assert opp.predict_pick(prof, board) == "hot"
    # outside the 15% window even a chaser stays chalk
    board = [(100.0, "top", False), (80.0, "hot", True)]
    assert opp.predict_pick(prof, board) == "top"
    assert opp.predict_pick(prof, []) is None


def test_mirror_rate_mined_from_history(db_mid):
    profs = opp.mine_profiles(db_mid, SEASON)
    assert profs["Mirror Max"].mirror_rate == 1.0
    assert profs["Rival Two"].mirror_rate == 0.0
    assert profs["Jay Doura"].mirror_rate == 0.0   # self never counts mirrors
    assert profs["Mirror Max"].events_measured == 2


def test_predicted_picks_locked_verbatim_else_projected(db_mid):
    pga = store.resolve_event(db_mid, SEASON, "pga championship")
    preds = store.latest_preds(db_mid, pga["event_id"])
    pred = opp.predicted_picks(db_mid, SEASON, pga, preds)
    assert pred["Rival One"] == ["rory mcilroy", "jon rahm"]  # locked verbatim
    # projections fill BOTH major slots: chalk + next-best EV
    assert pred["Jay Doura"] == ["scottie scheffler", "rory mcilroy"]
    # projections respect the one-and-done used set
    used = store.used_set(db_mid, SEASON, "Rival Two")
    assert not (set(pred["Rival Two"]) & used)
    assert len(set(pred["Rival Two"])) == 2               # slots are distinct


def test_predicted_picks_respect_liv_rule(db_mid):
    trav = store.resolve_event(db_mid, SEASON, "travelers")
    preds = store.latest_preds(db_mid, trav["event_id"])
    pred = opp.predicted_picks(db_mid, SEASON, trav, preds)
    assert all("jon rahm" not in lineup for lineup in pred.values())
    assert all(len(lineup) == 1 for lineup in pred.values())  # not a major


def test_dead_hoard_flagged_when_no_major_remains(db_final):
    # The hoarded-Rahm-expired-at-the-BMW intel: season's majors settled,
    # unspent LIV names are dead money, flagged and out of hoard_score.
    profs = opp.mine_profiles(db_final, SEASON)
    assert profs["Jay Doura"].dead_hoard == ("jon rahm", "keegan bradley")
    # Rival One actually SPENT Rahm at the PGA — only Bradley is dead there.
    assert profs["Rival One"].dead_hoard == ("keegan bradley",)


def test_no_dead_hoard_while_a_major_remains(db_mid):
    profs = opp.mine_profiles(db_mid, SEASON)      # PGA still unsettled
    assert all(p.dead_hoard == () for p in profs.values())


def test_money_cushion_uses_first_unpaid_seat():
    # The 2026 dashboard bug the design critics caught: Jay 5th of 86,
    # cushion must be measured to 7th (first unpaid), NOT 6th (still paid).
    st = {"Snyder": 18_544_802, "Rappaport": 15_314_887, "Livote": 14_283_254,
          "LeMaire": 14_171_479, "Jay": 13_694_339, "Aadal": 13_016_747,
          "White": 12_637_620, "Santana": 12_626_827}
    cushion, ref_rank, ref_name = opp.money_cushion(st, "Jay", 6)
    assert cushion == 13_694_339 - 12_637_620 == 1_056_719
    assert (ref_rank, ref_name) == (7, "White")
    # out of the money: deficit to the LAST paid seat
    cushion, ref_rank, ref_name = opp.money_cushion(st, "White", 6)
    assert cushion == 12_637_620 - 13_016_747
    assert (ref_rank, ref_name) == (6, "Aadal")


def test_posture_classification():
    overall = {"A": 5_000_000, "B": 4_000_000, "C": 3_900_000, "D": 3_800_000,
               "E": 3_700_000, "F": 3_600_000, "G": 3_100_000, "H": 500_000}
    segment = dict(overall)   # same shape on the segment board
    # F holds the last overall money spot -> leading
    assert opp.posture_for("F", overall, segment, 40e6, 10e6) == "leading"
    # G is $500k off the money with $40M left -> chasing
    assert opp.posture_for("G", overall, segment, 40e6, 10e6) == "trailing"
    # H is $3.1M back with only $4M of purse left -> longshot
    assert opp.posture_for("H", overall, segment, 4e6, 2e6) == "longshot"
    # unknown manager on both boards -> longshot (no evidence of contention)
    assert opp.posture_for("Z", {}, {}, 40e6, 10e6) == "longshot"


BOARD = [  # (exp, key, hot, win, floor)
    (100.0, "steady", False, 0.01, 90.0),   # top EV, all floor
    (95.0, "boom", False, 0.15, 20.0),      # win-heavy
    (60.0, "hot mid", True, 0.05, 40.0),    # last week's winner
]


def test_rank_candidates_baseline_matches_legacy_heuristic():
    chalk = opp.Profile(manager="r", form_chase_rate=0.1)
    chaser = opp.Profile(manager="r", form_chase_rate=0.6)
    assert opp.rank_candidates(chalk, BOARD, None)[0] == "steady"
    legacy = opp.predict_pick(chaser, [(e, k, h) for e, k, h, _, _ in BOARD])
    assert opp.rank_candidates(chaser, BOARD, None)[0] == legacy


def test_rank_candidates_postures_reorder():
    prof = opp.Profile(manager="r")
    assert opp.rank_candidates(prof, BOARD, "leading")[0] == "steady"
    assert opp.rank_candidates(prof, BOARD, "trailing")[0] == "boom"
    assert opp.rank_candidates(prof, BOARD, "longshot")[0] == "boom"
    # longshot ranks purely by win%: steady (1%) falls below hot mid (5%)
    ranked = opp.rank_candidates(prof, BOARD, "longshot")
    assert ranked.index("steady") > ranked.index("hot mid")
