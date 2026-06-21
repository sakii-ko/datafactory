from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from .schema import LabelKind, Source, Viewpoint

EPISODE_META_SCHEMA = {
    "type": "object",
    "required": ["episode_id", "source", "viewpoint", "label_kind", "schema_version"],
    "additionalProperties": True,
    "properties": {
        "episode_id": {"type": "string", "minLength": 1},
        "source": {"enum": [s.value for s in Source]},
        "viewpoint": {"enum": [v.value for v in Viewpoint]},
        "label_kind": {"enum": [l.value for l in LabelKind]},
        "scene_id": {"type": "string"},
        "character_id": {"type": "string"},
        "fps": {"type": "number", "exclusiveMinimum": 0},
        "resolution": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
        "seed": {"type": "integer"},
        "coord_frame": {"type": "string"},
        "schema_version": {"type": "integer", "minimum": 1},
        "created_at": {"type": "string"},
        "extra": {"type": "object"},
        "num_steps": {"type": "integer", "minimum": 0},
    },
}


def validate_meta(meta: dict) -> None:
    jsonschema.validate(meta, EPISODE_META_SCHEMA)


def write_meta(path: Path, meta: dict) -> None:
    validate_meta(meta)
    Path(path).write_text(json.dumps(meta, indent=2, sort_keys=True))


def read_meta(path: Path) -> dict:
    meta = json.loads(Path(path).read_text())
    validate_meta(meta)
    return meta


def write_dataset_index(path: Path, episode_metas: list[dict]) -> dict:
    """JSONL index over episodes + bucket counts by (viewpoint, label_kind)."""
    path = Path(path)
    buckets: dict[str, int] = {}
    with path.open("w") as f:
        for m in episode_metas:
            validate_meta(m)
            f.write(json.dumps(m, sort_keys=True) + "\n")
            key = f"{m['viewpoint']}/{m['label_kind']}"
            buckets[key] = buckets.get(key, 0) + 1
    summary = {"episodes": len(episode_metas), "buckets": buckets}
    path.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    return summary
