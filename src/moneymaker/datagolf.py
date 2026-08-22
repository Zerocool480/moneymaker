"""DataGolf ingestion: CSV now, API phase 2 (same column contract)."""
import io
import os
import urllib.error
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


KEY_FILE = os.path.join("data", "datagolf.key")   # gitignored (data/)


def _resolve_key(key: str | None) -> str | None:
    if key:
        return key
    env = os.environ.get("DATAGOLF_API_KEY")
    if env:
        return env.strip()
    try:
        with open(KEY_FILE) as fh:
            return fh.read().strip() or None
    except OSError:
        return None


class DataGolfAPI:
    """Thin client for https://feeds.datagolf.com (phase 2). Returns frames in
    the exact CSV contract shape so everything downstream is source-agnostic.
    Key lookup: explicit arg -> DATAGOLF_API_KEY env -> data/datagolf.key
    (a one-line file; data/ is gitignored so the secret never hits git)."""

    BASE = "https://feeds.datagolf.com"

    def __init__(self, key: str | None = None, opener=None):
        self.key = _resolve_key(key)
        if not self.key:
            raise RuntimeError(
                "DataGolf API key missing: set DATAGOLF_API_KEY, or put the "
                "key alone in data/datagolf.key, or use CSV ingestion "
                "(mm ingest-preds).")
        self._open = opener or urllib.request.urlopen

    def _get_csv(self, path: str, required=("player_name",), **params
                 ) -> pd.DataFrame:
        params = {"file_format": "csv", "key": self.key, **params}
        url = f"{self.BASE}/{path}?{urllib.parse.urlencode(params)}"
        try:
            with self._open(url, timeout=30) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:      # never echo the URL (key!)
            body = e.read()[:200].decode("utf-8", "replace")
            raise RuntimeError(
                f"DataGolf API rejected {path} (HTTP {e.code}): {body!r} — "
                "check the key and your subscription tier.") from None
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"cannot reach feeds.datagolf.com ({e.reason}). If this "
                "machine restricts outbound traffic (e.g. a Claude Code "
                "remote environment), allow feeds.datagolf.com in its "
                "network policy. CSV ingestion (mm ingest-preds) works "
                "offline.") from None
        try:
            d = pd.read_csv(io.BytesIO(raw))
        except Exception:
            raise RuntimeError(
                f"DataGolf {path} did not return CSV; first bytes: "
                f"{raw[:200].decode('utf-8', 'replace')!r}") from None
        missing = set(required) - set(d.columns)
        if missing:
            raise RuntimeError(
                f"DataGolf {path} response is missing expected columns "
                f"{sorted(missing)}; got {list(d.columns)[:15]} — the feed "
                "contract may have changed, please report this.")
        return d

    def pre_tournament_preds(self, tour: str = "pga",
                             model: str = "baseline_history_fit"
                             ) -> pd.DataFrame:
        d = self._get_csv("preds/pre-tournament", tour=tour,
                          required=("player_name", *COLS),
                          odds_format="percent", dead_heat="no")
        # Live-feed fact (verified 2026-08, BMW pull): the CSV stacks one row
        # per golfer PER MODEL (baseline + baseline_history_fit). Keep one
        # model or every golfer ingests twice.
        if "model" in d.columns and d["model"].nunique() > 1:
            want = model if (d["model"] == model).any() else \
                d["model"].iloc[0]
            d = d[d["model"] == want].copy()
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
