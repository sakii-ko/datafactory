# Batch-import every character under DF_BATCH_ROOT/<id>/ (character.fbx [+ walking.fbx]) in ONE
# editor session, and write a combined manifest [{id, mesh, anim}, ...] to DF_BATCH_MANIFEST.
#   DF_BATCH_ROOT=assets_in/mixamo  DF_BATCH_MANIFEST=/tmp/m.json
#   UnrealEditor-Cmd <ABS proj> -run=pythonscript -script=import_characters_batch.py -unattended -RenderOffscreen
import glob
import json
import os

import unreal

root = os.environ["DF_BATCH_ROOT"]
out = os.environ["DF_BATCH_MANIFEST"]
tools = unreal.AssetToolsHelpers.get_asset_tools()


def _task(fn, dest, ui):
    t = unreal.AssetImportTask()
    t.filename, t.destination_path = fn, dest
    t.automated = t.save = t.replace_existing = True
    t.options = ui
    return t


results = []
for d in sorted(glob.glob(os.path.join(root, "*"))):
    cid = os.path.basename(d)
    char = os.path.join(d, "character.fbx")
    walk = os.path.join(d, "walking.fbx")
    if not os.path.exists(char) or not os.path.exists(walk):
        continue   # only fully-fetched characters (mesh + walk anim)
    dest = f"/Game/DataFarm/Characters/{cid}"
    mui = unreal.FbxImportUI()
    mui.import_mesh = True
    mui.import_as_skeletal = True
    mui.import_animations = False
    mui.import_materials = True
    mui.import_textures = True
    mui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    tools.import_asset_tasks([_task(char, dest, mui)])
    skel = mesh = None
    for p in unreal.EditorAssetLibrary.list_assets(dest, recursive=True) or []:
        cls = str(unreal.EditorAssetLibrary.find_asset_data(p).asset_class_path.asset_name)
        if cls == "Skeleton":
            skel = p
        elif cls == "SkeletalMesh":
            mesh = p
    anim = None
    if os.path.exists(walk) and skel:
        aui = unreal.FbxImportUI()
        aui.import_mesh = False
        aui.import_as_skeletal = True
        aui.import_animations = True
        aui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_ANIMATION)
        aui.set_editor_property("skeleton", unreal.EditorAssetLibrary.load_asset(skel))
        t = _task(walk, dest + "/Anim", aui)
        tools.import_asset_tasks([t])
        ap = [str(x) for x in t.imported_object_paths]
        anim = ap[0] if ap else None
    unreal.EditorAssetLibrary.save_directory(dest)
    results.append({"id": cid, "mesh": mesh, "anim": anim})
    unreal.log(f"[batch] {cid}: mesh={mesh} anim={anim}")

with open(out, "w") as f:
    json.dump(results, f, indent=2)
unreal.log(f"[batch] imported {len(results)} characters -> {out}")
