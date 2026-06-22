from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .schema import LabelKind, Viewpoint


@dataclass
class SceneSpec:
    """A renderable scene + which backend renders it. Adding content = adding one of
    these (a [[scene]] entry in content/*.toml), no core code change."""
    id: str
    backend: str                       # "ue" | "unrealzoo" | "mock"
    map: str = ""                      # ue: /Game/Scenes/X ; unrealzoo: env/binary name
    viewpoints: tuple[Viewpoint, ...] = (Viewpoint.FPV, Viewpoint.TPV)
    label_kind: LabelKind = LabelKind.PRECISE_ACTION
    license: str = "research-only"
    tags: tuple[str, ...] = ()
    params: dict = field(default_factory=dict)   # backend-specific extras
    source: str = ""


def _spec_from_toml(e: dict, source: str) -> SceneSpec:
    return SceneSpec(
        id=e["id"],
        backend=e["backend"],
        map=e.get("map", ""),
        viewpoints=tuple(Viewpoint(v) for v in e.get("viewpoints", ["fpv", "tpv"])),
        label_kind=LabelKind(e.get("label_kind", "precise_action")),
        license=e.get("license", "research-only"),
        tags=tuple(e.get("tags", [])),
        params=e.get("params", {}),
        source=source,
    )


class SceneCatalog:
    """Registry of scenes loaded from content/*.toml (each may hold many [[scene]])."""

    def __init__(self, content_dir: str | Path = "content"):
        self._scenes: dict[str, SceneSpec] = {}
        d = Path(content_dir)
        if d.is_dir():
            for f in sorted(d.glob("*.toml")):
                for e in tomllib.loads(f.read_text()).get("scene", []):
                    self.add(_spec_from_toml(e, f.name))

    def add(self, spec: SceneSpec) -> None:
        self._scenes[spec.id] = spec

    def get(self, scene_id: str) -> SceneSpec | None:
        return self._scenes.get(scene_id)

    def resolve(self, ids: list[str]) -> list[SceneSpec]:
        missing = [i for i in ids if i not in self._scenes]
        if missing:
            raise KeyError(f"unknown scene(s): {missing}")
        return [self._scenes[i] for i in ids]

    def scenes(self, backend: str | None = None, tag: str | None = None) -> list[SceneSpec]:
        out = [s for s in self._scenes.values()
               if (backend is None or s.backend == backend)
               and (tag is None or tag in s.tags)]
        return sorted(out, key=lambda s: s.id)

    def __len__(self) -> int:
        return len(self._scenes)
