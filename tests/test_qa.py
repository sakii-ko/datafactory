import numpy as np

from datafarm.qa import (
    QAConfig,
    assess,
    displacement_ratio,
    median_speed,
    redundant_frames,
)

from .conftest import make_episode


def test_redundant_frames():
    a = np.zeros((4, 4, 3), np.uint8)
    b = np.full((4, 4, 3), 200, np.uint8)
    frames = [a, a.copy(), b, b.copy(), a]
    assert redundant_frames(frames, eps=0.5) == [1, 3]


def test_displacement_ratio_uniform():
    pos = np.array([[i, 0, 0] for i in range(10)], float)
    assert np.isclose(displacement_ratio(pos), 1.0)


def test_displacement_ratio_spike():
    pos = np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0], [100, 0, 0]], float)
    assert displacement_ratio(pos) > 20


def test_median_speed():
    pos = np.array([[i, 0, 0] for i in range(5)], float)  # 1 unit/step
    assert np.isclose(median_speed(pos, fps=16.0), 16.0)


def test_assess_good_episode():
    r = assess(make_episode(n=10))
    assert r["kept"] and not r["reasons"]
    assert np.isclose(r["stats"]["median_speed"], 16.0)


def test_assess_too_static():
    r = assess(make_episode(n=10, static=True))
    assert not r["kept"] and "too_static" in r["reasons"]


def test_assess_too_few_steps():
    r = assess(make_episode(n=3), cfg=QAConfig(min_steps=8))
    assert "too_few_steps" in r["reasons"]
