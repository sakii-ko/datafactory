from __future__ import annotations

import ctypes.util
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..action import infer_actions
from ..schema import Episode
from ..writers import read_episode, write_episode
from .base import BackendStatus, CaptureBackend, EpisodePlan, JobSpec, default_plan

DEFAULT_UE_ROOT = "/root/nas/bigdata1/cjw/UnrealEngine_5.5.4"
_REPO = Path(__file__).resolve().parents[2]


@dataclass
class UEConfig:
    ue_root: str = os.environ.get("DATAFARM_UE_ROOT", DEFAULT_UE_ROOT)
    project: str = str(_REPO / "ue/DataFarmCapture/DataFarmCapture.uproject")
    map_name: str = os.environ.get("DATAFARM_UE_MAP", "/Game/Maps/Capture")
    warmup_frames: int = 6
    orbit_test: bool = True   # placeholder camera motion until the P7 agent drives the pawn
    infer_actions: bool = True   # derive WSAD labels from pose deltas (M-G3 §4.2)
    action_deadzone: float = 1.0  # cm/frame; UE_LEFT_CM units
    timeout_s: int = 1800

    @property
    def editor_cmd(self) -> Path:
        return Path(self.ue_root) / "Engine/Binaries/Linux/UnrealEditor-Cmd"


def _vulkan_loader() -> str | None:
    if ctypes.util.find_library("vulkan"):
        return ctypes.util.find_library("vulkan")
    for p in ("/lib/x86_64-linux-gnu/libvulkan.so.1", "/usr/lib/x86_64-linux-gnu/libvulkan.so.1"):
        if Path(p).exists():
            return p
    return None


class UEBackend(CaptureBackend):
    """UE5 headless tick-synchronized capture (primary route). capture() wiring lands
    in P8 once the TickCapture C++ plugin (P6) + content/agent (P7) exist."""

    name = "ue"

    def __init__(self, config: UEConfig | None = None):
        self.cfg = config or UEConfig()

    def plan(self, job: JobSpec) -> list[EpisodePlan]:
        return default_plan(job)

    def capture(self, plan: EpisodePlan, out_root: Path, gpu: int | None = None) -> Episode:
        out_dir = (Path(out_root) / plan.episode_id).resolve()
        (out_dir / "frames").mkdir(parents=True, exist_ok=True)
        cfg = {
            "episode_id": plan.episode_id,
            "out_dir": str(out_dir),
            "width": int(plan.resolution[0]),
            "height": int(plan.resolution[1]),
            "fps": float(plan.fps),
            "num_frames": int(plan.steps),
            "warmup_frames": int(self.cfg.warmup_frames),
            "viewpoint": plan.viewpoint.value,
            "seed": int(plan.seed),
            "orbit_test": bool(plan.extra.get("orbit_test", self.cfg.orbit_test)),
        }
        cfg_path = out_dir / "render_config.json"
        cfg_path.write_text(json.dumps(cfg, indent=2))
        args = ["bash", str(_REPO / "scripts" / "ue_capture.sh"), str(cfg_path)]
        if gpu is not None:
            args.append(str(gpu))
        subprocess.run(args, check=True, capture_output=True, timeout=self.cfg.timeout_s)
        if not (out_dir / "steps.csv").exists():
            raise RuntimeError(f"UE capture produced no steps.csv in {out_dir}")
        ep = read_episode(out_dir)
        if self.cfg.infer_actions and len(ep) > 1:
            acts = infer_actions(
                [s.player_pose for s in ep.steps],
                [s.camera_pose for s in ep.steps],
                deadzone=self.cfg.action_deadzone,
            )
            for s, a in zip(ep.steps, acts):
                s.action = a
            write_episode(ep, out_dir.parent)  # rewrite steps.csv with inferred labels
        return ep

    def healthcheck(self) -> BackendStatus:
        issues = []
        if not self.cfg.editor_cmd.exists():
            issues.append(f"UnrealEditor-Cmd missing at {self.cfg.editor_cmd}")
        if _vulkan_loader() is None:
            issues.append("libvulkan.so.1 not found (conda install -c conda-forge vulkan-loader)")
        if not self.cfg.project:
            issues.append("DATAFARM_UE_PROJECT unset (no .uproject yet — P7)")
        return BackendStatus(not issues, "; ".join(issues) or f"UE ok at {self.cfg.ue_root}")
