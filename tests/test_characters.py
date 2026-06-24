from pathlib import Path

import pytest

from datafarm.backends.base import JobSpec, default_plan
from datafarm.characters import CharacterCatalog

_TOML = """
[[character]]
id = "c1"
mesh = "/Game/X/SK_a"
anim_bp = "/Game/X/ABP_a_C"
tags = ["humanoid"]
[character.wardrobe]
top = "/Game/W/top"
"""


def _write(tmp_path):
    (tmp_path / "characters.toml").write_text(_TOML)
    return tmp_path


def test_catalog_load(tmp_path):
    c = CharacterCatalog(_write(tmp_path))
    assert len(c) == 1
    s = c.get("c1")
    assert s.mesh == "/Game/X/SK_a" and s.standard_rig == "ue5_manny"
    assert s.wardrobe == {"top": "/Game/W/top"}
    assert [x.id for x in c.characters(tag="humanoid")] == ["c1"]


def test_resolve_unknown_raises(tmp_path):
    with pytest.raises(KeyError):
        CharacterCatalog(_write(tmp_path)).resolve(["c1", "nope"])


def test_default_plan_assigns_character(tmp_path):
    c = CharacterCatalog(_write(tmp_path))
    job = JobSpec(name="j", num_episodes=2, character_specs=tuple(c.resolve(["c1"])))
    plans = default_plan(job)
    assert all(p.character_id == "c1" for p in plans)
    assert plans[0].extra["character"]["mesh"] == "/Game/X/SK_a"
    assert plans[0].extra["character"]["wardrobe"] == {"top": "/Game/W/top"}


def test_repo_characters_load():
    c = CharacterCatalog(Path(__file__).resolve().parents[1] / "content")
    assert c.get("manny").standard_rig == "ue5_manny"
