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
    scene_specs: tuple = ()   # resolved SceneSpec objects (from SceneCatalog); overrides scenes/viewpoints
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
    map: str = ""             # backend-specific scene handle (ue: /Game/Scenes/X; unrealzoo: env)
    extra: dict = field(default_factory=dict)


@dataclass
class BackendStatus:
    ok: bool
    detail: str = ""


def default_plan(job: JobSpec) -> list[EpisodePlan]:
    plans = []
    for i in range(job.num_episodes):
        common = dict(
            episode_id=f"{job.name}_{i:05d}",
            seed=job.seed * 100003 + i,
            steps=job.steps_per_episode,
            fps=job.fps,
            resolution=tuple(job.resolution),
        )
        if job.scene_specs:  # scene-catalog-driven: viewpoint/map come from the SceneSpec
            spec = job.scene_specs[i % len(job.scene_specs)]
            vps = spec.viewpoints or (Viewpoint.TPV,)
            plans.append(EpisodePlan(
                viewpoint=vps[i % len(vps)], scene_id=spec.id, map=spec.map, **common))
        else:
            vps = job.viewpoints or (Viewpoint.TPV,)
            plans.append(EpisodePlan(
                viewpoint=vps[i % len(vps)],
                scene_id=job.scenes[i % len(job.scenes)] if job.scenes else "",
                character_id=job.characters[i % len(job.characters)] if job.characters else "",
                **common))
    return plans


class CaptureBackend(ABC):
    name = "base"
    warm_pool = False   # True => orchestrator drives this backend through a warm EnvPool (one per slot)

    @abstractmethod
    def plan(self, job: JobSpec) -> list[EpisodePlan]:
        ...

    @abstractmethod
    def capture(self, plan: EpisodePlan, out_root: Path, gpu: int | None = None) -> Episode:
        """Produce one episode under out_root/<episode_id> and return it."""
        ...

    def healthcheck(self) -> BackendStatus:
        return BackendStatus(True)

    # --- warm-pool hooks (default: stateless backend, one shared instance) ---
    def for_slot(self, gpu: int | None, port: int) -> "CaptureBackend":
        return self

    def open(self, ready_timeout: float = 180.0) -> None:
        ...

    def alive(self) -> bool:
        return True

    def close(self) -> None:
        ...
