"""End-to-end weekly workflow through the real CLI (F1-F9)."""
from typer.testing import CliRunner

from moneymaker.cli import app

runner = CliRunner()
SEASON = "2027"


def run(*args):
    res = runner.invoke(app, list(args))
    assert res.exit_code == 0, f"{args}\n{res.output}"
    return res.output


def test_weekly_workflow(tmp_path, wb_mid, pga_csv, travelers_csv):
    db = str(tmp_path / "mm.db")
    base = ["--db", db, "--season", SEASON]

    out = run("ingest-league", str(wb_mid), "--self", "Jay Doura", *base)
    assert "5 events" in out

    run("flag-liv", "Rahm, Jon", "--db", db)

    out = run("ingest-preds", str(pga_csv), "--event", "pga championship", *base)
    assert "has_cut=True" in out
    assert "Koivun" in out                       # amateur called out loudly

    out = run("best-available", "--event", "pga", "--posture", "trailing", *base)
    assert "Scottie Scheffler" in out
    assert "AMATEUR $0" in out                   # still amateur at this point

    out = run("ingest-preds", str(travelers_csv), "--event", "travelers", *base)
    assert "has_cut=False" in out                # no-cut auto-detected

    # Koivun appears WITHOUT "(a)" in the Travelers pull -> pro from now on.
    out = run("best-available", "--event", "pga", "--posture", "trailing", *base)
    assert "AMATEUR $0" not in out

    out = run("best-available", "--event", "pga",
              "--reserve", "Scheffler, Scottie", *base)
    assert "GUARD" in out                        # reserved ace on top -> warn

    out = run("sequence", *base)
    assert "season plan" in out
    assert "scottie scheffler" in out

    out = run("simulate", "--board", "overall", "--n", "4000", *base)
    assert "P(1st)" in out
    assert "Top threats" in out
    assert "Rival Two" in out

    out = run("simulate", "--board", "overall", "--n", "2000",
              "--sensitivity", *base)
    assert "Sensitivity" in out

    out = run("threats", "--event", "pga", "--n", "4000", *base)
    assert "MIRROR" in out                       # Mirror Max projected onto
    #                                              the same chalk as us

    out = run("opponents", *base)
    assert "Mirror Max" in out and "100%" in out

    run("journal", "--add", "locked Scheffler, field feels soft", "--event",
        "pga", *base)
    out = run("journal", *base)
    assert "locked Scheffler" in out


def test_sunday_card(tmp_path, wb_sunday, pga_csv, positions_csv):
    db = str(tmp_path / "mm.db")
    base = ["--db", db, "--season", SEASON]
    run("ingest-league", str(wb_sunday), "--self", "Jay Doura", *base)
    out = run("ingest-preds", str(pga_csv), "--event", "pga", *base)
    out = run("sunday-card", "--positions", str(positions_csv),
              "--event", "pga", "--n", "8000", *base)
    assert "Sunday card" in out
    assert "Viktor Hovland" in out or "viktor hovland" in out
    assert "Pass thresholds" in out
    assert "Rival Two" in out                    # the leader we must chase
    # Chalk Charlie holds amateur Koivun: called out, credited $0
    assert "AMATEUR" in out and "Chalk Charlie" in out


def test_sunday_card_live_positions(tmp_path, wb_sunday, pga_csv, monkeypatch):
    import pandas as pd

    from moneymaker import cli

    class FakeAPI:
        def live_stats(self, tour="pga"):
            return pd.DataFrame({
                "event_name": ["PGA Championship"] * 4,
                "last_updated": ["2027-05-22"] * 4,
                "stat_round": [3] * 4,
                "position": ["1", "2", "T3", "CUT"],
                "player_name": ["Scheffler, Scottie", "Hovland, Viktor",
                                "Thomas, Justin", "Fox, Ryan"],
                "total": [-12, -11, -8, 2],
            })

    monkeypatch.setattr(cli, "DataGolfAPI", FakeAPI)
    db = str(tmp_path / "mm.db")
    base = ["--db", db, "--season", SEASON]
    run("ingest-league", str(wb_sunday), "--self", "Jay Doura", *base)
    run("ingest-preds", str(pga_csv), "--event", "pga", *base)
    out = run("sunday-card", "--live", "--event", "pga", "--n", "6000", *base)
    assert "live positions: 3 players" in out      # CUT row dropped
    assert "Pass thresholds" in out

    res = runner.invoke(app, ["sunday-card", "--event", "pga", *base])
    assert res.exit_code == 1                      # neither source given


def test_sequence_reserved_ace_weak_fields_only(tmp_path, wb_mid, pga_csv,
                                                travelers_csv, weak_csv):
    """Reserved aces are barred from WEAK fields only. The no-cut $20M
    Travelers counts as strong (the 2026 playoff-pair lesson) even while
    typed 'open'; the $6M cut event is the weak field."""
    db = str(tmp_path / "mm.db")
    base = ["--db", db, "--season", SEASON]
    run("ingest-league", str(wb_mid), "--self", "Jay Doura", *base)
    run("ingest-preds", str(pga_csv), "--event", "pga", *base)
    run("ingest-preds", str(travelers_csv), "--event", "travelers", *base)
    run("ingest-preds", str(weak_csv), "--event", "weak open", *base)
    out = run("sequence", "--reserve", "Scheffler, Scottie", *base)
    weak_lines = [l for l in out.splitlines() if "Weak Open" in l]
    assert weak_lines and all("scottie scheffler" not in l for l in weak_lines)
    assert "scottie scheffler" in out            # still spent at a strong field

    # Explicit tagging beats inference: mark the weak event a signature
    # field and the ace becomes assignable there.
    run("set-field-type", "weak open", "signature", *base)
    out = run("sequence", "--reserve", "Scheffler, Scottie", *base)
    assert "scottie scheffler" in out


def test_best_available_unknown_manager_fails_cleanly(tmp_path, wb_mid,
                                                      pga_csv):
    db = str(tmp_path / "mm.db")
    base = ["--db", db, "--season", SEASON]
    run("ingest-league", str(wb_mid), "--self", "Jay Doura", *base)
    run("ingest-preds", str(pga_csv), "--event", "pga", *base)
    res = runner.invoke(app, ["best-available", "--event", "pga",
                              "--manager", "jay doura", *base])
    assert res.exit_code == 1
    assert "Jay Doura" in res.output             # suggests the real name
