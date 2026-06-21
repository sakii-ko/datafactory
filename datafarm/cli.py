from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .backends.aaa import AAABackend
from .backends.base import JobSpec
from .backends.mock import MockBackend
from .backends.video import VideoIngestBackend
from .orchestrator import run_job
from .schema import Viewpoint

_BACKENDS = {"mock": MockBackend, "video": VideoIngestBackend, "aaa": AAABackend}


def _backend(name: str):
    if name == "ue":
        from .backends.ue import UEBackend
        return UEBackend()
    return _BACKENDS[name]()


def main(argv=None) -> int:
    p = argparse.ArgumentParser("datafarm")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="generate a dataset")
    r.add_argument("--backend", default="mock")
    r.add_argument("--name", default="run0")
    r.add_argument("--episodes", type=int, default=4)
    r.add_argument("--steps", type=int, default=16)
    r.add_argument("--fps", type=float, default=16.0)
    r.add_argument("--res", default="1280x720")
    r.add_argument("--viewpoints", default="tpv")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--out", default="runs")
    r.add_argument("--gpus", default="")

    h = sub.add_parser("healthcheck", help="check a backend's readiness")
    h.add_argument("--backend", default="ue")

    args = p.parse_args(argv)

    if args.cmd == "healthcheck":
        st = _backend(args.backend).healthcheck()
        print(json.dumps({"backend": args.backend, "ok": st.ok, "detail": st.detail}, indent=2))
        return 0 if st.ok else 1

    w, h = (int(x) for x in args.res.lower().split("x"))
    job = JobSpec(
        name=args.name, backend=args.backend, num_episodes=args.episodes,
        steps_per_episode=args.steps, fps=args.fps, resolution=(w, h),
        viewpoints=tuple(Viewpoint(v) for v in args.viewpoints.split(",")),
        seed=args.seed, out_root=args.out,
    )
    gpus = [int(x) for x in args.gpus.split(",")] if args.gpus else None
    rep = run_job(job, _backend(args.backend), gpus=gpus)
    print(json.dumps(asdict(rep), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
