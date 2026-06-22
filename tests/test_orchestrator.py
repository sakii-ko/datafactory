import json
from pathlib import Path

from datafarm.backends.base import CaptureBackend, JobSpec, default_plan
from datafarm.backends.mock import MockBackend
from datafarm.orchestrator import run_job
from datafarm.qa import QAConfig
from datafarm.schema import Viewpoint


def _job(**kw):
    base = dict(name="t", num_episodes=4, steps_per_episode=12, resolution=(32, 32), out_root="")
    base.update(kw)
    return JobSpec(**base)


def test_run_job_end_to_end(tmp_path):
    rep = run_job(_job(out_root=str(tmp_path)), MockBackend())
    assert rep.total == 4 and rep.kept == 4 and rep.failed == 0
    idx = Path(rep.out_root) / "index.jsonl"
    assert idx.exists()
    lines = idx.read_text().strip().splitlines()
    assert len(lines) == 4
    assert all("qa" in json.loads(x) for x in lines)


def test_run_job_buckets(tmp_path):
    rep = run_job(_job(out_root=str(tmp_path), viewpoints=(Viewpoint.FPV, Viewpoint.TPV)), MockBackend())
    assert rep.buckets.get("fpv/precise_action") == 2
    assert rep.buckets.get("tpv/precise_action") == 2


def test_run_job_quarantine_on_qa_fail(tmp_path):
    rep = run_job(_job(out_root=str(tmp_path)), MockBackend(), qa_cfg=QAConfig(min_steps=10_000))
    assert rep.kept == 0 and rep.dropped == 4
    assert (Path(rep.out_root) / "quarantine").is_dir()
    assert not (Path(rep.out_root) / "index.jsonl").exists()


class _Flaky(CaptureBackend):
    name = "flaky"

    def __init__(self):
        self.calls = 0

    def plan(self, job):
        return default_plan(job)

    def capture(self, plan, out_root, gpu=None):
        self.calls += 1
        raise RuntimeError("boom")


def test_run_job_failures_counted(tmp_path):
    b = _Flaky()
    rep = run_job(_job(out_root=str(tmp_path), num_episodes=2), b, retries=1)
    assert rep.failed == 2 and rep.kept == 0
    assert b.calls == 4  # 2 episodes * (1 try + 1 retry)


def test_run_job_concurrent(tmp_path):
    rep = run_job(_job(out_root=str(tmp_path), num_episodes=6), MockBackend(), workers=3)
    assert rep.total == 6 and rep.kept == 6 and rep.failed == 0
    lines = (Path(rep.out_root) / "index.jsonl").read_text().strip().splitlines()
    assert len(lines) == 6


def test_run_job_concurrent_with_gpus(tmp_path):
    rep = run_job(_job(out_root=str(tmp_path), num_episodes=4), MockBackend(), gpus=[0, 1], workers=2)
    assert rep.kept == 4
