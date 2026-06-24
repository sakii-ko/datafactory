# Own-track characters — what to provide

The own-content track (UE5.5 project `ue/DataFarmCapture`) is how we get REAL new rigged characters
(beyond UnrealZoo's 18 `set_app` looks). Pipeline: **you provide FBX → `import_character.py` imports
them → the capture runtime spawns + navmesh-walks them → FPV/TPV episodes**. Here's the asset part.

## Mixamo (free, fastest — needs your Adobe login)
For each character you want:
1. mixamo.com → pick a humanoid (e.g. *Y Bot*, *X Bot*, or any character) → **Download**:
   - Format **FBX Binary**, Pose **T-pose**, **with skin** → `‹name›.fbx` (the mesh+skeleton).
2. Animations (do a few — these become the locomotion): search *Walking*, *Running*, *Idle* → for each
   **Download** → FBX Binary, **Without Skin**, **In Place** → `walk.fbx`, `run.fbx`, `idle.fbx`.
   "Without Skin" makes them bind to the same skeleton, so **no retargeting needed**.
3. Drop them on the box, one folder per character:
   `~/datafactory/assets_in/‹id›/{‹name›.fbx, walk.fbx, run.fbx, idle.fbx}` and tell me the `‹id›`.

I then run (per character):
```
DF_CHAR_FBX=assets_in/<id>/<name>.fbx DF_ANIM_FBXS=assets_in/<id>/walk.fbx,assets_in/<id>/run.fbx \
DF_DEST=/Game/DataFarm/Characters/<id> DF_CHAR_ID=<id> DF_MANIFEST=/tmp/<id>.json \
  UnrealEditor-Cmd ue/DataFarmCapture/DataFarmCapture.uproject -run=pythonscript \
  -script=ue/scripts/import_character.py -unattended
```
→ a `[[character]]` entry in `content/characters.toml`, then the capture runtime uses it.

## Fab / Quixel Megascans (Epic login) — for scenes/props and some characters
- Characters: any rigged humanoid FBX/glTF works through the same `import_character.py`.
- Scenes: export the kit and import via `ue/scripts/import_glb.py` + a level-build script (next), which
  adds a NavMeshBoundsVolume so the agent can walk it.

## What I'm building in parallel (no assets needed yet)
- `import_character.py` ✅ (ingest).
- The **C++ capture runtime** (spawn skeletal char + navmesh-walk + FPV/TPV capture → steps.csv) — being
  drafted now; I'll validate it against the engine's built-in shapes/Manny first, so it's ready the moment
  your FBX lands.

**Smallest useful first drop:** one Mixamo character + a *Walking* animation. That's enough to prove the
whole own-track end-to-end; then we scale to many characters + a modular wardrobe.
