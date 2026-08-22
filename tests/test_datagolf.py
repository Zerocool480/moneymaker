import io

import pytest

from moneymaker.datagolf import COLS, DataGolfAPI, load_preds_csv


def test_csv_contract_and_amateur_detection(pga_csv):
    d = load_preds_csv(pga_csv)
    assert set(COLS) <= set(d.columns)
    assert d.attrs["has_cut"] is True
    am = d[d["amateur"]]
    assert list(am["key"]) == ["jackson koivun"]


def test_no_cut_autodetect(travelers_csv):
    d = load_preds_csv(travelers_csv)
    assert d.attrs["has_cut"] is False


def test_api_requires_key(monkeypatch):
    monkeypatch.delenv("DATAGOLF_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DATAGOLF_API_KEY"):
        DataGolfAPI()


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_api_maps_percent_feed_to_probabilities():
    body = (b"player_name,win,top_5,top_10,top_20,make_cut\n"
            b'"Scheffler, Scottie",16,35,48,65,92\n'
            b'"Koivun, Jackson (a)",3,12,20,35,80\n')
    seen = {}

    def fake_open(url, timeout=None):
        seen["url"] = url
        return _FakeResp(body)

    api = DataGolfAPI(key="k123", opener=fake_open)
    d = api.pre_tournament_preds()
    assert "preds/pre-tournament" in seen["url"]
    assert "key=k123" in seen["url"]
    assert abs(d.loc[d["key"] == "scottie scheffler", "win"].iloc[0] - .16) < 1e-9
    assert bool(d.loc[d["key"] == "jackson koivun", "amateur"].iloc[0])
    assert d.attrs["has_cut"] is True
