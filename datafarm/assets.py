from __future__ import annotations

import json
import sqlite3
try:
    import tomllib
except ModuleNotFoundError:  # python < 3.11
    import tomli as tomllib
from dataclasses import dataclass, field
from pathlib import Path

CATEGORIES = ("scene", "character", "animation", "prop", "material")
_CATEGORY_ALIASES = {"char": "character", "anim": "animation"}


def _norm_category(c: str | None) -> str:
    c = (c or "other").lower()
    return _CATEGORY_ALIASES.get(c, c)


@dataclass
class Asset:
    uid: str
    category: str
    name: str = ""
    path: str = ""              # derived glb, or a UE asset path for local assets
    source: str = ""
    subcategory: str = ""
    license: str = ""
    is_commercial_ok: bool = False
    render_status: str = "ok"
    has_skeleton: bool = False
    standard_rig: str | None = None
    tags: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @classmethod
    def from_manifest(cls, m: dict) -> "Asset":
        return cls(
            uid=str(m["uid"]),
            category=_norm_category(m.get("category")),
            name=m.get("asset_name", ""),
            path=(m.get("normalized_formats") or {}).get("glb", "") or m.get("original_path", ""),
            source=m.get("source_site", ""),
            subcategory=m.get("subcategory", ""),
            license=m.get("license", ""),
            is_commercial_ok=bool(m.get("is_commercial_ok", False)),
            render_status=m.get("render_status", "ok"),
            has_skeleton=bool(m.get("has_skeleton", False)),
            standard_rig=m.get("standard_rig"),
            tags=m.get("tags") or [],
            meta=m,
        )

    @classmethod
    def from_local(cls, category: str, e: dict) -> "Asset":
        known = {f for f in cls.__dataclass_fields__ if f not in ("meta", "category")}
        return cls(
            category=_norm_category(category),
            meta=e,
            **{k: v for k, v in e.items() if k in known},
        )


@dataclass
class GateConfig:
    license_allowlist: set[str] | None = None   # None = allow any
    require_commercial_ok: bool = False
    require_render_ok: bool = True
    require_rigged_character: bool = True
    required_standard_rig: str | None = "ue5_manny"


def passes_gate(a: Asset, cfg: GateConfig) -> bool:
    if cfg.require_render_ok and a.render_status not in ("ok", ""):
        return False
    if cfg.license_allowlist is not None and a.license not in cfg.license_allowlist:
        return False
    if cfg.require_commercial_ok and not a.is_commercial_ok:
        return False
    if a.category == "character" and cfg.require_rigged_character:
        if not a.has_skeleton:
            return False
        if cfg.required_standard_rig and a.standard_rig != cfg.required_standard_rig:
            return False
    return True


class AssetCatalog:
    """Consume an asset-library (manifests/ or library.db) + a local catalog.toml override."""

    def __init__(self, library_root=None, local_catalog=None, gate_cfg: GateConfig = GateConfig()):
        self.gate_cfg = gate_cfg
        self._assets: dict[str, Asset] = {}
        if library_root:
            self._load_library(Path(library_root))
        if local_catalog:
            self._load_local(Path(local_catalog))  # local wins on uid clash

    def _load_library(self, root: Path):
        mdir = root / "manifests"
        loaded = False
        if mdir.is_dir():
            for p in sorted(mdir.glob("*.meta.json")):
                try:
                    a = Asset.from_manifest(json.loads(p.read_text()))
                except (json.JSONDecodeError, KeyError):
                    continue
                self._assets[a.uid] = a
                loaded = True
        db = root / "library.db"
        if db.is_file() and not loaded:
            con = sqlite3.connect(db)
            con.row_factory = sqlite3.Row
            try:
                for row in con.execute("SELECT * FROM assets"):
                    m = {k: row[k] for k in row.keys()}
                    for j in ("normalized_formats", "tags", "textures"):
                        if isinstance(m.get(j), str):
                            try:
                                m[j] = json.loads(m[j])
                            except json.JSONDecodeError:
                                pass
                    a = Asset.from_manifest(m)
                    self._assets[a.uid] = a
            finally:
                con.close()

    def _load_local(self, path: Path):
        data = tomllib.loads(Path(path).read_text())
        for cat in CATEGORIES:
            for e in data.get(cat, []):
                a = Asset.from_local(cat, e)
                self._assets[a.uid] = a

    def assets(self, category: str | None = None, gated: bool = True) -> list[Asset]:
        out = [a for a in self._assets.values() if category is None or a.category == category]
        if gated:
            out = [a for a in out if passes_gate(a, self.gate_cfg)]
        return sorted(out, key=lambda a: a.uid)

    def scenes(self, **kw) -> list[Asset]:
        return self.assets("scene", **kw)

    def characters(self, **kw) -> list[Asset]:
        return self.assets("character", **kw)

    def animations(self, **kw) -> list[Asset]:
        return self.assets("animation", **kw)

    def get(self, uid: str) -> Asset | None:
        return self._assets.get(uid)

    def __len__(self) -> int:
        return len(self._assets)
