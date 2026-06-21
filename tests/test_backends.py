import numpy as np
import pytest

from datafarm.backends.aaa import AAABackend
from datafarm.backends.base import JobSpec
from datafarm.backends.mock import MockBackend
from datafarm.backends.video import VideoIngestBackend
from datafarm.schema import Viewpoint
from datafarm.writers import read_episode


def _plan(steps=12, res=(32, 32), vp=Viewpoint.TPV, seed=7):
    from datafarm.backends.base import EpisodePlan
    return EpisodePlan("ep", seed, vp, steps, 16.0, res)


def test_default_plan_count_and_viewpoints():
    job = JobSpec(name="j", num_episodes=4, viewpoints=(Viewpoint.FPV, Viewpoint.TPV))
    plans = MockBackend().plan(job)
    assert len(plans) == 4
    assert [p.viewpoint for p in plans] == [Viewpoint.FPV, Viewpoint.TPV, Viewpoint.FPV, Viewpoint.TPV]
    assert len({p.seed for p in plans}) == 4  # distinct seeds


def test_mock_determinism(tmp_path):
    b = MockBackend()
    e1 = b.capture(_plan(), tmp_path / "a")
    e2 = b.capture(_plan(), tmp_path / "b")
    p1 = np.array([s.player_pose.position for s in e1.steps])
    p2 = np.array([s.player_pose.position for s in e2.steps])
    assert np.allclose(p1, p2)
    assert [s.action.to_list() for s in e1.steps] == [s.action.to_list() for s in e2.steps]
    assert np.array_equal(e1.steps[3].rgb.array, e2.steps[3].rgb.array)


def test_mock_writes_and_reads(tmp_path):
    ep = MockBackend().capture(_plan(steps=10), tmp_path)
    d = tmp_path / ep.meta.episode_id
    assert (d / "meta.json").exists() and (d / "frames" / "000000.png").exists()
    back = read_episode(d)
    assert len(back) == 10


def test_mock_actions_match_motion(tmp_path):
    # forward-moving agent facing heading -> 'forward' dominates
    ep = MockBackend().capture(_plan(steps=20), tmp_path)
    fwd = sum(s.action.forward for s in ep.steps)
    assert fwd >= 15  # nearly every step moves forward along heading


def test_mock_fpv_vs_tpv_camera(tmp_path):
    fpv = MockBackend().capture(_plan(vp=Viewpoint.FPV), tmp_path / "f")
    tpv = MockBackend().capture(_plan(vp=Viewpoint.TPV), tmp_path / "t")
    # TPV camera sits behind the player, FPV near the player
    d_fpv = np.linalg.norm(fpv.steps[5].camera_pose.position - fpv.steps[5].player_pose.position)
    d_tpv = np.linalg.norm(tpv.steps[5].camera_pose.position - tpv.steps[5].player_pose.position)
    assert d_tpv > d_fpv + 2


def test_stub_backends_raise(tmp_path):
    for B in (VideoIngestBackend, AAABackend):
        b = B()
        assert b.healthcheck().ok is False
        with pytest.raises(NotImplementedError):
            b.capture(_plan(), tmp_path)
