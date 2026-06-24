from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:  # python < 3.11
    import tomli as tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CharacterSpec:
    """A rigged character for the own-content (TickCapture) track: a skeletal mesh + a locomotion
    AnimBP retargeted to a standard rig, plus an optional modular wardrobe. Adding a character =
    a [[character]] entry in content/characters.toml — no code change. (UnrealZoo's own track gets
    its character variety from set_app instead; this registry is for characters we import.)"""
    id: str
    mesh: str = ""                 # UE skeletal mesh asset path (/Game/...)
    anim_bp: str = ""              # locomotion AnimBlueprint path (preferred)
    anim: str = ""                 # single AnimSequence to loop (fallback when no anim_bp)
    standard_rig: str = "ue5_manny"
    wardrobe: dict = field(default_factory=dict)   # slot -> mesh path (top/pants/shoes/hair/hat)
    url: str = ""                  # CC0 source (glTF/GLB) for autonomous fetch+ingest
    license: str = ""
    tags: tuple[str, ...] = ()
    source: str = ""


def _spec_from_toml(e: dict, source: str) -> CharacterSpec:
    return CharacterSpec(
        id=e["id"], mesh=e.get("mesh", ""), anim_bp=e.get("anim_bp", ""), anim=e.get("anim", ""),
        standard_rig=e.get("standard_rig", "ue5_manny"), wardrobe=e.get("wardrobe", {}),
        url=e.get("url", ""), license=e.get("license", ""), tags=tuple(e.get("tags", [])), source=source,
    )


class CharacterCatalog:
    """Registry of importable characters loaded from content/*.toml [[character]] (mirrors SceneCatalog)."""

    def __init__(self, content_dir: str | Path = "content"):
        self._chars: dict[str, CharacterSpec] = {}
        d = Path(content_dir)
        if d.is_dir():
            for f in sorted(d.glob("*.toml")):
                for e in tomllib.loads(f.read_text()).get("character", []):
                    self.add(_spec_from_toml(e, f.name))

    def add(self, spec: CharacterSpec) -> None:
        self._chars[spec.id] = spec

    def get(self, cid: str) -> CharacterSpec | None:
        return self._chars.get(cid)

    def resolve(self, ids: list[str]) -> list[CharacterSpec]:
        missing = [i for i in ids if i not in self._chars]
        if missing:
            raise KeyError(f"unknown character(s): {missing}")
        return [self._chars[i] for i in ids]

    def characters(self, tag: str | None = None) -> list[CharacterSpec]:
        out = [c for c in self._chars.values() if tag is None or tag in c.tags]
        return sorted(out, key=lambda c: c.id)

    def __len__(self) -> int:
        return len(self._chars)
