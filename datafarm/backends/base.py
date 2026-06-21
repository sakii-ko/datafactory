from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ..schema import Episode, Viewpoint


@dataclass
class JobSpec:
    name: str
    backend: str = "mock"
    num_episodes: int = 4
    steps_per_episode: int = 16
    fps: float = 16.0
    resolution: tuple[int, int] = (1280, 720)
    viewpoints: tuple[Viewpoint, ...] = (Viewpoint.TPV,)
    scenes: tuple[str, ...] = ()
    characters: tuple[str, ...] = ()
    seed: int = 0
    out_root: str = "runs"
    extra: dict = field(default_factory=dict)


@dataclass
class EpisodePlan:
    episode_id: str
    seed: int
    viewpoint: Viewpoint
    steps: int
    fps: float
    resolution: tuple[int, int]
    scene_id: str = ""
    character_id: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class BackendStatus:
    ok: bool
    detail: str = ""


def default_plan(job: JobSpec) -> list[EpisodePlan]:
    vps = job.viewpoints or (Viewpoint.TPV,)
    plans = []
    for i in range(job.num_episodes):
        plans.append(EpisodePlan(
            episode_id=f"{job.name}_{i:05d}",
            seed=job.seed * 100003 + i,
            viewpoint=vps[i % len(vps)],
            steps=job.steps_per_episode,
            fps=job.fps,
            resolution=tuple(job.resolution),
            scene_id=job.scenes[i % len(job.scenes)] if job.scenes else "",
            character_id=job.characters[i % len(job.characters)] if job.characters else "",
        ))
    return plans


class CaptureBackend(ABC):
    name = "base"

    @abstractmethod
    def plan(self, job: JobSpec) -> list[EpisodePlan]:
        ...

    @abstractmethod
    def capture(self, plan: EpisodePlan, out_root: Path, gpu: int | None = None) -> Episode:
        """Produce one episode under out_root/<episode_id> and return it."""
        ...

    def healthcheck(self) -> BackendStatus:
        return BackendStatus(True)
