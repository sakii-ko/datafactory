from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

Vec3 = np.ndarray
Quat = np.ndarray  # (w, x, y, z), unit Hamilton


class CoordFrame(str, Enum):
    UE_LEFT_CM = "ue_left_cm"   # left-handed, X-fwd Y-right Z-up, centimeters
    CANON_RH_M = "canon_rh_m"   # right-handed, X-fwd Y-left Z-up, meters


# 4x4 similarity mapping each frame's coords INTO the canonical frame.
_TO_CANON: dict[CoordFrame, np.ndarray] = {
    CoordFrame.CANON_RH_M: np.eye(4),
    CoordFrame.UE_LEFT_CM: np.diag([0.01, -0.01, 0.01, 1.0]),  # flip Y (LH->RH) + cm->m
}


def quat_normalize(q: Quat) -> Quat:
    q = np.asarray(q, float)
    n = np.linalg.norm(q)
    if n == 0:
        raise ValueError("zero quaternion")
    q = q / n
    return q if q[0] >= 0 else -q


def quat_to_matrix(q: Quat) -> np.ndarray:
    w, x, y, z = quat_normalize(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def matrix_to_quat(r: np.ndarray) -> Quat:
    t = np.trace(r)
    if t > 0:
        s = np.sqrt(t + 1.0) * 2
        w = 0.25 * s
        x = (r[2, 1] - r[1, 2]) / s
        y = (r[0, 2] - r[2, 0]) / s
        z = (r[1, 0] - r[0, 1]) / s
    else:
        i = int(np.argmax(np.diag(r)))
        j, k = (i + 1) % 3, (i + 2) % 3
        s = np.sqrt(1.0 + r[i, i] - r[j, j] - r[k, k]) * 2
        q = np.zeros(4)
        q[0] = (r[k, j] - r[j, k]) / s
        q[i + 1] = 0.25 * s
        q[j + 1] = (r[j, i] + r[i, j]) / s
        q[k + 1] = (r[k, i] + r[i, k]) / s
        return quat_normalize(q)
    return quat_normalize(np.array([w, x, y, z]))


def quat_mul(a: Quat, b: Quat) -> Quat:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array([
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    ])


def quat_rotate(q: Quat, v: Vec3) -> Vec3:
    return quat_to_matrix(q) @ np.asarray(v, float)


@dataclass
class Pose6DoF:
    position: Vec3
    rotation: Quat  # (w,x,y,z)
    frame: CoordFrame = CoordFrame.CANON_RH_M

    def __post_init__(self):
        self.position = np.asarray(self.position, float).reshape(3)
        self.rotation = quat_normalize(self.rotation)

    def __eq__(self, o):
        return (isinstance(o, Pose6DoF) and self.frame == o.frame
                and np.array_equal(self.position, o.position)
                and np.array_equal(self.rotation, o.rotation))

    __hash__ = None

    def matrix(self) -> np.ndarray:
        m = np.eye(4)
        m[:3, :3] = quat_to_matrix(self.rotation)
        m[:3, 3] = self.position
        return m

    @classmethod
    def from_matrix(cls, m: np.ndarray, frame: CoordFrame = CoordFrame.CANON_RH_M) -> "Pose6DoF":
        return cls(m[:3, 3].copy(), matrix_to_quat(m[:3, :3]), frame)

    @property
    def forward(self) -> Vec3:
        return quat_to_matrix(self.rotation)[:, 0]

    @property
    def right(self) -> Vec3:
        return quat_to_matrix(self.rotation)[:, 1]  # +Y; in canon frame Y is left, so right = -this

    @property
    def up(self) -> Vec3:
        return quat_to_matrix(self.rotation)[:, 2]

    def to(self, target: CoordFrame) -> "Pose6DoF":
        if target == self.frame:
            return Pose6DoF(self.position.copy(), self.rotation.copy(), self.frame)
        s = np.linalg.inv(_TO_CANON[target]) @ _TO_CANON[self.frame]
        m = s @ self.matrix() @ np.linalg.inv(s)
        return Pose6DoF.from_matrix(m, target)

    def yaw(self) -> float:
        f = self.forward
        return float(np.arctan2(f[1], f[0]))
