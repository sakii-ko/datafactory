from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..action import infer_actions
from ..pose import CoordFrame, Pose6DoF
from ..schema import (
    Action,
    Episode,
    EpisodeMeta,
    FrameRef,
    LabelKind,
    Source,
    Step,
    Viewpoint,
)
from .base import BackendStatus, CaptureBackend, EpisodePlan, JobSpec, default_plan


@dataclass
class UnrealZooConfig:
    host: str = "127.0.0.1"
    port: int = 9000
    cam_id: int = 0
    speed: float = 60.0          # cm/step forward
    yaw_jitter: float = 0.06     # rad/step heading wander
    action_deadzone: float = 0.01  # m/frame (poses normalized to CANON_RH_M before inference)


def _yaw_quat(yaw: float) -> np.ndarray:
    return np.array([np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)])


class UnrealZooBackend(CaptureBackend):
    """Capture from a running UnrealZoo env (its scene binary + baked-in UnrealCV server,
    launched headless via scripts/unrealzoo_launch.sh). Drives the camera on a forward-wander
    flythrough and grabs RGB + pose per step. Research-only content (purchased UE Marketplace
    assets, packaged binaries — do not redistribute / not for a shipped commercial model)."""

    name = "unrealzoo"

    def __init__(self, config: UnrealZooConfig | None = None):
        self.cfg = config or UnrealZooConfig()
        self._client = None

    def _connect(self):
        from unrealcv import Client
        if self._client is None or not self._client.isconnected():
            self._client = Client((self.cfg.host, self.cfg.port))
            self._client.connect()
            if not self._client.isconnected():
                raise RuntimeError(f"cannot connect to UnrealCV {self.cfg.host}:{self.cfg.port}")
        return self._client

    def plan(self, job: JobSpec) -> list[EpisodePlan]:
        return default_plan(job)

    def _location(self, c) -> np.ndarray:
        return np.array([float(x) for x in c.request(f"vget /camera/{self.cfg.cam_id}/location").split()])

    def _yaw(self, c) -> float:
        return float(c.request(f"vget /camera/{self.cfg.cam_id}/rotation").split()[1])  # pitch yaw roll

    def capture(self, plan: EpisodePlan, out_root: Path, gpu: int | None = None) -> Episode:
        from PIL import Image
        from ..writers import write_episode

        c = self._connect()
        rng = np.random.default_rng(plan.seed)
        cam = self.cfg.cam_id
        loc = self._location(c)
        yaw = np.deg2rad(self._yaw(c))

        steps = []
        for i in range(plan.steps):
            yaw += float(rng.normal(0, self.cfg.yaw_jitter))
            loc = loc + self.cfg.speed * np.array([np.cos(yaw), np.sin(yaw), 0.0])
            c.request(f"vset /camera/{cam}/location {loc[0]:.2f} {loc[1]:.2f} {loc[2]:.2f}")
            c.request(f"vset /camera/{cam}/rotation 0 {np.rad2deg(yaw):.2f} 0")
            png = c.request(f"vget /camera/{cam}/lit png")
            arr = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
            pose = Pose6DoF(loc.copy(), _yaw_quat(yaw), CoordFrame.UE_LEFT_CM)
            steps.append(Step(i, i / plan.fps, FrameRef(array=arr), pose, pose, Action.zero()))

        if len(steps) > 1:
            acts = infer_actions(
                [s.player_pose.to(CoordFrame.CANON_RH_M) for s in steps],
                [s.camera_pose.to(CoordFrame.CANON_RH_M) for s in steps],
                deadzone=self.cfg.action_deadzone,
            )
            for s, a in zip(steps, acts):
                s.action = a

        h, w = (steps[0].rgb.array.shape[:2] if steps else (plan.resolution[1], plan.resolution[0]))
        meta = EpisodeMeta(
            episode_id=plan.episode_id, source=Source.UNREALZOO, viewpoint=Viewpoint.FPV,
            label_kind=LabelKind.PRECISE_ACTION, scene_id=plan.scene_id or plan.map,
            fps=plan.fps, resolution=(w, h), seed=plan.seed,
            coord_frame=CoordFrame.UE_LEFT_CM, extra={"license": "research-only"},
        )
        ep = Episode(meta, steps)
        write_episode(ep, out_root)
        return ep

    def healthcheck(self) -> BackendStatus:
        try:
            c = self._connect()
            ok = bool(c.request("vget /unrealcv/status"))
            return BackendStatus(ok, f"UnrealCV {self.cfg.host}:{self.cfg.port} ok" if ok else "no status")
        except Exception as e:  # noqa: BLE001
            return BackendStatus(False, f"UnrealCV not reachable: {e}")
