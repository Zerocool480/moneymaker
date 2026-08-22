import numpy as np
from conftest import SEASON

from moneymaker import choice, store


def test_predict_proba_sums_to_one():
    X = np.array([[0.0, 0.0, 1.0, 0.0, 0.2],
                  [-1.0, -0.5, 0.0, 0.0, 0.0],
                  [-3.0, -1.0, 0.0, 0.0, 0.5]])
    p = choice.predict_proba(choice.DEFAULT_BETA, X)
    assert abs(p.sum() - 1) < 1e-12
    assert p[0] > p[2]                       # better candidate, more mass


def test_fit_recovers_preference_directions():
    rng = np.random.default_rng(5)
    true = np.array([2.0, 1.0, 1.5, 0.0, 0.0])
    rows = []
    for _ in range(400):
        X = np.column_stack([
            -rng.random(6) * 3,              # rel_log_ev in [-3, 0]
            -rng.random(6),                  # rel_win
            rng.integers(0, 2, 6).astype(float),
            np.zeros(6), np.zeros(6)])
        p = choice.predict_proba(true, X)
        rows.append((X, int(rng.choice(6, p=p))))
    beta = choice.fit(rows)
    assert beta is not None
    assert beta[0] > 0.5                     # EV preference recovered
    assert beta[2] > 0.3                     # hot preference recovered
    # fitted model must beat the default prior on its own training NLL
    assert choice._nll(beta, rows, 0.0) < choice._nll(choice.DEFAULT_BETA,
                                                      rows, 0.0)


def test_fit_refuses_tiny_samples():
    rows = [(np.zeros((3, 5)), 0)] * (choice.MIN_FIT_ROWS - 1)
    assert choice.fit(rows) is None


def test_feature_matrix_shapes_and_bounds(db_mid):
    pga = store.resolve_event(db_mid, SEASON, "pga championship")
    preds = store.latest_preds(db_mid, pga["event_id"])
    from moneymaker.ev import board
    b = board(preds, 19e6, used=set())
    X = choice.feature_matrix(b, {"scottie scheffler"}, None, {"jj spaun": .4})
    assert X.shape == (len(b), 5)
    assert (X[:, 0] <= 0).all() and (X[:, 0] >= -8).all()
    assert X[0, 2] in (0.0, 1.0)


def test_training_rows_and_store_fit_fallback(db_mid):
    rows = choice.training_rows(db_mid, SEASON)
    # only Rival One's two locked PGA picks are recorded with preds available
    assert len(rows) >= 2
    X, chosen = rows[0]
    assert X.shape[1] == 5
    assert 0 <= chosen < X.shape[0]
    assert choice.fit_from_store(db_mid, SEASON) is None   # too few rows
