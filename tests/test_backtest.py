import json
import shutil

from moneymaker.backtest import replay

SEASON = 2027


def test_replay_uses_deadline_snapshot_only(tmp_path, wb_early, wb_final,
                                            pga_csv):
    league_dir = tmp_path / "league"
    preds_dir = tmp_path / "dg"
    league_dir.mkdir(), preds_dir.mkdir()
    shutil.copy(wb_early, league_dir / "a_early.xlsx")
    shutil.copy(wb_final, league_dir / "z_final.xlsx")
    shutil.copy(pga_csv, preds_dir / "pga_championship.csv")

    out = tmp_path / "golden.json"
    df, summary = replay(str(league_dir), str(preds_dir), SEASON,
                         manager="Jay Doura", out_json=str(out))
    row = df.iloc[0]
    assert row["event"].startswith("PGA")
    # deadline info = the early workbook (only Sony picked), NOT the final one
    assert row["deadline_workbook"] == "a_early.xlsx"
    # engine sees Scheffler available (Jay only used Spaun by then)
    assert row["engine_pick"] == "scottie scheffler"
    assert row["actual_pick"] == "viktor hovland"        # what Jay really did
    assert row["realized"] == 650_000                    # settled PGA money
    assert summary["sum_ev_engine"] >= summary["sum_ev_actual"]
    assert isinstance(summary["accept_sum_ev"], bool)

    golden = json.loads(out.read_text())
    assert golden["summary"]["manager"] == "Jay Doura"
    assert len(golden["events"]) == 1
