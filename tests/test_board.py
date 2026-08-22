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


def test_trailing_posture_flips_to_the_win_play():
    # The Gotterup John Deere shape: a steady-EV name vs a lower-EV,
    # higher-win name — trailing MUST flip the board to the win play.
    d = pd.DataFrame([
        {"player_name": "Steady, Eddie", "key": "eddie steady",
         "win": .02, "top_5": .25, "top_10": .40, "top_20": .60,
         "make_cut": .95},
        {"player_name": "Boom, Bart", "key": "bart boom",
         "win": .11, "top_5": .18, "top_10": .22, "top_20": .28,
         "make_cut": .50},
    ])
    neutral = board(d, 1e7, used=set())
    trailing = board(d, 1e7, used=set(), posture="trailing")
    assert neutral.iloc[0]["key"] == "eddie steady"     # raw EV favors him
    assert trailing.iloc[0]["key"] == "bart boom"       # win%-blend flips it


def test_leading_posture_flips_to_the_floor_play():
    # Protecting a lead: boom-or-bust win equity loses to a steady casher
    # even at slightly lower raw EV (ALGORITHMS s3 "leading (EV/floor)").
    d = pd.DataFrame([
        {"player_name": "Boom, Bart", "key": "bart boom",
         "win": .16, "top_5": .17, "top_10": .18, "top_20": .20,
         "make_cut": .30},
        {"player_name": "Steady, Eddie", "key": "eddie steady",
         "win": .01, "top_5": .20, "top_10": .35, "top_20": .55,
         "make_cut": .90},
    ])
    neutral = board(d, 1e7, used=set())
    leading = board(d, 1e7, used=set(), posture="leading")
    assert neutral.iloc[0]["key"] == "bart boom"
    assert leading.iloc[0]["key"] == "eddie steady"


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
