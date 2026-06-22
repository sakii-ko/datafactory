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
    binary: str | None = None,
    ready_timeout: float = 180.0,
) -> RunReport:
    out_root = Path(job.out_root) / job.name
    out_root.mkdir(parents=True, exist_ok=True)
    plans = backend.plan(job)

    if getattr(backend, "warm_pool", False) and gpus:   # multi-instance fan-out (UnrealZoo)
        return _run_warmpool(backend, plans, out_root, qa_cfg, gpus, workers,
                             binary, ready_timeout, retries)

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
        else:
            _grade(ep, out_root, qa_cfg, kept_metas, dropped)

    summary = write_dataset_index(out_root / "index.jsonl", kept_metas) if kept_metas else {"buckets": {}}
    return RunReport(str(out_root), len(plans), len(kept_metas), len(dropped),
                     len(failed), summary["buckets"], dropped, failed, errors)


def _grade(ep, out_root: Path, qa_cfg: QAConfig, kept_metas: list, dropped: list) -> None:
    frames = [s.rgb.array for s in ep.steps] if all(s.rgb.has_data for s in ep.steps) else None
    qa = assess(ep, frames=frames, cfg=qa_cfg)
    if qa["kept"]:
        kept_metas.append({**ep.meta.to_dict(), "num_steps": len(ep.steps), "qa": qa})
        return
    eid = ep.meta.episode_id
    dropped.append(eid)
    src, dst = out_root / eid, out_root / "quarantine" / eid
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            shutil.rmtree(dst)
        shutil.move(str(src), str(dst))


def _run_warmpool(proto, plans, out_root, qa_cfg, gpus, workers,
                  binary, ready_timeout, retries) -> RunReport:
    import queue as _queue

    from .farm.pool import EnvPool
    n = min(workers or len(gpus), len(plans)) or 1
    pool = EnvPool(plans, proto, binary, gpus, n, out_root,
                   ready_timeout=ready_timeout, max_retries=retries + 1)
    threads = pool.start()
    kept, dropped, failed, errors, delivered, total = [], [], [], [], set(), len(plans)
    try:
        while len(delivered) < total:
            try:
                res = pool.results.get(timeout=5.0)
            except _queue.Empty:
                if not any(t.is_alive() for t in threads):
                    break   # no live env left to make progress -> reconcile leftovers below
                continue
            if res.plan.episode_id in delivered:
                continue   # defensive: one terminal result per plan
            delivered.add(res.plan.episode_id)
            if res.episode is None:
                failed.append(res.plan.episode_id)
                errors.append({"episode_id": res.plan.episode_id, "error": (res.error or "")[:800]})
                print(f"[datafarm] episode {res.plan.episode_id} failed: {res.error}", file=sys.stderr)
            else:
                _grade(res.episode, out_root, qa_cfg, kept, dropped)
        for p in plans:   # any plan stranded by dead envs -> failed
            if p.episode_id not in delivered:
                failed.append(p.episode_id)
                errors.append({"episode_id": p.episode_id, "error": "no live env produced a result"})
    finally:
        pool.shutdown()
    summary = write_dataset_index(out_root / "index.jsonl", kept) if kept else {"buckets": {}}
    return RunReport(str(out_root), total, len(kept), len(dropped),
                     len(failed), summary["buckets"], dropped, failed, errors)
