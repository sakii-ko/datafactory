# Headless content gen: a minimal lit level for validating TickCapture.
# Run: UnrealEditor-Cmd <proj> -run=pythonscript -script=<this> -unattended -RenderOffscreen
import unreal

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def spawn(cls, loc=(0, 0, 0), rot=(0, 0, 0)):
    return eas.spawn_actor_from_class(cls, unreal.Vector(*loc), unreal.Rotator(*rot))


if unreal.EditorAssetLibrary.does_asset_exist("/Game/Maps/Capture"):
    unreal.EditorAssetLibrary.delete_asset("/Game/Maps/Capture")   # new_level won't overwrite
les.new_level("/Game/Maps/Capture")

plane = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Plane")
cube = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Cube")

floor = spawn(unreal.StaticMeshActor)
floor.static_mesh_component.set_static_mesh(plane)
floor.set_actor_scale3d(unreal.Vector(80, 80, 1))

for i, (x, y) in enumerate([(400, 0), (0, 400), (-400, 0), (0, -400), (300, 300)]):
    c = spawn(unreal.StaticMeshActor, (x, y, 100))
    c.static_mesh_component.set_static_mesh(cube)
    c.set_actor_scale3d(unreal.Vector(2, 2, 2))

spawn(unreal.DirectionalLight, (0, 0, 1000), (-45, 45, 0))
spawn(unreal.SkyLight, (0, 0, 500))
spawn(unreal.SkyAtmosphere)
spawn(unreal.ExponentialHeightFog)
spawn(unreal.PlayerStart, (0, 0, 120))

# Navmesh bounds so the rigged-character AIController (GetRandomReachablePointInRadius) has a
# navmesh to query at runtime. With RuntimeGeneration=Dynamic + bAutoCreateNavigationData (ini),
# a RecastNavMesh auto-builds inside these bounds. The volume brush scales with the actor.
nav = spawn(unreal.NavMeshBoundsVolume, (0, 0, 100))
nav.set_actor_scale3d(unreal.Vector(60, 60, 8))   # ~120x120m x 16m over the 80x80m floor

les.save_current_level()
unreal.log("TickCapture: wrote /Game/Maps/Capture (with NavMeshBoundsVolume)")
