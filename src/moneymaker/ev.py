"""Bucket EV engine -- DataGolf marginals -> expected earnings + boards."""
import numpy as np, pandas as pd
from .payouts import BUCKETS, BUCKET_ORDER

SPLIT2, SPLIT2140 = 0.30, 0.55  # sensitivity-tested 2026; ALGORITHMS s3

def bucket_probs(win, t5, t10, t20, cut, has_cut=True,
                 split2=SPLIT2, split2140=SPLIT2140) -> np.ndarray:
    """Split overrides exist ONLY for sensitivity analysis (ALGORITHMS s3);
    the defaults are the season-proven values."""
    if not has_cut:
        cut = 1.0
    p = np.array([win, (t5-win)*split2, (t5-win)*(1-split2), t10-t5, t20-t10,
                  (cut-t20)*split2140, (cut-t20)*(1-split2140), 1-cut])
    return np.clip(p, 0, None)

def expected_value(row, purse, has_cut=True) -> float:
    p = bucket_probs(row["win"], row["top_5"], row["top_10"], row["top_20"],
                     row["make_cut"], has_cut)
    mids = np.array([(BUCKETS[b][0]+BUCKETS[b][1])/2 for b in BUCKET_ORDER]) * purse
    return float((p * mids).sum())

def floor_value(row, purse, has_cut=True) -> float:
    """EV of the non-win buckets — the robustness half of the leading posture
    ("EV/floor"). Sort order stays plain EV; this is a displayed column."""
    p = bucket_probs(row["win"], row["top_5"], row["top_10"], row["top_20"],
                     row["make_cut"], has_cut)
    mids = np.array([(BUCKETS[b][0]+BUCKETS[b][1])/2 for b in BUCKET_ORDER]) * purse
    p = p.copy(); p[0] = 0.0
    return float((p * mids).sum())


def board(preds: pd.DataFrame, purse: float, used: set, has_cut=True,
          reserved=frozenset(), ineligible=frozenset(),
          posture: str = "neutral") -> pd.DataFrame:
    """Best-available for one manager. Requires normalized `key` column.
    League rules encoded here: amateurs stay VISIBLE but earn $0 (loud flag);
    ineligible (LIV outside majors, non-qualifiers) are excluded; reserved
    aces are guarded with a flag, never hidden."""
    d = preds[~preds["key"].isin(set(used) | set(ineligible))].copy()
    d["exp"] = d.apply(lambda r: expected_value(r, purse, has_cut), axis=1)
    d["floor"] = d.apply(lambda r: floor_value(r, purse, has_cut), axis=1)
    am = (d["amateur"].fillna(False).astype(bool) if "amateur" in d.columns
          else pd.Series(False, index=d.index))
    liv = (d["is_liv"].fillna(False).astype(bool) if "is_liv" in d.columns
           else pd.Series(False, index=d.index))
    d["amateur"] = am
    d.loc[am, ["exp", "floor"]] = 0.0  # amateurs earn $0 regardless of finish
    d["reserved"] = d["key"].isin(reserved)
    if posture == "trailing":
        d["score"] = d["exp"] * (1 + 8.0*d["win"])
    elif posture == "leading":
        # "EV/floor" (ALGORITHMS s3): protect the lead — blend toward the
        # non-win floor so steady cashers outrank boom-or-bust win equity.
        # v1 interpretation (equal blend); adjudicate via backtest replay.
        d["score"] = (d["exp"] + d["floor"]) / 2.0
    else:
        d["score"] = d["exp"]
    d["flags"] = (am.map({True: "AMATEUR $0 ", False: ""})
                  + d["reserved"].map({True: "RESERVED ", False: ""})
                  + liv.map({True: "LIV", False: ""})).str.strip()
    return d.sort_values("score", ascending=False).reset_index(drop=True)
