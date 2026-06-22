# Import a single GLB/FBX into UE content via Interchange (editor-time).
# Args via env (robust under -run=pythonscript): DF_SRC=<file> DF_DEST=/Game/Imported/Foo
#   UE_CMD <proj> -run=pythonscript -script=import_glb.py -RenderOffscreen -unattended
import os

import unreal

src = os.environ["DF_SRC"]
dest = os.environ.get("DF_DEST", "/Game/Imported/Scene")

im = unreal.InterchangeManager.get_interchange_manager_scripted()
params = unreal.ImportAssetParameters()
params.is_automated = True
src_data = unreal.InterchangeManager.create_source_data(src)
im.import_asset(dest, src_data, params)
unreal.EditorAssetLibrary.save_directory(dest)

assets = unreal.EditorAssetLibrary.list_assets(dest, recursive=True) or []
unreal.log(f"[import] {len(assets)} assets under {dest}")
for x in assets:
    ad = unreal.EditorAssetLibrary.find_asset_data(x)
    unreal.log(f"[import]   {ad.asset_class_path.asset_name}  {x}")
