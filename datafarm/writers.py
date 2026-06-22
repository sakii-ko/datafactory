from __future__ import annotations

import csv
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

import numpy as np
from PIL import Image

from . import manifest
from .pose import Pose6DoF
from .schema import ACTION_KEYS, Action, Episode, EpisodeMeta, FrameRef, Step

_POSE_COLS = (
    [f"player_{a}" for a in "xyz"] + [f"player_q{a}" for a in "wxyz"]
    + [f"cam_{a}" for a in "xyz"] + [f"cam_q{a}" for a in "wxyz"]
)
_BASE_FIELDS = ["index", "t", "rgb", *_POSE_COLS, *ACTION_KEYS]


def save_frame(array: np.ndarray, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.asarray(array, np.uint8)).convert("RGB").save(path)  # enforce HxWx3


def save_depth16(array: np.ndarray, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.asarray(array).astype(np.uint16)).save(path)  # 16-bit PNG, no precision loss


def save_mask(array: np.ndarray, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    a = np.asarray(array, np.uint8)
    Image.fromarray(a if a.ndim == 2 else a[..., :3]).save(path)


def load_frame(path: Path) -> np.ndarray:
    return np.array(Image.open(path))


def encode_video(frames_dir: Path, out: Path, fps: float, codec: str = "libx264") -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found")
    if not sorted(Path(frames_dir).glob("*.png")):
        raise RuntimeError(f"no frames to encode in {frames_dir}")
    subprocess.run(  # glob input tolerates non-zero start / gaps in frame indices
        ["ffmpeg", "-y", "-framerate", str(fps), "-pattern_type", "glob",
         "-i", str(Path(frames_dir) / "*.png"), "-c:v", codec, "-pix_fmt", "yuv420p", str(out)],
        check=True, capture_output=True,
    )
    return Path(out)


def write_episode(ep: Episode, out_root: Path, video: bool = False, codec: str = "libx264") -> Path:
    d = Path(out_root) / ep.meta.episode_id
    (d / "frames").mkdir(parents=True, exist_ok=True)
    rows, has_depth, has_seg = [], False, False
    for s in ep.steps:
        if s.rgb.has_data:
            rel = f"frames/{s.index:06d}.png"
            save_frame(s.rgb.array, d / rel)
            s.rgb.path = rel
        if s.depth and s.depth.has_data:
            rel = f"depth/{s.index:06d}.png"
            save_depth16(s.depth.array, d / rel)
            s.depth.path = rel
        if s.seg and s.seg.has_data:
            rel = f"seg/{s.index:06d}.png"
            save_mask(s.seg.array, d / rel)
            s.seg.path = rel
        rows.append(s.to_row())
        has_depth |= s.depth is not None
        has_seg |= s.seg is not None
    fields = list(_BASE_FIELDS) + (["depth"] if has_depth else []) + (["seg"] if has_seg else [])
    with (d / "steps.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    manifest.write_meta(d / "meta.json", {**ep.meta.to_dict(), "num_steps": len(ep.steps)})
    if video:
        encode_video(d / "frames", d / "video.mp4", ep.meta.fps, codec)
    return d


def read_episode(d: Path) -> Episode:
    d = Path(d)
    meta = EpisodeMeta.from_dict(json.loads((d / "meta.json").read_text()))
    cf = meta.coord_frame
    steps = []
    with (d / "steps.csv").open() as f:
        for r in csv.DictReader(f):
            pp = Pose6DoF([r[f"player_{a}"] for a in "xyz"], [r[f"player_q{a}"] for a in "wxyz"], cf)
            cp = Pose6DoF([r[f"cam_{a}"] for a in "xyz"], [r[f"cam_q{a}"] for a in "wxyz"], cf)
            act = Action.from_dict({k: int(r[k]) for k in ACTION_KEYS})
            steps.append(Step(
                index=int(r["index"]), t=float(r["t"]), rgb=FrameRef(path=r["rgb"] or None),
                player_pose=pp, camera_pose=cp, action=act,
                depth=FrameRef(path=r["depth"]) if r.get("depth") else None,
                seg=FrameRef(path=r["seg"]) if r.get("seg") else None,
            ))
    return Episode(meta, steps)


def pack_tar(episode_dirs: list[Path], shard: Path) -> Path:
    with tarfile.open(shard, "w") as tar:
        for d in episode_dirs:
            d = Path(d)
            tar.add(d, arcname=d.name)
    return Path(shard)
