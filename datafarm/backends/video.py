from __future__ import annotations

from pathlib import Path

from ..schema import Episode
from .base import BackendStatus, CaptureBackend, EpisodePlan, JobSpec, default_plan


class VideoIngestBackend(CaptureBackend):
    """Stub (P9): ingest real/AI video -> 6-DoF camera pose (ViPE/DPVO) -> pose-inferred
    actions + Plucker. Interface fixed; not implemented."""

    name = "video"

    def plan(self, job: JobSpec) -> list[EpisodePlan]:
        return default_plan(job)

    def capture(self, plan: EpisodePlan, out_root: Path, gpu: int | None = None) -> Episode:
        raise NotImplementedError("VideoIngestBackend pending P9 (ViPE/DPVO pose annotation).")

    def healthcheck(self) -> BackendStatus:
        return BackendStatus(False, "stub: not implemented (P9)")
