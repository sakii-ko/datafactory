import json

import jsonschema
import pytest

from datafarm.manifest import read_meta, validate_meta, write_dataset_index, write_meta


def good_meta(**kw):
    m = {
        "episode_id": "ep1", "source": "ue", "viewpoint": "fpv",
        "label_kind": "precise_action", "fps": 16.0, "resolution": [1280, 720],
        "seed": 1, "schema_version": 1,
    }
    m.update(kw)
    return m


def test_validate_good():
    validate_meta(good_meta())


@pytest.mark.parametrize("bad", [
    {"source": "nope"},
    {"viewpoint": "side"},
    {"fps": 0},
    {"episode_id": ""},
    {"resolution": [1280]},
])
def test_validate_rejects(bad):
    with pytest.raises(jsonschema.ValidationError):
        validate_meta(good_meta(**bad))


def test_meta_write_read_roundtrip(tmp_path):
    p = tmp_path / "meta.json"
    write_meta(p, good_meta())
    assert read_meta(p)["episode_id"] == "ep1"


def test_dataset_index_buckets(tmp_path):
    metas = [
        good_meta(episode_id="a", viewpoint="fpv", label_kind="precise_action"),
        good_meta(episode_id="b", viewpoint="tpv", label_kind="precise_action"),
        good_meta(episode_id="c", viewpoint="tpv", label_kind="video_only"),
    ]
    summary = write_dataset_index(tmp_path / "index.jsonl", metas)
    assert summary["episodes"] == 3
    assert summary["buckets"]["tpv/precise_action"] == 1
    assert summary["buckets"]["fpv/precise_action"] == 1
    lines = (tmp_path / "index.jsonl").read_text().strip().splitlines()
    assert len(lines) == 3 and all(json.loads(x) for x in lines)
