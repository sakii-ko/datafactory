from __future__ import annotations

import numpy as np

from .pose import Pose6DoF
from .schema import Action

# WSAD inference: project XY position deltas onto the camera-local forward/right axes
# and threshold into discrete keys (Matrix-Game-3.0 §4.2). The movement *direction* is
# scale-invariant, but the discrete labels are NOT — `deadzone` is applied in the poses'
# native units, and left/right assume a right-handed Y-left frame. Pass poses in one
# consistent frame (canonical) and scale the deadzone to those units.


def movement_keys(delta_xy: np.ndarray, yaw: float, deadzone: float) -> np.ndarray:
    f = np.array([np.cos(yaw), np.sin(yaw)])
    r = np.array([np.sin(yaw), -np.cos(yaw)])
    df, dr = float(delta_xy @ f), float(delta_xy @ r)
    return np.array([df > deadzone, df < -deadzone, dr < -deadzone, dr > deadzone], np.uint8)


def infer_actions(
    player_poses: list[Pose6DoF],
    camera_poses: list[Pose6DoF],
    deadzone: float = 1e-3,
) -> list[Action]:
    """action[t] = movement taking frame t -> t+1; last action is zero."""
    n = len(player_poses)
    out = [Action.zero() for _ in range(n)]
    for t in range(n - 1):
        d = (player_poses[t + 1].position - player_poses[t].position)[:2]
        keys = movement_keys(d, camera_poses[t].yaw(), deadzone)
        out[t] = Action(np.concatenate([keys, [0, 0]]))  # jump/attack unknown from pose
    return out


def plucker_rays(K: np.ndarray, c2w: np.ndarray, h: int, w: int) -> np.ndarray:
    """(6,H,W) Plucker map p=(o x d, d), rays in world space."""
    u, v = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    pix = np.stack([u, v, np.ones_like(u)], -1)              # (H,W,3)
    d_cam = pix @ np.linalg.inv(K).T
    d_world = d_cam @ c2w[:3, :3].T
    d = d_world / np.linalg.norm(d_world, axis=-1, keepdims=True)
    o = np.broadcast_to(c2w[:3, 3], d.shape)
    m = np.cross(o, d)
    return np.concatenate([m, d], -1).transpose(2, 0, 1).astype(np.float32)
