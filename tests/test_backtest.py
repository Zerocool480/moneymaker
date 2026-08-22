import json
import shutil

from moneymaker.backtest import replay

SEASON = 2027


def test_replay_is_content_based_and_slot_aligned(tmp_path, wb_early,
                                                  wb_final, pga_csv):
    league_dir = tmp_path / "league"
    preds_dir = tmp_path / "dg"
    league_dir.mkdir(), preds_dir.mkdir()
    # ADVERSARIAL filenames: alphabetical order is the REVERSE of
    # chronology — selection must go by pick-history content, not names.
    shutil.copy(wb_early, league_dir / "zzz_wrong_if_sorted.xlsx")
    shutil.copy(wb_final, league_dir / "aaa_wrong_if_sorted.xlsx")
    shutil.copy(pga_csv, preds_dir / "pga_championship.csv")

    out = tmp_path / "golden.json"
    df, summary = replay(str(league_dir), str(preds_dir), SEASON,
                         manager="Jay Doura", out_json=str(out))
    row = df.iloc[0]
    assert row["event"].startswith("PGA")
    assert summary["final_workbook"] == "aaa_wrong_if_sorted.xlsx"
    # deadline snapshot = most progressed workbook with no PGA picks yet
    assert row["deadline_workbook"] == "zzz_wrong_if_sorted.xlsx"
    # used set at lock includes BOTH earlier picks (Sony AND Farmers),
    # sourced from strictly-prior columns of the final workbook
    assert "scottie scheffler" in row["engine_pick"]
    assert "collin morikawa" not in row["engine_pick"]
    assert "jj spaun" not in row["engine_pick"]
    # majors compare like with like: two engine picks vs two actual picks
    assert len(row["engine_pick"].split(", ")) == 2
    assert row["actual_pick"] == "viktor hovland, justin thomas"
    assert row["actual_ev"] > 0
    assert row["realized"] == 650_000                    # both slots settled
    assert summary["sum_ev_engine"] >= summary["sum_ev_actual"]
    assert isinstance(summary["accept_sum_ev"], bool)

    golden = json.loads(out.read_text())
    assert golden["summary"]["manager"] == "Jay Doura"
    assert len(golden["events"]) == 1
