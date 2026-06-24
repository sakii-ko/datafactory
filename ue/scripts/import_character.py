# Import a rigged character (skeletal mesh + skeleton) and its animation FBXs into UE content,
# then emit a manifest the character registry can consume. Editor-time (run via UnrealEditor-Cmd).
#
#   DF_CHAR_FBX=<mesh.fbx>  DF_ANIM_FBXS=<walk.fbx,run.fbx,...>  DF_DEST=/Game/DataFarm/Characters/<id>
#   DF_CHAR_ID=<id>  [DF_MANIFEST=<out.json>]
#   UE_CMD <proj> -run=pythonscript -script=import_character.py -unattended
#
# Mixamo: download the character as FBX (with skin), and animations as FBX "Without Skin" so they
# bind to the same skeleton -> no retarget needed. (Retarget-to-ue5_manny is a later optimisation.)
import json
import os

import unreal

char_fbx = os.environ["DF_CHAR_FBX"]
anim_fbxs = [s.strip() for s in os.environ.get("DF_ANIM_FBXS", "").split(",") if s.strip()]
dest = os.environ.get("DF_DEST", "/Game/DataFarm/Characters/imported")
char_id = os.environ.get("DF_CHAR_ID", "imported")
tools = unreal.AssetToolsHelpers.get_asset_tools()


def _task(filename, destination, options):
    t = unreal.AssetImportTask()
    t.filename = filename
    t.destination_path = destination
    t.automated = True
    t.save = True
    t.replace_existing = True
    t.options = options
    return t


# --- character: skeletal mesh + skeleton (+ materials/textures) ---
mesh_ui = unreal.FbxImportUI()
mesh_ui.import_mesh = True
mesh_ui.import_as_skeletal = True
mesh_ui.import_animations = False
mesh_ui.import_materials = True
mesh_ui.import_textures = True
mesh_ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
mesh_task = _task(char_fbx, dest, mesh_ui)
tools.import_asset_tasks([mesh_task])
unreal.log(f"[char] mesh import -> {list(mesh_task.imported_object_paths)}")

skeleton = mesh = None
for p in unreal.EditorAssetLibrary.list_assets(dest, recursive=True) or []:
    cls = str(unreal.EditorAssetLibrary.find_asset_data(p).asset_class_path.asset_name)
    if cls == "Skeleton":
        skeleton = p
    elif cls == "SkeletalMesh":
        mesh = p

# --- animations onto that skeleton ---
anim_paths = []
for fb in anim_fbxs:
    a_ui = unreal.FbxImportUI()
    a_ui.import_mesh = False
    a_ui.import_as_skeletal = True
    a_ui.import_animations = True
    a_ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_ANIMATION)
    if skeleton:
        a_ui.set_editor_property("skeleton", unreal.EditorAssetLibrary.load_asset(skeleton))
    a_task = _task(fb, dest + "/Anim", a_ui)
    tools.import_asset_tasks([a_task])
    anim_paths += [str(x) for x in a_task.imported_object_paths]

unreal.EditorAssetLibrary.save_directory(dest)

manifest = {
    "id": char_id, "mesh": mesh, "skeleton": skeleton, "anims": anim_paths,
    "standard_rig": "imported", "license": os.environ.get("DF_LICENSE", ""),
    "source": os.path.basename(char_fbx),
}
unreal.log(f"[char] manifest: {json.dumps(manifest)}")
if os.environ.get("DF_MANIFEST"):
    with open(os.environ["DF_MANIFEST"], "w") as f:
        json.dump(manifest, f, indent=2)
