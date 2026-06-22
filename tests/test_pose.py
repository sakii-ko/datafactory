import numpy as np

from datafarm.pose import (
    CoordFrame,
    Pose6DoF,
    matrix_to_quat,
    quat_mul,
    quat_normalize,
    quat_rotate,
    quat_to_matrix,
)


def rand_quat(rng):
    q = rng.standard_normal(4)
    return quat_normalize(q)


def test_quat_matrix_roundtrip():
    rng = np.random.default_rng(0)
    for _ in range(50):
        q = rand_quat(rng)
        assert np.allclose(matrix_to_quat(quat_to_matrix(q)), q, atol=1e-6)


def test_quat_to_matrix_is_rotation():
    rng = np.random.default_rng(1)
    for _ in range(20):
        r = quat_to_matrix(rand_quat(rng))
        assert np.allclose(r @ r.T, np.eye(3), atol=1e-6)
        assert np.isclose(np.linalg.det(r), 1.0, atol=1e-6)


def test_quat_rotate_matches_mul():
    rng = np.random.default_rng(2)
    q = rand_quat(rng)
    v = rng.standard_normal(3)
    qv = quat_mul(quat_mul(q, np.array([0.0, *v])), np.array([q[0], -q[1], -q[2], -q[3]]))
    assert np.allclose(qv[1:], quat_rotate(q, v), atol=1e-6)


def test_pose_matrix_roundtrip():
    p = Pose6DoF([1, 2, 3], [0.5, 0.5, 0.5, 0.5])
    p2 = Pose6DoF.from_matrix(p.matrix())
    assert np.allclose(p2.position, p.position)
    assert np.allclose(p2.rotation, quat_normalize(p.rotation))


def test_coordframe_roundtrip():
    rng = np.random.default_rng(3)
    p = Pose6DoF(rng.standard_normal(3) * 100, rand_quat(rng), CoordFrame.UE_LEFT_CM)
    back = p.to(CoordFrame.CANON_RH_M).to(CoordFrame.UE_LEFT_CM)
    assert np.allclose(back.position, p.position, atol=1e-6)
    assert np.allclose(back.rotation, p.rotation, atol=1e-6)


def test_coordframe_equivariance():
    # converting a transformed point == transforming the converted point
    rng = np.random.default_rng(4)
    s = np.diag([0.01, -0.01, 0.01])  # UE coords -> canon coords (rotation part)
    pose_ue = Pose6DoF(rng.standard_normal(3) * 50, rand_quat(rng), CoordFrame.UE_LEFT_CM)
    pose_canon = pose_ue.to(CoordFrame.CANON_RH_M)
    pt = rng.standard_normal(3) * 20
    moved_ue = (pose_ue.matrix() @ np.array([*pt, 1.0]))[:3]
    lhs = s @ moved_ue
    rhs = (pose_canon.matrix() @ np.array([*(s @ pt), 1.0]))[:3]
    assert np.allclose(lhs, rhs, atol=1e-6)


def test_pose_equality_returns_bool():
    a = Pose6DoF([1, 2, 3], [1, 0, 0, 0])
    b = Pose6DoF([1, 2, 3], [1, 0, 0, 0])
    c = Pose6DoF([1, 2, 4], [1, 0, 0, 0])
    assert (a == b) is True and (a == c) is False  # must not raise on ndarray fields


def test_yaw_faces_x():
    p = Pose6DoF([0, 0, 0], [1, 0, 0, 0])  # identity -> forward +X
    assert np.isclose(p.yaw(), 0.0, atol=1e-9)
    assert np.allclose(p.forward, [1, 0, 0], atol=1e-9)
