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


def test_api_requires_key(monkeypatch, tmp_path):
    monkeypatch.delenv("DATAGOLF_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)               # no data/datagolf.key here
    with pytest.raises(RuntimeError, match="DATAGOLF_API_KEY"):
        DataGolfAPI()


def test_api_key_file_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("DATAGOLF_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "datagolf.key").write_text("k-from-file\n")
    assert DataGolfAPI().key == "k-from-file"


def test_api_network_error_is_actionable():
    import urllib.error

    def blocked(url, timeout=None):
        raise urllib.error.URLError("Tunnel connection failed: 403 Forbidden")

    api = DataGolfAPI(key="k123", opener=blocked)
    with pytest.raises(RuntimeError, match="network policy"):
        api.pre_tournament_preds()


def test_api_contract_drift_is_reported():
    body = b"player_name,something_else\nA B,1\n"

    def fake_open(url, timeout=None):
        return _FakeResp(body)

    api = DataGolfAPI(key="k123", opener=fake_open)
    with pytest.raises(RuntimeError, match="missing expected columns"):
        api.pre_tournament_preds()


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
