import json
import sqlite3

from datafarm.assets import AssetCatalog, GateConfig


def _manifest(uid, category, **kw):
    m = {"uid": uid, "category": category, "asset_name": uid, "license": "CC0-1.0",
         "render_status": "ok", "normalized_formats": {"glb": f"derived/{uid}/{uid}.glb"}}
    m.update(kw)
    return m


def write_library(root):
    md = root / "manifests"
    md.mkdir(parents=True)
    items = [
        _manifest("good_char", "char", has_skeleton=True, standard_rig="ue5_manny", is_commercial_ok=True),
        _manifest("unrigged_char", "char", has_skeleton=False),
        _manifest("badrig_char", "char", has_skeleton=True, standard_rig=None),
        _manifest("scene_ok", "scene"),
        _manifest("scene_err", "scene", render_status="error"),
        _manifest("prop_a", "prop"),
    ]
    for m in items:
        (md / f"{m['uid']}.meta.json").write_text(json.dumps(m))


def test_category_normalization(tmp_path):
    write_library(tmp_path)
    cat = AssetCatalog(library_root=tmp_path)
    assert cat.get("good_char").category == "character"


def test_character_gating(tmp_path):
    write_library(tmp_path)
    cat = AssetCatalog(library_root=tmp_path)
    gated = [a.uid for a in cat.characters()]
    assert gated == ["good_char"]                       # unrigged + bad-rig filtered
    assert len(cat.characters(gated=False)) == 3


def test_scene_gating(tmp_path):
    write_library(tmp_path)
    cat = AssetCatalog(library_root=tmp_path)
    assert [a.uid for a in cat.scenes()] == ["scene_ok"]  # error status filtered


def test_license_allowlist(tmp_path):
    write_library(tmp_path)
    cat = AssetCatalog(library_root=tmp_path, gate_cfg=GateConfig(license_allowlist={"MIT"}))
    assert cat.scenes() == []                            # CC0 not in allowlist


def test_local_catalog_and_override(tmp_path):
    write_library(tmp_path)
    toml = tmp_path / "catalog.toml"
    toml.write_text(
        '[[scene]]\nuid="scene_ok"\nname="Local City"\npath="/Game/Maps/City"\n'
        'license="ue-eula"\nsource="local"\n\n'
        '[[character]]\nuid="quantum_01"\nname="Quantum"\nhas_skeleton=true\n'
        'standard_rig="ue5_manny"\nlicense="fab"\n'
    )
    cat = AssetCatalog(library_root=tmp_path, local_catalog=toml)
    assert cat.get("scene_ok").source == "local"         # local override wins
    assert "quantum_01" in [a.uid for a in cat.characters()]


def test_sqlite_fallback(tmp_path):
    db = tmp_path / "library.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE assets (uid TEXT, category TEXT, has_skeleton INT, "
                "standard_rig TEXT, license TEXT, render_status TEXT, normalized_formats TEXT)")
    con.execute("INSERT INTO assets VALUES (?,?,?,?,?,?,?)",
                ("c1", "char", 1, "ue5_manny", "CC0-1.0", "ok", json.dumps({"glb": "c1.glb"})))
    con.commit()
    con.close()
    cat = AssetCatalog(library_root=tmp_path)
    assert cat.get("c1").path == "c1.glb" and cat.get("c1").category == "character"
    assert [a.uid for a in cat.characters()] == ["c1"]
