from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .schema import Episode


@dataclass
class QAConfig:
    min_steps: int = 8
    identical_eps: float = 0.5        # mean abs pixel diff below this = redundant frame
    max_displacement_ratio: float = 20.0  # max/median per-step displacement
    min_median_speed: float = 1e-4    # units/sec; drop near-static clips
    max_median_speed: float = 1e9


def redundant_frames(frames: list[np.ndarray], eps: float) -> list[int]:
    out, prev = [], None
    for i, f in enumerate(frames):
        f = np.asarray(f, np.float32)
        if prev is not None and float(np.abs(f - prev).mean()) <= eps:
            out.append(i)
        else:
            prev = f
    return out


def step_displacements(positions: np.ndarray) -> np.ndarray:
    if len(positions) < 2:
        return np.zeros(0)
    return np.linalg.norm(np.diff(positions, axis=0), axis=1)


def displacement_ratio(positions: np.ndarray) -> float:
    d = step_displacements(positions)
    med = float(np.median(d)) if len(d) else 0.0
    return float(d.max() / med) if med > 0 else 0.0  # degenerate (static) -> 0, caught by too_static


def median_speed(positions: np.ndarray, fps: float) -> float:
    d = step_displacements(positions)
    return float(np.median(d) * fps) if len(d) else 0.0


def assess(ep: Episode, frames: list[np.ndarray] | None = None, cfg: QAConfig = QAConfig()) -> dict:
    pos = np.array([s.player_pose.position for s in ep.steps]) if ep.steps else np.zeros((0, 3))
    ratio = displacement_ratio(pos)
    speed = median_speed(pos, ep.meta.fps)
    redundant = redundant_frames(frames, cfg.identical_eps) if frames is not None else []
    reasons = []
    if len(ep.steps) < cfg.min_steps:
        reasons.append("too_few_steps")
    if ratio > cfg.max_displacement_ratio:
        reasons.append("motion_anomaly")
    if speed < cfg.min_median_speed:
        reasons.append("too_static")
    if speed > cfg.max_median_speed:
        reasons.append("too_fast")
    return {
        "kept": not reasons,
        "reasons": reasons,
        "stats": {
            "num_steps": len(ep.steps),
            "displacement_ratio": ratio,
            "median_speed": speed,
            "redundant_frames": len(redundant),
        },
        "redundant_indices": redundant,
    }
