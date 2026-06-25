"""GameInjectBackend — capture roaming data by injecting a shipped UE game (Proton + UE4SS).

This is the real implementation behind the deferred AAA route. The injection stack lives in
``gameinject/`` (generic ``framework/`` + per-game ``games/<game>/`` adapters); this backend is the
Python side: it launches one episode via ``gameinject/framework/launch/run_episode.sh`` and parses the
UE4SS Lua agent's JSONL log + captured frames into the datafarm ``Episode`` schema.

Because *we author the action* in the Lua agent, the action label is known directly (no pose-inference),
but tick-sync and depth are best-effort under injection, so episodes are tagged ``APPROX_ACTION``.

Prerequisites (see ``gameinject/STATUS.md``): a Proton-runnable game install, a GPU-attached headless X,
Steam+Proton, and a matched UE4SS build. ``healthcheck()`` reports which are missing; ``capture()`` only
runs once the adapter's ``game.toml`` resolves a real install.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ..pose import CoordFrame, Pose6DoF
from ..schema import (Action, Episode, EpisodeMeta, FrameRef, LabelKind, Source,
                      Step, Viewpoint)
from .base import BackendStatus, CaptureBackend, EpisodePlan, JobSpec, default_plan

_REPO = Path(__file__).resolve().parents[2]
_GAMEINJECT = _REPO / "gameinject"
_LAUNCH = _GAMEINJECT / "framework" / "launch" / "run_episode.sh"


def _ue_euler_to_quat(pitch_deg: float, yaw_deg: float, roll_deg: float) -> np.ndarray:
    """UE FRotator (Pitch=Y, Yaw=Z, Roll=X, degrees, left-handed) -> (w,x,y,z). [VALIDATE on live game]"""
    p, y, r = (math.radians(a) * 0.5 for a in (pitch_deg, yaw_deg, roll_deg))
    sp, cp, sy, cy, sr, cr = math.sin(p), math.cos(p), math.sin(y), math.cos(y), math.sin(r), math.cos(r)
    # UE order: R = Yaw(Z) * Pitch(Y) * Roll(X)
    w = cr * cp * cy + sr * sp * sy
    x = sr * cp * cy - cr * sp * sy
    yq = cr * sp * cy + sr * cp * sy
    z = cr * cp * sy - sr * sp * cy
    return np.array([w, x, yq, z], float)


def _pose_from_ue(loc_cm: list[float], rot_euler: list[float]) -> Pose6DoF:
    """Build a Pose6DoF from UE's logged (location cm, FRotator deg), in UE_LEFT_CM frame.

    Downstream canon conversion uses ``CoordFrame.UE_LEFT_CM`` (cm->m + Y flip), matching the UE backend.
    """
    return Pose6DoF(np.asarray(loc_cm, float), _ue_euler_to_quat(*rot_euler), frame=CoordFrame.UE_LEFT_CM)


def load_agent_log(jsonl_path: Path, frames_dir: Path, *, depth_dir: Path | None = None,
                   fps: float = 30.0) -> list[Step]:
    """Parse the UE4SS Lua agent's JSONL (one row/frame) + captured frames into Steps.

    Reusable + unit-testable without a running game. Frame i -> ``frames_dir/<i:06d>.png`` (matched by
    the agent's ``frame`` id), action read directly from the log (we authored it).
    """
    steps: list[Step] = []
    for line in jsonl_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        i = int(row["frame"])
        rgb = frames_dir / f"{i:06d}.png"
        depth = (depth_dir / f"{i:06d}.exr") if depth_dir else None
        steps.append(Step(
            index=i,
            t=float(row.get("t", i / fps)),
            rgb=FrameRef(path=str(rgb.relative_to(frames_dir.parent)) if rgb.exists() else None),
            player_pose=_pose_from_ue(row["player_loc"], row["player_rot"]),
            camera_pose=_pose_from_ue(row["cam_loc"], row["cam_rot"]),
            action=Action(np.asarray(row["action"], np.uint8)),
            depth=FrameRef(path=str(depth.relative_to(frames_dir.parent))) if depth and depth.exists() else None,
        ))
    return steps


class GameInjectBackend(CaptureBackend):
    name = "gameinject"

    def __init__(self, game: str = "blackmyth"):
        self.game = game
        self.adapter_dir = _GAMEINJECT / "games" / game

    # -- prerequisites ------------------------------------------------------
    def _adapter(self) -> dict:
        toml_path = self.adapter_dir / "game.toml"
        if not toml_path.exists():
            return {}
        import tomllib
        return tomllib.loads(toml_path.read_text())

    def healthcheck(self) -> BackendStatus:
        a = self._adapter()
        if not a:
            return BackendStatus(False, f"no adapter at {self.adapter_dir}/game.toml")
        miss = []
        game_root = a.get("install", {}).get("game_root", "")
        if not game_root or not Path(os.path.expanduser(game_root)).exists():
            miss.append(f"game install not found ({game_root or 'unset'})")
        if not (a.get("install", {}).get("ue4ss_dir") and
                Path(os.path.expanduser(a["install"]["ue4ss_dir"])).exists()):
            miss.append("UE4SS not installed")
        import shutil
        if not (shutil.which("steam") or os.path.expanduser(a.get("proton", {}).get("proton_dir", "x")) and
                Path(os.path.expanduser(a.get("proton", {}).get("proton_dir", "/x"))).exists()):
            miss.append("Steam/Proton not set up")
        if not _LAUNCH.exists():
            miss.append("launch script missing")
        if miss:
            return BackendStatus(False, "; ".join(miss))
        return BackendStatus(True, f"{self.game}: ready")

    # -- plan / capture -----------------------------------------------------
    def plan(self, job: JobSpec) -> list[EpisodePlan]:
        plans = default_plan(job)
        for p in plans:
            p.extra = {**p.extra, "game": self.game}
        return plans

    def capture(self, plan: EpisodePlan, out_root: Path, gpu: int | None = None) -> Episode:
        hc = self.healthcheck()
        if not hc.ok:
            raise NotImplementedError(
                f"gameinject[{self.game}] not runnable yet: {hc.detail}. "
                "See gameinject/STATUS.md for the prerequisite checklist (game install + Proton + UE4SS).")
        ep_dir = out_root / plan.episode_id
        ep_dir.mkdir(parents=True, exist_ok=True)
        # launch one episode: headless X + Proton + UE4SS inject + roam + capture
        env = {**os.environ, "GI_GAME": self.game, "GI_EPISODE": plan.episode_id,
               "GI_OUT": str(ep_dir), "GI_FRAMES": str(plan.steps), "GI_FPS": str(plan.fps),
               "GI_SEED": str(plan.seed), "GI_GPU": str(gpu if gpu is not None else 0),
               "GI_W": str(plan.resolution[0]), "GI_H": str(plan.resolution[1])}
        subprocess.run(["bash", str(_LAUNCH)], env=env, check=True)
        steps = load_agent_log(ep_dir / "agent.jsonl", ep_dir / "frames",
                               depth_dir=ep_dir / "depth", fps=plan.fps)
        meta = EpisodeMeta(
            episode_id=plan.episode_id, source=Source.AAA, viewpoint=plan.viewpoint,
            label_kind=LabelKind.APPROX_ACTION, scene_id=plan.scene_id or self.game,
            fps=plan.fps, resolution=tuple(plan.resolution), seed=plan.seed,
            created_at=datetime.now(timezone.utc).isoformat(),
            extra={"game": self.game, "track": "gameinject"})
        return Episode(meta=meta, steps=steps)
