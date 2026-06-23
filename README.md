# datafactory

World-model data farm — batch generation of action-labeled first/third-person video
for training interactive world models (Matrix-Game-3.0 style). UE5 high-fidelity
synthetic data is the primary route.

- **What & why**: see [`SPEC.md`](SPEC.md).
- **How Matrix-Game 3.0 makes its data** (primary-source teardown): [`docs/matrix-game-3-data-system.md`](docs/matrix-game-3-data-system.md).
- **Buildable implementation guide**: [`docs/implementation-guide.md`](docs/implementation-guide.md).

## Layout

```
datafarm/        engine-agnostic core (Python): schema, pose, action, scenes, assets, writers, qa, orchestrator
datafarm/backends/  capture backends: unrealzoo (research track), ue/TickCapture (own-content track), mock, video/aaa (stubs)
datafarm/farm/   multi-instance EnvPool supervisor (warm env per GPU/port, crash-recovery, level-affinity)
content/         scene registry (content/*.toml) — add a scene = add a [[scene]] entry
ue/              UE5 side: TickCapture C++ plugin + minimal project (own-content track)
tests/           pytest — core runs on CPU/H100; UE/UnrealZoo render runs on the A6000 farm (duan78)
docs/            research + design (see docs/unrealzoo-backend.md for the farm)
scripts/         committed helpers (env setup)
scratch/         local-only, never committed (.gitignore)
```

## Two tracks
- **Research track (`backend=unrealzoo`)** — primary content: run UnrealZoo's cooked UE5.6 scene
  binaries (100+ photoreal scenes) headless, drive a BP_Character along navmesh paths, capture FPV
  over UnrealCV. Multi-GPU farm fans out one warm env per A6000. Research-only assets.
- **Own-content track (`backend=ue`)** — TickCapture plugin in scenes we own the source of (.umap),
  zero-alignment in-engine capture (RGB+depth+seg). For when we author/import scenes.

## Dev

```bash
uv venv .venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

## Status

The data sample is the Matrix-Game-3.0 tuple `D_t = (RGB, player pose, camera 6-DoF,
6-dim action)`, captured tick-synchronized. Build progresses by phase (`SPEC.md §8`).

**Working & tested (74 tests):**
- Engine-agnostic core: schema/pose/action, scenes registry, manifest/writers/qa, assets
  catalog, MockBackend, orchestrator, CLI. `datafarm run --backend mock` produces a dataset.
- **UnrealZoo research track (validated on 8×A6000)**: cooked UE5.6 scene binaries run headless
  (`xvfb` + `-RenderOffScreen`), a BP_Character walks navmesh paths, FPV captured over UnrealCV →
  WSAD inferred from pose deltas → QA → dataset. **Multi-GPU farm** (`datafarm/farm` EnvPool) fans
  out one warm env per GPU (`-graphicsadapter`, auto-discovered), with crash-relaunch + level-affinity
  scheduling. Validated: 8-GPU/64-ep run (48 kept, 0 failed); navmesh policy yields ~100% (8/8).
- **TickCapture own-content track**: headless UE produces real action-labeled FPV/TPV video
  (`ue/DataFarmCapture`), `datafarm run --backend ue` end-to-end.

Run the farm:
```bash
datafarm run --backend unrealzoo --scenes uz_containeryard,uz_suburb,... \
  --gpus auto --envs 8 --binary <pkg>/UnrealZoo_UE5_6.sh --episodes 48
```
See [`docs/unrealzoo-backend.md`](docs/unrealzoo-backend.md). Deferred: clean headless segmentation,
VideoIngest (P9), AAA recording (research-only stub).
