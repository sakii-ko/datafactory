# Import a rigged GLB/glTF character via Interchange and write back its asset paths.
#   DF_SRC=<file.glb> DF_DEST=/Game/DataFarm/Characters/<id> DF_MANIFEST=<out.json>
#   UnrealEditor-Cmd <ABS proj> -run=pythonscript -script=import_glb_char.py -unattended -RenderOffscreen
# Emits {mesh, skeleton, anim, ...} object paths for content/characters.toml.
import json, os
import unreal
src = os.environ["DF_SRC"]; dest = os.environ.get("DF_DEST", "/Game/DataFarm/Characters/x")
im = unreal.InterchangeManager.get_interchange_manager_scripted()
params = unreal.ImportAssetParameters(); params.is_automated = True
sd = unreal.InterchangeManager.create_source_data(src)
im.import_asset(dest, sd, params)
unreal.EditorAssetLibrary.save_directory(dest)
def objpath(p):
    return p if "." in p.rsplit("/", 1)[-1] else f"{p}.{p.rsplit('/', 1)[-1]}"
mesh = skel = anim = None
allp = unreal.EditorAssetLibrary.list_assets(dest, recursive=True) or []
for p in allp:
    cls = str(unreal.EditorAssetLibrary.find_asset_data(p).asset_class_path.asset_name)
    if cls == "SkeletalMesh": mesh = objpath(p)
    elif cls == "Skeleton": skel = objpath(p)
    elif cls == "AnimSequence" and not anim: anim = objpath(p)
out = {"mesh": mesh, "skeleton": skel, "anim": anim, "n_assets": len(allp), "all": [str(x) for x in allp]}
with open(os.environ["DF_MANIFEST"], "w") as f: json.dump(out, f, indent=2)
unreal.log(f"[import] {json.dumps(out)}")
