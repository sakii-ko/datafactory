from __future__ import annotations

from pathlib import Path

from ..schema import Episode
from .base import BackendStatus, CaptureBackend, EpisodePlan, JobSpec, default_plan


class AAABackend(CaptureBackend):
    """Stub: commercial-game recording (M-G3 four-layer route). Deferred — academic
    research only, legally fraught, per-game Windows injection. Interface only."""

    name = "aaa"

    def plan(self, job: JobSpec) -> list[EpisodePlan]:
        return default_plan(job)

    def capture(self, plan: EpisodePlan, out_root: Path, gpu: int | None = None) -> Episode:
        raise NotImplementedError("AAABackend deferred (research-only; not implemented).")

    def healthcheck(self) -> BackendStatus:
        return BackendStatus(False, "stub: deferred")
