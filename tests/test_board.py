import pandas as pd

from conftest import SEASON

from moneymaker import store
from moneymaker.datagolf import load_preds_csv
from moneymaker.ev import board


def test_amateur_visible_but_zero_ev(pga_csv):
    d = load_preds_csv(pga_csv)
    b = board(d, 19e6, used=set())
    row = b[b["key"] == "jackson koivun"]
    assert len(row) == 1                       # loud, never hidden
    assert row["exp"].iloc[0] == 0.0           # earns $0 while amateur
    assert "AMATEUR $0" in row["flags"].iloc[0]
    assert row.index[0] > 5                    # $0 EV sinks him down the board


def test_koivun_ranks_after_turning_pro(db_mid):
    # The ISCO save: once the flip is recorded, he ranks purely on EV.
    trav = store.resolve_event(db_mid, SEASON, "travelers")
    preds = store.latest_preds(db_mid, trav["event_id"])
    b = board(preds, 20e6, used=set(), has_cut=False)
    row = b[b["key"] == "jackson koivun"]
    assert row["exp"].iloc[0] > 0
    assert "AMATEUR" not in row["flags"].iloc[0]


def test_used_and_ineligible_excluded(pga_csv):
    d = load_preds_csv(pga_csv)
    b = board(d, 19e6, used={"scottie scheffler"}, ineligible={"jon rahm"})
    assert "scottie scheffler" not in set(b["key"])
    assert "jon rahm" not in set(b["key"])


def test_reserved_flagged_not_hidden(pga_csv):
    d = load_preds_csv(pga_csv)
    b = board(d, 19e6, used=set(), reserved={"scottie scheffler"})
    top = b.iloc[0]
    assert top["key"] == "scottie scheffler"
    assert top["reserved"]
    assert "RESERVED" in top["flags"]


def test_trailing_posture_blends_win(pga_csv):
    d = load_preds_csv(pga_csv)
    neutral = board(d, 19e6, used=set())
    trailing = board(d, 19e6, used=set(), posture="trailing")
    # Same pool, but trailing must weight win% harder than raw EV.
    assert list(trailing["score"]) != list(neutral["score"])
    top = trailing.iloc[0]
    assert top["score"] == top["exp"] * (1 + 8.0 * top["win"])


def test_floor_below_exp_and_no_cut_floor_higher(pga_csv):
    d = load_preds_csv(pga_csv)
    b_cut = board(d, 20e6, used=set(), has_cut=True)
    b_nocut = board(d, 20e6, used=set(), has_cut=False)
    pro = b_cut[b_cut["key"] == "scottie scheffler"].iloc[0]
    assert 0 < pro["floor"] < pro["exp"]
    # no-cut guarantees the check: EV strictly higher without an MC bucket
    assert b_nocut[b_nocut["key"] == "rory mcilroy"]["exp"].iloc[0] > \
        b_cut[b_cut["key"] == "rory mcilroy"]["exp"].iloc[0]


def test_board_handles_missing_flag_columns():
    d = pd.DataFrame([{"player_name": "A, B", "key": "b a", "win": .1,
                       "top_5": .2, "top_10": .3, "top_20": .4,
                       "make_cut": .8}])
    b = board(d, 1e7, used=set())
    assert b["flags"].iloc[0] == ""
