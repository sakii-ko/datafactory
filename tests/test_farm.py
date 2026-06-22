from datafarm.farm.pool import LevelQueue, slot_layout


class _P:
    def __init__(self, m):
        self.map = m
        self.extra = {}


def test_slot_layout_adapters_and_ports():
    assert slot_layout(3, [0, 2]) == [(0, 9000), (2, 9008), (0, 9016)]


def test_level_queue_affinity():
    q = LevelQueue([_P("a"), _P("a"), _P("b")])
    assert q.take("a").map == "a"      # serves the loaded level
    assert q.take("b").map == "b"
    assert q.take("a").map == "a"      # remaining "a"
    assert q.take("a") is None


def test_level_queue_retry_served_first():
    a, b = _P("x"), _P("y")
    q = LevelQueue([a, b])
    q.requeue(b)
    assert q.take("x") is b            # requeued plan jumps the line
    assert q.take("x") is a


def test_level_queue_largest_remaining_when_no_match():
    q = LevelQueue([_P("a"), _P("b"), _P("b")])
    assert q.take("missing").map == "b"   # falls back to the biggest remaining group
