from moneymaker.sequencer import solve


def test_whole_season_beats_greedy():
    # Greedy takes a@e1 (10) then c@e2 (8) = 18; the assignment answer is
    # b@e1 + a@e2 = 19 — the entire reason the sequencer exists.
    boards = {"e1": [(10.0, "a"), (9.0, "b")],
              "e2": [(10.0, "a"), (8.0, "c")]}
    tot, asg = solve(boards)
    assert tot == 19.0
    assert asg == {"e1": "b", "e2": "a"}


def test_all_picks_distinct():
    boards = {"e1": [(5.0, "a"), (4.0, "b")],
              "e2": [(5.0, "a"), (1.0, "b")],
              "e3": [(5.0, "a"), (1.0, "c")]}
    tot, asg = solve(boards)
    assert len(set(asg.values())) == 3


def test_constraint_hook_respected():
    boards = {"e1": [(10.0, "a"), (9.0, "b")],
              "e2": [(10.0, "a"), (8.0, "c")]}
    tot, asg = solve(boards, constraint=lambda g: g["e2"] != "a")
    assert asg == {"e1": "a", "e2": "c"}
    assert tot == 18.0


def test_infeasible_returns_none():
    boards = {"e1": [(1.0, "a")], "e2": [(1.0, "a")]}
    assert solve(boards) is None


def test_hungarian_matches_brute_force_on_random_instances():
    import random
    rnd = random.Random(9)
    for _ in range(20):
        events = [f"e{i}" for i in range(rnd.randint(2, 5))]
        pool = [f"g{i}" for i in range(7)]
        boards = {e: sorted(((round(rnd.uniform(1, 100), 2), g)
                             for g in rnd.sample(pool, rnd.randint(2, 5))),
                            reverse=True) for e in events}
        hung = solve(boards)
        brute = solve(boards, constraint=lambda a: True)  # forces brute path
        assert (hung is None) == (brute is None)
        if hung:
            assert abs(hung[0] - brute[0]) < 1e-9   # same optimum
            # assignments may differ on exact ties; totals must not


def test_full_season_slate_solves_fast():
    # The January full-season plan: ~30 slots x top-8 pools. Brute force
    # would be 8^30; Hungarian must return instantly and optimally.
    import time
    boards = {f"e{i}": [(100.0 - i - j * 0.5, f"g{i * 3 + j}")
                        for j in range(8)] for i in range(30)}
    t0 = time.perf_counter()
    res = solve(boards)
    assert res is not None
    assert time.perf_counter() - t0 < 2.0
    assert len(set(res[1].values())) == 30


def test_expiring_name_is_never_force_played():
    # The 2026 Bradley/Wyndham lesson: a name in its LAST usable field must
    # not be auto-picked over higher EV — expiring != must-play. The solver
    # optimizes pure EV; this pins that no urgency bias creeps in.
    boards = {"wyndham": [(500.0, "english"), (450.0, "bradley")],
              "playoff": [(900.0, "scheffler"), (100.0, "english")]}
    tot, asg = solve(boards)
    assert asg["wyndham"] == "english"      # bradley expires unplayed
    assert "bradley" not in asg.values()
