from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import numpy as np

from .pose import CoordFrame, Pose6DoF

ACTION_KEYS = ("forward", "back", "left", "right", "jump", "attack")
SCHEMA_VERSION = 1


class Viewpoint(str, Enum):
    FPV = "fpv"
    TPV = "tpv"


class LabelKind(str, Enum):
    PRECISE_ACTION = "precise_action"  # engine ground truth (UE/AAA)
    VIDEO_ONLY = "video_only"          # no actions, or pose-inferred only


class Source(str, Enum):
    UE = "ue"
    UNREALZOO = "unrealzoo"
    MOCK = "mock"
    VIDEO = "video"
    AAA = "aaa"


@dataclass(eq=False)
class Action:
    keys: np.ndarray  # (6,) in {0,1}, order = ACTION_KEYS

    def __post_init__(self):
        self.keys = np.asarray(self.keys, np.uint8).reshape(len(ACTION_KEYS))

    def __getattr__(self, name):
        if name in ACTION_KEYS:
            return int(self.keys[ACTION_KEYS.index(name)])
        raise AttributeError(name)

    def __eq__(self, o):
        return isinstance(o, Action) and np.array_equal(self.keys, o.keys)

    __hash__ = None

    def to_list(self) -> list[int]:
        return [int(v) for v in self.keys]

    @classmethod
    def zero(cls) -> "Action":
        return cls(np.zeros(len(ACTION_KEYS), np.uint8))

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        return cls(np.array([d.get(k, 0) for k in ACTION_KEYS], np.uint8))


@dataclass(eq=False)
class FrameRef:
    path: str | None = None       # relative to episode dir
    array: np.ndarray | None = None  # HxWx3 uint8, optional in-memory

    @property
    def has_data(self) -> bool:
        return self.array is not None

    def __eq__(self, o):
        return isinstance(o, FrameRef) and self.path == o.path and np.array_equal(self.array, o.array)

    __hash__ = None


@dataclass
class Step:
    index: int
    t: float
    rgb: FrameRef
    player_pose: Pose6DoF
    camera_pose: Pose6DoF
    action: Action
    depth: FrameRef | None = None
    seg: FrameRef | None = None

    def to_row(self) -> dict:
        pp, cp = self.player_pose, self.camera_pose
        row = {"index": self.index, "t": self.t, "rgb": self.rgb.path}
        row.update({f"player_{a}": float(v) for a, v in zip("xyz", pp.position)})
        row.update({f"player_q{a}": float(v) for a, v in zip("wxyz", pp.rotation)})
        row.update({f"cam_{a}": float(v) for a, v in zip("xyz", cp.position)})
        row.update({f"cam_q{a}": float(v) for a, v in zip("wxyz", cp.rotation)})
        row.update({k: int(v) for k, v in zip(ACTION_KEYS, self.action.keys)})
        if self.depth:
            row["depth"] = self.depth.path
        if self.seg:
            row["seg"] = self.seg.path
        return row


@dataclass
class EpisodeMeta:
    episode_id: str
    source: Source
    viewpoint: Viewpoint
    label_kind: LabelKind
    scene_id: str = ""
    character_id: str = ""
    fps: float = 16.0
    resolution: tuple[int, int] = (1280, 720)
    seed: int = 0
    coord_frame: CoordFrame = CoordFrame.CANON_RH_M
    schema_version: int = SCHEMA_VERSION
    created_at: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "source": self.source.value,
            "viewpoint": self.viewpoint.value,
            "label_kind": self.label_kind.value,
            "scene_id": self.scene_id,
            "character_id": self.character_id,
            "fps": self.fps,
            "resolution": list(self.resolution),
            "seed": self.seed,
            "coord_frame": self.coord_frame.value,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EpisodeMeta":
        return cls(
            episode_id=d["episode_id"],
            source=Source(d["source"]),
            viewpoint=Viewpoint(d["viewpoint"]),
            label_kind=LabelKind(d["label_kind"]),
            scene_id=d.get("scene_id", ""),
            character_id=d.get("character_id", ""),
            fps=d.get("fps", 16.0),
            resolution=tuple(d.get("resolution", (1280, 720))),
            seed=d.get("seed", 0),
            coord_frame=CoordFrame(d.get("coord_frame", CoordFrame.CANON_RH_M.value)),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            created_at=d.get("created_at", ""),
            extra=d.get("extra", {}),
        )


@dataclass
class Episode:
    meta: EpisodeMeta
    steps: list[Step] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.steps)
