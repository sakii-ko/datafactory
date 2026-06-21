# datafactory

World-model data farm — batch generation of action-labeled first/third-person video
for training interactive world models (Matrix-Game-3.0 style). UE5 high-fidelity
synthetic data is the primary route.

- **What & why**: see [`SPEC.md`](SPEC.md).
- **How Matrix-Game 3.0 makes its data** (primary-source teardown): [`docs/matrix-game-3-data-system.md`](docs/matrix-game-3-data-system.md).
- **Buildable implementation guide**: [`docs/implementation-guide.md`](docs/implementation-guide.md).

## Layout

```
datafarm/        engine-agnostic core (Python): schema, pose, action, assets, writers, qa, orchestrator
datafarm/backends/  capture backends: mock (done), ue (primary), video/aaa (stubs)
ue/              UE5 side: TickCapture C++ plugin + minimal project (primary deliverable)
tests/           pytest — P1–P4 run on CPU/H100; UE render tests run on the A6000/L40S farm
docs/            research + design
scripts/         committed helpers (env setup)
scratch/         local-only, never committed (.gitignore)
```

## Dev

```bash
uv venv .venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

## Status

Core (`schema`/`pose`/`action`) implemented and tested. Build progresses by phase per
`SPEC.md §8`; see the task list. The data sample is the Matrix-Game-3.0 tuple
`D_t = (RGB, player pose, camera 6-DoF, 6-dim action)`, captured tick-synchronized.
