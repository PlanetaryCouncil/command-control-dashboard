import random

from app.sync import Clock, HLC, Op, OpLog, make_ops


def test_hlc_strictly_increases_within_the_same_millisecond():
    clock = Clock("node-a")
    a = clock.tick(now_ms=1000)
    b = clock.tick(now_ms=1000)
    c = clock.tick(now_ms=1000)
    assert a.to_tuple() < b.to_tuple() < c.to_tuple()


def test_hlc_never_goes_backwards_even_with_a_stale_wall_clock():
    clock = Clock("node-a")
    clock.tick(now_ms=5000)
    later = clock.tick(now_ms=1000)  # wall clock jumped backwards
    assert later.to_tuple() > (5000, 0, "node-a")


def test_observe_folds_a_future_remote_timestamp_into_the_local_clock():
    clock = Clock("node-a")
    clock.tick(now_ms=1000)
    clock.observe(HLC(9000, 3, "node-b"))
    nxt = clock.tick(now_ms=1000)  # still stale locally
    assert nxt.wall_ms >= 9000
    assert nxt.node_id == "node-a", "a clock only ever emits its own node id"


def test_single_writer_projects_to_the_written_value():
    clock = Clock("laptop")
    log = OpLog()
    log.merge(make_ops(clock, "project", "p1", {"status": "blocked"}))
    assert log.project("project") == {"p1": {"status": "blocked"}}


def test_later_hlc_wins_regardless_of_merge_order():
    a = Op("laptop", 1, HLC(1000, 0, "laptop"), "project", "p1", "status", "warming")
    b = Op("phone", 1, HLC(2000, 0, "phone"), "project", "p1", "status", "blocked")

    forward, backward = OpLog(), OpLog()
    forward.merge([a, b])
    backward.merge([b, a])

    assert forward.project("project") == backward.project("project") == {"p1": {"status": "blocked"}}


def test_merge_is_idempotent():
    a = Op("laptop", 1, HLC(1000, 0, "laptop"), "project", "p1", "status", "warming")
    log = OpLog()
    log.merge([a])
    log.merge([a])  # same op again — e.g. a retried sync push
    log.merge([a])
    assert len(log) == 1
    assert log.project("project") == {"p1": {"status": "warming"}}


def test_different_fields_from_different_nodes_do_not_conflict():
    a = Op("laptop", 1, HLC(1000, 0, "laptop"), "project", "p1", "status", "warming")
    b = Op("phone", 1, HLC(1001, 0, "phone"), "project", "p1", "next_action", "call the host")
    log = OpLog()
    conflicts = log.merge([a, b])
    assert conflicts == []
    assert log.project("project") == {"p1": {"status": "warming", "next_action": "call the host"}}


def test_same_field_different_nodes_is_a_logged_conflict():
    a = Op("laptop", 1, HLC(1000, 0, "laptop"), "project", "p1", "status", "warming")
    b = Op("phone", 1, HLC(2000, 0, "phone"), "project", "p1", "status", "blocked")
    log = OpLog()
    conflicts = log.merge([a, b])
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.key == ("project", "p1", "status")
    assert c.losing_op.node_id == "laptop" and c.losing_op.value == "warming"
    assert c.winning_op.node_id == "phone" and c.winning_op.value == "blocked"


def test_same_field_same_node_sequential_edits_are_not_a_conflict():
    """A node correcting its own earlier write is just history, not a conflict."""
    a = Op("laptop", 1, HLC(1000, 0, "laptop"), "project", "p1", "status", "warming")
    b = Op("laptop", 2, HLC(2000, 0, "laptop"), "project", "p1", "status", "blocked")
    log = OpLog()
    conflicts = log.merge([a, b])
    assert conflicts == []
    assert log.project("project") == {"p1": {"status": "blocked"}}


def test_convergence_under_random_merge_order():
    """The core correctness property: however ops arrive, everyone ends up
    with the same projection."""
    clocks = {n: Clock(n) for n in ["laptop", "phone", "hermes"]}
    ops = []
    for i in range(30):
        node = random.choice(list(clocks))
        ops += make_ops(clocks[node], "project", f"p{i % 4}", {"status": random.choice(["active", "blocked", "warming"])})

    results = []
    for _ in range(5):
        shuffled = ops[:]
        random.shuffle(shuffled)
        log = OpLog()
        # feed it in two ragged batches to also prove merge() composes
        mid = len(shuffled) // 2
        log.merge(shuffled[:mid])
        log.merge(shuffled[mid:])
        results.append(log.project("project"))

    assert all(r == results[0] for r in results), "projection must not depend on arrival order"


def test_round_trip_through_dict_serialization():
    clock = Clock("laptop")
    log = OpLog()
    log.merge(make_ops(clock, "horizon", "week", {"goal": "ship the sync layer"}))
    restored = OpLog.from_list(log.to_list())
    assert restored.project("horizon") == log.project("horizon")


def test_project_ignores_other_resources():
    clock = Clock("laptop")
    log = OpLog()
    log.merge(make_ops(clock, "project", "p1", {"status": "active"}))
    log.merge(make_ops(clock, "horizon", "week", {"goal": "x"}))
    assert "p1" not in log.project("horizon")
    assert "week" not in log.project("project")
