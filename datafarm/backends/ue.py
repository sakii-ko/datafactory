from __future__ import annotations

import ctypes.util
import os
from dataclasses import dataclass
from pathlib import Path

from ..schema import Episode
from .base import BackendStatus, CaptureBackend, EpisodePlan, JobSpec, default_plan

DEFAULT_UE_ROOT = "/root/nas/bigdata1/cjw/UnrealEngine_5.5.4"


@dataclass
class UEConfig:
    ue_root: str = os.environ.get("DATAFARM_UE_ROOT", DEFAULT_UE_ROOT)
    project: str = os.environ.get("DATAFARM_UE_PROJECT", "")
    map_name: str = os.environ.get("DATAFARM_UE_MAP", "")

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
        raise NotImplementedError("UEBackend.capture pending P6/P8 (TickCapture plugin + wiring).")

    def healthcheck(self) -> BackendStatus:
        issues = []
        if not self.cfg.editor_cmd.exists():
            issues.append(f"UnrealEditor-Cmd missing at {self.cfg.editor_cmd}")
        if _vulkan_loader() is None:
            issues.append("libvulkan.so.1 not found (conda install -c conda-forge vulkan-loader)")
        if not self.cfg.project:
            issues.append("DATAFARM_UE_PROJECT unset (no .uproject yet — P7)")
        return BackendStatus(not issues, "; ".join(issues) or f"UE ok at {self.cfg.ue_root}")
