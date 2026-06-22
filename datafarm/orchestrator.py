from __future__ import annotations

import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .backends.base import CaptureBackend, EpisodePlan, JobSpec
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
    errors: list = field(default_factory=list)


def _capture(backend: CaptureBackend, plan: EpisodePlan, out_root: Path, gpu: int | None, retries: int):
    err = None
    for _ in range(retries + 1):
        try:
            return backend.capture(plan, out_root, gpu=gpu), None
        except Exception as e:  # noqa: BLE001 — record and retry/report
            err = e
    return None, err


def run_job(
    job: JobSpec,
    backend: CaptureBackend,
    qa_cfg: QAConfig = QAConfig(),
    gpus: list[int] | None = None,
    retries: int = 1,
    workers: int = 1,
) -> RunReport:
    out_root = Path(job.out_root) / job.name
    out_root.mkdir(parents=True, exist_ok=True)
    plans = backend.plan(job)

    def gpu_for(i: int) -> int | None:
        return gpus[i % len(gpus)] if gpus else None

    # Capture in parallel (one process per worker, GPU round-robin); QA/index sequentially.
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(
                lambda ip: _capture(backend, ip[1], out_root, gpu_for(ip[0]), retries),
                enumerate(plans),
            ))
    else:
        results = [_capture(backend, p, out_root, gpu_for(i), retries) for i, p in enumerate(plans)]

    kept_metas, dropped, failed, errors = [], [], [], []
    for plan, (ep, err) in zip(plans, results):
        if ep is None:
            failed.append(plan.episode_id)
            errors.append({"episode_id": plan.episode_id, "error": str(err)[:800]})
            print(f"[datafarm] episode {plan.episode_id} failed: {err}", file=sys.stderr)
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
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.move(str(src), str(dst))

    summary = write_dataset_index(out_root / "index.jsonl", kept_metas) if kept_metas else {"buckets": {}}
    return RunReport(str(out_root), len(plans), len(kept_metas), len(dropped),
                     len(failed), summary["buckets"], dropped, failed, errors)
