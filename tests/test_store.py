import pytest
from conftest import SEASON

from moneymaker import store


def test_events_grouped_with_major_two_slots(db_mid):
    ev = store.events_df(db_mid, SEASON)
    assert len(ev) == 4
    pga = ev[ev["name"].str.contains("PGA")].iloc[0]
    assert pga["picks_per_manager"] == 2
    assert pga["field_type"] == "major"
    assert list(ev["segment"]) == [1, 1, 2, 2]
    assert list(ev["seq"]) == [0, 1, 2, 3]


def test_purse_parsed_from_header(db_mid):
    ev = store.events_df(db_mid, SEASON).set_index("name")
    assert ev.loc["Sony Open- $8.3M", "purse"] == pytest.approx(8.3e6)
    assert ev.loc["Travelers- $20M", "purse"] == 20e6


def test_wd_pick_still_consumes_golfer(db_mid):
    used = store.used_set(db_mid, SEASON, "Jay Doura")
    assert "collin morikawa" in used   # "(WD)" stripped, pick still burned
    assert "jj spaun" in used


def test_money_earned_settles_picks(db_mid):
    row = db_mid.execute(
        "SELECT p.earnings FROM picks p JOIN managers m ON m.manager_id="
        "p.manager_id JOIN golfers g ON g.golfer_id=p.golfer_id "
        "WHERE m.name='Rival Two' AND g.key='chris gotterup'").fetchone()
    assert row[0] == 1_584_000
    zero = db_mid.execute(
        "SELECT p.earnings FROM picks p JOIN managers m ON m.manager_id="
        "p.manager_id JOIN golfers g ON g.golfer_id=p.golfer_id "
        "WHERE m.name='Jay Doura' AND g.key='collin morikawa'").fetchone()
    assert zero[0] == 0  # WD week: settled at $0, not left NULL


def test_standings_snapshot(db_mid):
    st = store.latest_standings(db_mid, SEASON, "overall")
    assert st["Rival Two"] == 1_664_000
    assert st["Jay Doura"] == 40_000


def test_resolve_event_fragment_and_errors(db_mid):
    assert store.resolve_event(db_mid, SEASON, "travelers")["purse"] == 20e6
    try:
        store.resolve_event(db_mid, SEASON, "s")  # matches several
        assert False, "expected ambiguity error"
    except KeyError as e:
        assert "ambiguous" in str(e)
    try:
        store.resolve_event(db_mid, SEASON, "zurich")
        assert False, "expected no-match error"
    except KeyError as e:
        assert "no event" in str(e)


def test_no_cut_autodetected(db_mid):
    trav = store.resolve_event(db_mid, SEASON, "travelers")
    pga = store.resolve_event(db_mid, SEASON, "pga championship")
    assert trav["has_cut"] == 0
    assert pga["has_cut"] == 1


def test_amateur_flag_and_koivun_flip(wb_mid, pga_csv, travelers_csv):
    conn = store.connect(":memory:")
    store.ingest_league(conn, wb_mid, SEASON, self_name="Jay Doura")
    pga = store.resolve_event(conn, SEASON, "pga championship")
    store.ingest_preds_csv(conn, pga_csv, pga["event_id"])
    assert "jackson koivun" in store.amateur_keys(conn)
    p = store.latest_preds(conn, pga["event_id"])
    assert bool(p.loc[p["key"] == "jackson koivun", "amateur"].iloc[0])

    # Next pull has him without "(a)": pro from now on, never amateur again.
    trav = store.resolve_event(conn, SEASON, "travelers")
    store.ingest_preds_csv(conn, travelers_csv, trav["event_id"])
    assert "jackson koivun" not in store.amateur_keys(conn)
    row = conn.execute("SELECT turned_pro_date FROM golfers WHERE "
                       "key='jackson koivun'").fetchone()
    assert row[0] is not None


def test_liv_ineligible_outside_majors_only(db_mid):
    pga = store.resolve_event(db_mid, SEASON, "pga championship")
    trav = store.resolve_event(db_mid, SEASON, "travelers")
    pga_preds = store.latest_preds(db_mid, pga["event_id"])
    trav_preds = store.latest_preds(db_mid, trav["event_id"])
    assert store.ineligible_keys(db_mid, pga, pga_preds) == {}
    assert store.ineligible_keys(db_mid, trav, trav_preds) == \
        {"jon rahm": "LIV: majors only"}


def test_reingest_is_idempotent(db_mid, wb_mid):
    before = store.picks_df(db_mid, SEASON)
    store.ingest_league(db_mid, wb_mid, SEASON)
    after = store.picks_df(db_mid, SEASON)
    assert len(before) == len(after)
    assert len(store.events_df(db_mid, SEASON)) == 4
