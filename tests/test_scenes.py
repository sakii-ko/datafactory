from pathlib import Path

import pytest

from datafarm.backends.base import JobSpec, default_plan
from datafarm.scenes import SceneCatalog
from datafarm.schema import Viewpoint

_TOML = """
[[scene]]
id = "m1"
backend = "mock"

[[scene]]
id = "u1"
backend = "ue"
map = "/Game/Scenes/A"
viewpoints = ["fpv"]
tags = ["indoor"]
license = "self"
"""


def _write(tmp_path):
    (tmp_path / "s.toml").write_text(_TOML)
    return tmp_path


def test_catalog_load_and_filter(tmp_path):
    cat = SceneCatalog(_write(tmp_path))
    assert len(cat) == 2
    assert cat.get("u1").map == "/Game/Scenes/A"
    assert cat.get("u1").viewpoints == (Viewpoint.FPV,)
    assert [s.id for s in cat.scenes(backend="ue")] == ["u1"]
    assert [s.id for s in cat.scenes(tag="indoor")] == ["u1"]


def test_resolve_unknown_raises(tmp_path):
    with pytest.raises(KeyError):
        SceneCatalog(_write(tmp_path)).resolve(["m1", "nope"])


def test_default_plan_from_scene_specs(tmp_path):
    cat = SceneCatalog(_write(tmp_path))
    job = JobSpec(name="j", num_episodes=4, scene_specs=tuple(cat.resolve(["u1"])))
    plans = default_plan(job)
    assert len(plans) == 4
    assert all(p.map == "/Game/Scenes/A" and p.scene_id == "u1" for p in plans)
    assert all(p.viewpoint == Viewpoint.FPV for p in plans)  # viewpoint from the SceneSpec


def test_repo_content_catalog_loads():
    cat = SceneCatalog(Path(__file__).resolve().parents[1] / "content")
    assert cat.get("df_testroom").backend == "ue"
    assert cat.get("df_testroom").map == "/Game/Maps/Capture"
    assert cat.get("mock").backend == "mock"
