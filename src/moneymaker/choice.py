"""Probabilistic rival-pick model — conditional logit over the available board.

P(manager picks golfer g) = softmax_g( beta . x(g) ) across their AVAILABLE
board at that event. This replaces point predictions with a calibrated
distribution the race Monte Carlo can SAMPLE from: a point pick assigns
probability zero to everything else a rival might do (and rivals do
"everything else" ~3 weeks in 4 — measured 23% top-1 on 2026), while a
fitted softmax spreads mass the way the field actually behaves.

Features per candidate (all computable strictly from pre-deadline data):
  rel_log_ev  log(exp / exp_top)          board-relative EV        (<= 0)
  rel_win     10 * (win - win_top)        board-relative win prob
  hot         prior-week top-10 earner    (form signal)
  chase_hot   form_chase_rate * hot       (chasers act on form)
  pop         share of league that used g at earlier events (herding)

Fit: L2-regularized maximum likelihood (scipy BFGS). ~5 params vs hundreds
of observed picks — deliberately small; anything bigger memorizes 86 people.
"""
import numpy as np
from scipy.optimize import minimize

FEATURES = ["rel_log_ev", "rel_win", "hot", "chase_hot", "pop"]
# Cold-start prior: EV-driven with a mild win/form tilt (used until enough
# picks accumulate to fit; also the optimizer's starting point).
DEFAULT_BETA = np.array([1.5, 1.0, 0.3, 0.3, 0.5])
MIN_FIT_ROWS = 120


def feature_matrix(board, hot_keys: set, profile, pop: dict) -> np.ndarray:
    """board: ev.board() DataFrame (sorted, has exp/win/key). -> (G, 5)."""
    exp = board["exp"].to_numpy(dtype=float)
    win = board["win"].to_numpy(dtype=float)
    top_exp = max(float(exp.max()), 1e-9) if len(exp) else 1e-9
    top_win = float(win.max()) if len(win) else 0.0
    hot = board["key"].isin(hot_keys).to_numpy(dtype=float)
    chase = getattr(profile, "form_chase_rate", 0.0) * hot
    popularity = board["key"].map(lambda k: pop.get(k, 0.0)).to_numpy(float)
    rel_log_ev = np.log(np.clip(exp, 1e-9, None) / top_exp)
    rel_log_ev = np.clip(rel_log_ev, -8.0, 0.0)   # amateurs/zeros bounded
    rel_win = 10.0 * (win - top_win)
    return np.column_stack([rel_log_ev, rel_win, hot, chase, popularity])


def predict_proba(beta: np.ndarray, X: np.ndarray) -> np.ndarray:
    z = X @ beta
    z = z - z.max()
    p = np.exp(z)
    return p / p.sum()


def _nll(beta, rows, l2):
    total = 0.0
    for X, chosen in rows:
        z = X @ beta
        z = z - z.max()
        total -= z[chosen] - np.log(np.exp(z).sum())
    return total / max(len(rows), 1) + l2 * float(beta @ beta) / max(len(rows), 1)


def fit(rows, l2: float = 2.0, beta0: np.ndarray | None = None):
    """rows: [(X, chosen_index)]. Returns fitted beta, or None if there is
    not enough data to trust a fit (caller falls back to DEFAULT_BETA)."""
    if len(rows) < MIN_FIT_ROWS:
        return None
    res = minimize(_nll, beta0 if beta0 is not None else DEFAULT_BETA.copy(),
                   args=(rows, l2), method="BFGS",
                   options={"maxiter": 200})
    return res.x if res.success or res.fun < _nll(DEFAULT_BETA, rows, l2) \
        else None


def popularity(conn, season: int, before_seq: int) -> dict:
    """key -> share of managers who used the golfer before before_seq."""
    n = conn.execute("SELECT COUNT(*) FROM managers").fetchone()[0] or 1
    out = {}
    for r in conn.execute(
            "SELECT g.key, COUNT(DISTINCT p.manager_id) FROM picks p"
            " JOIN events e ON e.event_id=p.event_id"
            " JOIN golfers g ON g.golfer_id=p.golfer_id"
            " WHERE p.season=? AND e.seq<? GROUP BY g.key",
            (season, before_seq)):
        out[r[0]] = r[1] / n
    return out


def training_rows(conn, season: int, profiles=None, top_cap: int = 60):
    """Assemble (X, chosen) rows from every stored event that has both
    predictions and recorded picks — used sets, hot lists, and popularity
    all as-of each event (strictly walk-forward within the season)."""
    from . import opponents as opp
    from . import store
    from .ev import board as ev_board
    profiles = profiles or opp.mine_profiles(conn, season)
    picks_df = store.picks_df(conn, season)
    rows = []
    for eid in store.events_with_preds(conn, season):
        erow = conn.execute("SELECT * FROM events WHERE event_id=?",
                            (eid,)).fetchone()
        actual = store.event_picks(conn, season, eid)
        if not actual:
            continue
        preds = store.latest_preds(conn, eid)
        seq = int(erow["seq"])
        hot = opp.hot_keys(picks_df, seq)
        pop = popularity(conn, season, seq)
        purse = erow["purse"] or 1e7
        prior = picks_df[picks_df["seq"] < seq]
        used_asof = prior.groupby("manager")["key"].agg(set).to_dict()
        for mgr, chosen_keys in actual.items():
            used = set(used_asof.get(mgr, set()))
            prof = profiles.get(mgr)
            for k in chosen_keys:            # majors: one row per slot
                b = ev_board(preds, purse, used,
                             has_cut=bool(erow["has_cut"])).head(top_cap)
                keys = list(b["key"])
                if k not in keys:
                    used.add(k)              # off-board pick still consumes
                    continue
                X = feature_matrix(b, hot, prof, pop)
                rows.append((X, keys.index(k)))
                used.add(k)
    return rows


def fit_from_store(conn, season: int, profiles=None):
    """Fit on everything the store has seen so far; None -> use DEFAULT_BETA."""
    return fit(training_rows(conn, season, profiles))
