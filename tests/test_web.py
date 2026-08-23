"""Web UI v3 (SUNDAY BROADCAST) e2e over the fixture league."""
import pytest
from fastapi.testclient import TestClient

from conftest import SEASON

from moneymaker import store
from moneymaker.web.app import _money, create_app

MINUS = "−"


@pytest.fixture()
def client(tmp_path, wb_mid, pga_csv, travelers_csv):
    db = str(tmp_path / "mm.db")
    conn = store.connect(db)
    store.ingest_league(conn, wb_mid, SEASON, self_name="Jay Doura")
    store.set_liv(conn, ["Rahm, Jon"])
    for csv, frag in ((pga_csv, "pga championship"), (travelers_csv, "travelers")):
        e = store.resolve_event(conn, SEASON, frag)
        store.ingest_preds_csv(conn, csv, e["event_id"])
    conn.close()
    return TestClient(create_app(db=db, season=SEASON))


def test_money_filter_uses_true_minus():
    assert _money(-677_592) == f"{MINUS}$677,592"
    assert _money(1_056_719) == "$1,056,719"


def test_dashboard_broadcast_open(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "THE TOWER" in r.text
    assert "Rival Two" in r.text
    assert "MONEY MAKER" in r.text
    assert "OVR " in r.text                        # the score bug ticker
    r2 = client.get("/?board=segment1")
    assert r2.status_code == 200


def test_pick_decision_desk(client):
    r = client.get("/pick?event=pga&posture=trailing")
    assert r.status_code == 200
    assert "Scottie Scheffler" in r.text
    assert "LIV" in r.text                         # Rahm flagged on a major
    assert "EV bar · scale" in r.text              # printed shared scale
    assert "- $19M" not in r.text                  # purse suffix normalized
    why = client.get("/pick/why", params={"event": "pga",
                                          "key": "scottie scheffler"})
    assert why.status_code == 200
    assert "Missed cut" in why.text and "Expected value" in why.text


def test_pick_hx_swap_returns_board_only(client):
    r = client.get("/pick?event=pga&posture=leading",
                   headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert "board-table" in r.text
    assert "MONEY MAKER" not in r.text             # partial, not full page


def test_race_projection_desk(client):
    r = client.post("/race/run", data={"board": "overall", "n": 3000})
    assert r.status_code == 200
    assert "P(in the money)" in r.text
    assert "THE CATCH LIST" in r.text
    assert "±" in r.text                           # whisker on the headline P


def test_lock_endpoint_writes_pick(client):
    r = client.post("/api/lock", data={"event": "travelers",
                                       "key": "viktor hovland"})
    assert r.status_code == 200 and r.json()["ok"]
    r2 = client.get("/season")
    assert "Viktor Hovland" in r2.text             # season map shows the lock
    # second lock on a 1-slot event is refused
    r3 = client.post("/api/lock", data={"event": "travelers",
                                        "key": "harris english"})
    assert r3.status_code == 409


def test_season_map_and_plan(client):
    r = client.get("/season")
    assert r.status_code == 200
    assert "MAJOR ×2" in r.text
    assert "SEGMENT 1" in r.text                   # segment section heads
    plan = client.post("/season/plan", data={"posture": "neutral",
                                             "reserve": "", "top_k": 8})
    assert plan.status_code == 200
    assert "Plan total" in plan.text


def test_sunday_opens_dealt_with_defense(tmp_path, wb_sunday, pga_csv,
                                         positions_csv):
    db = str(tmp_path / "mm.db")
    conn = store.connect(db)
    store.ingest_league(conn, wb_sunday, SEASON, self_name="Jay Doura")
    e = store.resolve_event(conn, SEASON, "pga championship")
    store.ingest_preds_csv(conn, pga_csv, e["event_id"])
    conn.close()
    c = TestClient(create_app(db=db, season=SEASON))
    page = c.get("/sunday")
    assert page.status_code == 200
    assert 'selected>PGA Championship' in page.text   # server-side default
    with open(positions_csv, "rb") as fh:
        r = c.post("/sunday/run",
                   data={"event": "pga", "source": "upload", "n": 6000},
                   files={"positions": ("pos.csv", fh, "text/csv")})
    assert r.status_code == 200
    assert "RIGHT NOW YOU FINISH" in r.text
    assert "ATTACK" in r.text
    assert "DEFENSE" in r.text                     # the un-rendered side, rendered
    assert "±" in r.text                           # forced whisker on hero P


def test_history_season_film(client):
    r = client.get("/history")
    assert r.status_code == 200
    assert "RIVAL PROFILES" in r.text and "Mirror Max" in r.text
    assert "THE MONEY RACE" in r.text              # cumulative chart present


def test_empty_db_onboarding(tmp_path):
    c = TestClient(create_app(db=str(tmp_path / "empty.db"), season=SEASON))
    r = c.get("/")
    assert r.status_code == 200
    assert "mm ingest-league" in r.text
