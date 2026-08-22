"""DataGolf ingestion: CSV now, API phase 2 (same column contract)."""
import io
import os
import urllib.parse
import urllib.request

import pandas as pd

from .names import norm

COLS = ["win", "top_5", "top_10", "top_20", "make_cut"]
_AMATEUR_RX = r"\(\s*a\s*m?\s*\)"  # "(a)" / "(am)", any case/spacing


def _finish(d: pd.DataFrame) -> pd.DataFrame:
    for c in COLS:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    # Amateur flag must be read BEFORE norm() strips parentheticals.
    d["amateur"] = d["player_name"].astype(str).str.contains(
        _AMATEUR_RX, case=False, regex=True)
    d["key"] = d["player_name"].apply(norm)
    d = d.dropna(subset=COLS)
    d.attrs["has_cut"] = bool((d["make_cut"] < 0.999).any())  # auto-detect
    return d


def load_preds_csv(path) -> pd.DataFrame:
    return _finish(pd.read_csv(path))


class DataGolfAPI:
    """Thin client for https://feeds.datagolf.com (phase 2). Returns frames in
    the exact CSV contract shape so everything downstream is source-agnostic."""

    BASE = "https://feeds.datagolf.com"

    def __init__(self, key: str | None = None, opener=None):
        self.key = key or os.environ.get("DATAGOLF_API_KEY")
        if not self.key:
            raise RuntimeError(
                "DataGolf API key missing: set DATAGOLF_API_KEY or use CSV "
                "ingestion (mm ingest-preds).")
        self._open = opener or urllib.request.urlopen

    def _get_csv(self, path: str, **params) -> pd.DataFrame:
        params = {"file_format": "csv", "key": self.key, **params}
        url = f"{self.BASE}/{path}?{urllib.parse.urlencode(params)}"
        with self._open(url, timeout=30) as resp:
            raw = resp.read()
        return pd.read_csv(io.BytesIO(raw))

    def pre_tournament_preds(self, tour: str = "pga") -> pd.DataFrame:
        d = self._get_csv("preds/pre-tournament", tour=tour,
                          odds_format="percent", dead_heat="no")
        # Percent -> probability if the feed returned 0-100 numbers.
        for c in COLS:
            d[c] = pd.to_numeric(d[c], errors="coerce")
        if d[COLS].max().max() > 1.5:
            d[COLS] = d[COLS] / 100.0
        return _finish(d)

    def field_updates(self, tour: str = "pga") -> pd.DataFrame:
        d = self._get_csv("field-updates", tour=tour)
        d["key"] = d["player_name"].apply(norm)
        return d

    def live_stats(self, tour: str = "pga") -> pd.DataFrame:
        d = self._get_csv("preds/live-tournament-stats", tour=tour)
        d["key"] = d["player_name"].apply(norm)
        return d
