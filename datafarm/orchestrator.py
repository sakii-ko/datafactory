from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .backends.base import CaptureBackend, JobSpec
from .manifest import write_dataset_index
from .qa import QAConfig, assess


@dataclass
class RunReport:
    out_root: str
    total: int
    kept: int
    dropped: int
    failed: int
    buckets: dict = field(default_factory=dict)
    dropped_ids: list = field(default_factory=list)
    failed_ids: list = field(default_factory=list)


def gpu_env(gpu: int | None) -> dict:
    return {} if gpu is None else {"CUDA_VISIBLE_DEVICES": str(gpu)}


def run_job(
    job: JobSpec,
    backend: CaptureBackend,
    qa_cfg: QAConfig = QAConfig(),
    gpus: list[int] | None = None,
    retries: int = 1,
) -> RunReport:
    out_root = Path(job.out_root) / job.name
    out_root.mkdir(parents=True, exist_ok=True)
    plans = backend.plan(job)
    kept_metas, dropped, failed = [], [], []

    for i, plan in enumerate(plans):
        gpu = gpus[i % len(gpus)] if gpus else None
        ep = None
        for _ in range(retries + 1):
            try:
                ep = backend.capture(plan, out_root, gpu=gpu)
                break
            except Exception:
                ep = None
        if ep is None:
            failed.append(plan.episode_id)
            continue
        frames = [s.rgb.array for s in ep.steps] if all(s.rgb.has_data for s in ep.steps) else None
        qa = assess(ep, frames=frames, cfg=qa_cfg)
        meta = ep.meta.to_dict() | {"num_steps": len(ep.steps), "qa": qa}
        if qa["kept"]:
            kept_metas.append(meta)
        else:
            dropped.append(plan.episode_id)
            src, dst = out_root / plan.episode_id, out_root / "quarantine" / plan.episode_id
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))

    summary = (
        write_dataset_index(out_root / "index.jsonl", kept_metas)
        if kept_metas else {"buckets": {}}
    )
    return RunReport(str(out_root), len(plans), len(kept_metas), len(dropped),
                     len(failed), summary["buckets"], dropped, failed)
