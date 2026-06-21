from __future__ import annotations

from pathlib import Path

import numpy as np

from ..action import infer_actions
from ..pose import Pose6DoF
from ..schema import Action, Episode, EpisodeMeta, FrameRef, LabelKind, Source, Step, Viewpoint
from ..writers import write_episode
from .base import CaptureBackend, EpisodePlan, JobSpec, default_plan


def _yaw_quat(yaw: float) -> np.ndarray:
    return np.array([np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)])


def _frame(w: int, h: int, i: int, seed: int) -> np.ndarray:
    gx, gy = np.meshgrid(np.linspace(0, 1, w), np.linspace(0, 1, h))
    phase = ((seed % 97) / 97.0 + i * 0.05) % 1.0
    b = (gx + gy + phase) % 1.0
    return (np.stack([gx, gy, b], -1) * 255).astype(np.uint8)


class MockBackend(CaptureBackend):
    """Deterministic synthetic episodes for testing the skeleton without an engine."""

    name = "mock"

    def plan(self, job: JobSpec) -> list[EpisodePlan]:
        return default_plan(job)

    def capture(self, plan: EpisodePlan, out_root: Path, gpu: int | None = None) -> Episode:
        rng = np.random.default_rng(plan.seed)
        w, h = plan.resolution
        n = plan.steps
        yaw, pos, step_len = float(rng.uniform(-np.pi, np.pi)), np.zeros(3), 2.0
        ppos, cyaw = [], []
        for _ in range(n):
            yaw += float(rng.normal(0, 0.1))
            pos = pos + step_len * np.array([np.cos(yaw), np.sin(yaw), 0.0])
            ppos.append(pos.copy())
            cyaw.append(yaw)
        player = [Pose6DoF(p, _yaw_quat(y)) for p, y in zip(ppos, cyaw)]
        if plan.viewpoint == Viewpoint.TPV:
            cam = [Pose6DoF(p - 6 * np.array([np.cos(y), np.sin(y), 0]) + [0, 0, 2], _yaw_quat(y))
                   for p, y in zip(ppos, cyaw)]
        else:
            cam = [Pose6DoF(p + [0, 0, 1.7], _yaw_quat(y)) for p, y in zip(ppos, cyaw)]
        actions = infer_actions(player, cam, deadzone=0.1)
        for a in actions:
            a.keys[4] = int(rng.random() < 0.1)  # jump
            a.keys[5] = int(rng.random() < 0.1)  # attack
        steps = [
            Step(i, i / plan.fps, FrameRef(array=_frame(w, h, i, plan.seed)), player[i], cam[i], actions[i])
            for i in range(n)
        ]
        meta = EpisodeMeta(
            episode_id=plan.episode_id, source=Source.MOCK, viewpoint=plan.viewpoint,
            label_kind=LabelKind.PRECISE_ACTION, scene_id=plan.scene_id,
            character_id=plan.character_id, fps=plan.fps, resolution=(w, h), seed=plan.seed,
        )
        ep = Episode(meta, steps)
        write_episode(ep, out_root)
        return ep
