"""Web UI e2e over the fixture league via FastAPI TestClient."""
import pytest
from fastapi.testclient import TestClient

from conftest import SEASON

from moneymaker import store
from moneymaker.web.app import create_app


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


def test_dashboard(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Jay Doura" in r.text and "Standings" in r.text
    assert "Rival Two" in r.text                       # leader on the board
    r2 = client.get("/?board=segment1")
    assert r2.status_code == 200


def test_pick_board_and_why_panel(client):
    r = client.get("/pick?event=pga&posture=trailing")
    assert r.status_code == 200
    assert "Scottie Scheffler" in r.text
    assert "LIV" in r.text                             # Rahm flagged
    # (Koivun turned pro at the Travelers ingest, so no AMATEUR chip here —
    # the flag lifecycle is covered by the CLI e2e tests.)
    why = client.get("/pick/why", params={"event": "pga",
                                          "key": "scottie scheffler"})
    assert why.status_code == 200
    assert "Missed cut" in why.text and "Expected value" in why.text


def test_race_run(client):
    r = client.post("/race/run", data={"board": "overall", "n": 3000})
    assert r.status_code == 200
    assert "P(1st)" in r.text and "Threats" in r.text
    assert "Rival Two" in r.text


def test_season_map_and_plan(client):
    r = client.get("/season")
    assert r.status_code == 200
    assert "major ×2" in r.text
    plan = client.post("/season/plan", data={"posture": "neutral",
                                             "reserve": "", "top_k": 8})
    assert plan.status_code == 200
    assert "Plan total" in plan.text


def test_sunday_upload(client, positions_csv):
    with open(positions_csv, "rb") as fh:
        r = client.post("/sunday/run",
                        data={"event": "pga", "source": "upload", "n": 6000},
                        files={"positions": ("pos.csv", fh, "text/csv")})
    assert r.status_code == 200
    assert "Pass thresholds" in r.text


def test_history(client):
    r = client.get("/history")
    assert r.status_code == 200
    assert "Rival profiles" in r.text and "Mirror Max" in r.text


def test_empty_db_onboarding(tmp_path):
    c = TestClient(create_app(db=str(tmp_path / "empty.db"), season=SEASON))
    r = c.get("/")
    assert r.status_code == 200
    assert "mm ingest-league" in r.text
