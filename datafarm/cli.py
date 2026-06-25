from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .backends.aaa import AAABackend
from .backends.base import JobSpec
from .backends.mock import MockBackend
from .backends.unrealzoo import UnrealZooBackend
from .backends.video import VideoIngestBackend
from .orchestrator import run_job
from .scenes import SceneCatalog
from .schema import Viewpoint

_REPO = Path(__file__).resolve().parents[1]
_BACKENDS = {"mock": MockBackend, "video": VideoIngestBackend, "aaa": AAABackend,
             "unrealzoo": UnrealZooBackend}


def _backend(name: str):
    if name == "ue":
        from .backends.ue import UEBackend
        return UEBackend()
    if name == "gameinject" or name.startswith("gameinject:"):
        from .backends.gameinject import GameInjectBackend
        game = name.split(":", 1)[1] if ":" in name else "blackmyth"
        return GameInjectBackend(game=game)
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
    r.add_argument("--gpus", default="", help="comma vulkan-adapter indices, or 'auto' to discover A6000s")
    r.add_argument("--workers", type=int, default=1)
    r.add_argument("--scenes", default="", help="comma-separated scene ids from the content catalog")
    r.add_argument("--characters", default="", help="comma-separated character ids (content/characters.toml; own-track)")
    r.add_argument("--content", default=str(_REPO / "content"), help="content catalog dir")
    r.add_argument("--binary", default="", help="UnrealZoo launcher .sh path (warm-pool fan-out)")
    r.add_argument("--envs", type=int, default=0, help="warm envs for fan-out; 0 => len(gpus)")
    r.add_argument("--ready-timeout", type=float, default=180.0)

    h = sub.add_parser("healthcheck", help="check a backend's readiness")
    h.add_argument("--backend", default="ue")

    args = p.parse_args(argv)

    if args.cmd == "healthcheck":
        st = _backend(args.backend).healthcheck()
        print(json.dumps({"backend": args.backend, "ok": st.ok, "detail": st.detail}, indent=2))
        return 0 if st.ok else 1

    w, h = (int(x) for x in args.res.lower().split("x"))
    backend = args.backend
    scene_specs = ()
    if args.scenes:
        specs = SceneCatalog(args.content).resolve([s.strip() for s in args.scenes.split(",")])
        backends = {s.backend for s in specs}
        if len(backends) > 1:
            p.error(f"--scenes span multiple backends {backends}; run one backend at a time")
        backend = backends.pop()  # scene catalog drives the backend
        scene_specs = tuple(specs)
    character_specs = ()
    if args.characters:           # own-track: imported characters drive the ue backend
        from .characters import CharacterCatalog
        character_specs = tuple(CharacterCatalog(args.content).resolve(
            [c.strip() for c in args.characters.split(",")]))
        if backend == "mock":
            backend = "ue"
    job = JobSpec(
        name=args.name, backend=backend, num_episodes=args.episodes,
        steps_per_episode=args.steps, fps=args.fps, resolution=(w, h),
        viewpoints=tuple(Viewpoint(v.strip().lower()) for v in args.viewpoints.split(",")),
        seed=args.seed, out_root=args.out, scene_specs=scene_specs, character_specs=character_specs,
    )
    if args.gpus == "auto":                    # discover discrete-GPU vulkan adapters (skip llvmpipe)
        from .farm.pool import discover_gpu_adapters
        gpus = discover_gpu_adapters() or None
    else:
        gpus = [int(x) for x in args.gpus.split(",")] if args.gpus else None
    binary = args.binary or (scene_specs[0].params.get("binary", "") if scene_specs else "")
    workers = args.workers
    if backend == "unrealzoo" and gpus:        # --gpus (vulkan adapter indices) => warm-pool fan-out
        if not binary:
            p.error("--binary (UnrealZoo launcher .sh) is required for fan-out with --gpus")
        workers = args.envs or len(gpus)
    rep = run_job(job, _backend(backend), gpus=gpus, workers=workers,
                  binary=binary, ready_timeout=args.ready_timeout)
    print(json.dumps(asdict(rep), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
