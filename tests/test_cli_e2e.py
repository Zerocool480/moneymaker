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
    assert "4 events" in out

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


def test_sequence_respects_reserved_weak_field_rule(tmp_path, wb_mid, pga_csv,
                                                    travelers_csv):
    db = str(tmp_path / "mm.db")
    base = ["--db", db, "--season", SEASON]
    run("ingest-league", str(wb_mid), "--self", "Jay Doura", *base)
    run("ingest-preds", str(pga_csv), "--event", "pga", *base)
    run("ingest-preds", str(travelers_csv), "--event", "travelers", *base)
    # Reserve Scheffler: Travelers is field_type 'open' -> he may NOT be
    # assigned there; PGA is a major -> allowed.
    out = run("sequence", "--reserve", "Scheffler, Scottie", *base)
    for line in out.splitlines():
        if "Travelers" in line:
            assert "scottie scheffler" not in line
