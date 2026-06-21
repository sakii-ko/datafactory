import numpy as np

from datafarm.action import infer_actions, movement_keys, plucker_rays
from datafarm.pose import Pose6DoF
from datafarm.schema import ACTION_KEYS


def test_movement_keys_cardinal():
    # facing +X (yaw=0): +X=forward, -X=back, +Y=left, -Y=right
    assert movement_keys(np.array([1.0, 0]), 0.0, 0.1).tolist() == [1, 0, 0, 0]
    assert movement_keys(np.array([-1.0, 0]), 0.0, 0.1).tolist() == [0, 1, 0, 0]
    assert movement_keys(np.array([0.0, 1]), 0.0, 0.1).tolist() == [0, 0, 1, 0]
    assert movement_keys(np.array([0.0, -1]), 0.0, 0.1).tolist() == [0, 0, 0, 1]


def test_movement_keys_deadzone():
    assert movement_keys(np.array([0.05, 0.0]), 0.0, 0.1).tolist() == [0, 0, 0, 0]


def test_movement_keys_diagonal():
    # forward-left simultaneously
    assert movement_keys(np.array([1.0, 1.0]), 0.0, 0.1).tolist() == [1, 0, 1, 0]


def test_movement_keys_rotated_frame():
    # facing +Y (yaw=90deg): moving +Y should be forward
    assert movement_keys(np.array([0.0, 1.0]), np.pi / 2, 0.1).tolist() == [1, 0, 0, 0]


def test_infer_actions_straight_line():
    poses = [Pose6DoF([i, 0, 0], [1, 0, 0, 0]) for i in range(5)]
    acts = infer_actions(poses, poses, deadzone=0.1)
    assert len(acts) == 5
    assert all(a.forward == 1 for a in acts[:-1])
    assert acts[-1].keys.tolist() == [0] * len(ACTION_KEYS)  # last is zero


def test_plucker_shape_and_unit_dirs():
    K = np.array([[100.0, 0, 32], [0, 100.0, 32], [0, 0, 1]])
    c2w = np.eye(4)
    p = plucker_rays(K, c2w, 64, 64)
    assert p.shape == (6, 64, 64)
    d = p[3:]
    norms = np.linalg.norm(d, axis=0)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_plucker_moment_orthogonal_to_dir():
    K = np.array([[80.0, 0, 16], [0, 80.0, 16], [0, 0, 1]])
    c2w = np.eye(4)
    c2w[:3, 3] = [1.0, 2.0, 3.0]
    p = plucker_rays(K, c2w, 32, 32)
    m, d = p[:3], p[3:]
    dots = (m * d).sum(0)
    assert np.allclose(dots, 0.0, atol=1e-5)
