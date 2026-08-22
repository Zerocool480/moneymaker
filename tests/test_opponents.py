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
    assert pred["Rival One"] == "rory mcilroy"        # locked on the sheet
    assert pred["Jay Doura"] == "scottie scheffler"   # projected chalk
    # projections respect the one-and-done used set
    assert pred["Rival Two"] not in store.used_set(db_mid, SEASON, "Rival Two")


def test_predicted_picks_respect_liv_rule(db_mid):
    trav = store.resolve_event(db_mid, SEASON, "travelers")
    preds = store.latest_preds(db_mid, trav["event_id"])
    pred = opp.predicted_picks(db_mid, SEASON, trav, preds)
    assert all(k != "jon rahm" for k in pred.values())
