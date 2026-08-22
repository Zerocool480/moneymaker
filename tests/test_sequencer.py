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
