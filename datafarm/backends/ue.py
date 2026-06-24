from __future__ import annotations

import ctypes.util
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..action import infer_actions
from ..pose import CoordFrame
from ..schema import Episode
from ..writers import read_episode, write_episode
from .base import BackendStatus, CaptureBackend, EpisodePlan, JobSpec, default_plan

DEFAULT_UE_ROOT = "/root/nas/bigdata1/cjw/UnrealEngine_5.5.4"
_REPO = Path(__file__).resolve().parents[2]


@dataclass
class UEConfig:
    ue_root: str = os.environ.get("DATAFARM_UE_ROOT", DEFAULT_UE_ROOT)
    project: str = os.environ.get("DATAFARM_UE_PROJECT", str(_REPO / "ue/DataFarmCapture/DataFarmCapture.uproject"))
    map_name: str = os.environ.get("DATAFARM_UE_MAP", "/Game/Maps/Capture")
    warmup_frames: int = 6
    agent_mode: bool = True   # P7 wandering ExplorerCharacter + follow camera (default real mode)
    agent_bounds: float = 1500.0
    orbit_test: bool = True   # placeholder camera motion (used when agent_mode is False)
    infer_actions: bool = True   # derive WSAD labels from pose deltas (M-G3 §4.2)
    action_deadzone: float = 0.01  # m/frame (~1cm); poses normalized to CANON_RH_M before inference
    timeout_s: int = 600

    @property
    def editor_cmd(self) -> Path:
        return Path(self.ue_root) / "Engine/Binaries/Linux/UnrealEditor-Cmd"


def _vulkan_loader() -> str | None:
    lib = ctypes.util.find_library("vulkan")
    if lib:
        return lib
    for p in ("/lib/x86_64-linux-gnu/libvulkan.so.1", "/usr/lib/x86_64-linux-gnu/libvulkan.so.1"):
        if Path(p).exists():
            return p
    return None


class UEBackend(CaptureBackend):
    """UE5 headless tick-synchronized capture (primary route): write a render config,
    launch the TickCapture-driven editor headless, read back the episode, infer actions."""

    name = "ue"

    def __init__(self, config: UEConfig | None = None):
        self.cfg = config or UEConfig()

    def plan(self, job: JobSpec) -> list[EpisodePlan]:
        return default_plan(job)

    def capture(self, plan: EpisodePlan, out_root: Path, gpu: int | None = None) -> Episode:
        out_dir = (Path(out_root) / plan.episode_id).resolve()
        # Clear stale artifacts so the existence-based success check can't pass on a
        # prior attempt's output if UE crashes before writing this run's frames.
        shutil.rmtree(out_dir, ignore_errors=True)
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
            "agent_mode": bool(self.cfg.agent_mode),
            "agent_bounds": float(self.cfg.agent_bounds),
            "orbit_test": bool(self.cfg.orbit_test) and not self.cfg.agent_mode,
        }
        if plan.extra.get("character"):   # own-track character (TickCapture loads mesh+anim+wardrobe)
            cfg["character"] = plan.extra["character"]
        cfg_path = out_dir / "render_config.json"
        cfg_path.write_text(json.dumps(cfg, indent=2))
        scene_map = plan.map or self.cfg.map_name
        args = ["bash", str(_REPO / "scripts" / "ue_capture.sh"), str(cfg_path), scene_map]
        if gpu is not None:
            args.append(str(gpu))
        # Redirect to a file, NOT a pipe: UE forks UnrealTraceServer, which inherits the
        # stdout pipe and keeps it open after UE exits, so a piped subprocess.run would
        # block until timeout. Also judge success by artifacts, not the (often non-zero)
        # return code from a forced shutdown.
        log_path = out_dir / "ue.log"
        with open(log_path, "wb") as lf:
            proc = subprocess.run(args, stdout=lf, stderr=subprocess.STDOUT, timeout=self.cfg.timeout_s)
        if not (out_dir / "steps.csv").exists():
            tail = log_path.read_bytes()[-2000:].decode("utf-8", "replace") if log_path.exists() else ""
            raise RuntimeError(f"UE capture produced no steps.csv in {out_dir} "
                               f"(rc={proc.returncode})\n{tail}")
        ep = read_episode(out_dir)
        if len(ep) != int(plan.steps):
            raise RuntimeError(f"UE capture wrote {len(ep)} steps, expected {plan.steps} in {out_dir}")
        if self.cfg.infer_actions and len(ep) > 1:
            # movement_keys assumes canonical RH (Y=left); UE poses are ue_left_cm (Y=right),
            # so convert before inference or left/right labels invert.
            acts = infer_actions(
                [s.player_pose.to(CoordFrame.CANON_RH_M) for s in ep.steps],
                [s.camera_pose.to(CoordFrame.CANON_RH_M) for s in ep.steps],
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
        if not Path(self.cfg.project).exists():
            issues.append(f".uproject missing at {self.cfg.project} (set DATAFARM_UE_PROJECT)")
        return BackendStatus(not issues, "; ".join(issues) or f"UE ok at {self.cfg.ue_root}")
