# UnrealZoo backend — research-track content

UnrealZoo ships **cooked, packaged UE binaries** (purchased Marketplace scenes + a baked-in
UnrealCV server). We cannot put our own TickCapture plugin inside them, so we use them as-is:
run the binary headless, drive it over the UnrealCV socket, and feed frames into our data layer.
This is the **research track** (`backend = "unrealzoo"`). For scenes we own the source of, use the
**own track** (`backend = "ue"`, TickCapture) — see [ue-capture-plugin.md](ue-capture-plugin.md).

Content is research-only (Marketplace license): use for academic work, do not redistribute the
assets or ship a model trained on them commercially. Datasets are tagged `license=research-only`.

## Which package
ModelScope dataset `UnrealZoo/UnrealZoo-UE5`:
- `UE5_ExampleScene_Linux.zip` (~12.8 GB) — **render-only demo**. One scene (an industrial plant),
  free cameras only. `vset /objects/spawn_from_path` is NOT implemented → **no agent framework**.
  Good for validating capture/rendering, not for embodied navigation.
- `UnrealZoo_UE5_6_v3.0.2/Linux/UnrealZoo_UE5_6_Linux_v3.0.2.tar.gz{aa,ab,ac}` (~73 GB, 3 parts) —
  the **full package**: the `BP_Character` agent framework, `set_move` walking, navmesh, `safe_start`
  spawn points, and the 100+ scenes. This is what ground-agent navigation needs.

Download is slow through the H100 box's `HTTPS_PROXY` (ModelScope CDN is China-only); **bypass the
proxy** (`curl --noproxy '*'`, ~26 MB/s) or download on duan78 (Tsinghua, ~18 MB/s). Concatenate +
stream-extract: `cat ...tar.gzaa ...gzab ...gzac | tar xzf - -C <dir>`.

## Launch (headless on A6000)
`scripts/unrealzoo_launch.sh <SceneLauncher.sh>` → `xvfb-run -a -s "-screen 0 1280x720x24"
<binary> -nosound -unattended`. **xvfb (virtual display) is required** — bare `-RenderOffscreen`
crashes in the Vulkan startup GPU benchmark (`MeasureLongGPUTaskExecutionTime`,
`VulkanCommandBuffer.cpp:503`). UnrealCV serves on **:9000** (from `unrealcv.ini`); wait for the log
line `Start listening on 9000`. Do **not** use `-nullrhi` (black frames).

## Ground-agent recipe (UnrealCV commands; units = cm / deg)
One-time per env:
```
vset /objects/spawn_from_path /Game/SmartLocomotion/Blueprints/BP_Character.BP_Character_C <name>
vbp <name> set_phy 0
vbp <name> set_cam 20 0 0 0 0 0           # eye 20cm forward (set_cam args: x y z roll pitch yaw)
vbp <name> set_speed <cm/s>
vbp <name> generate_nav_goal <rmax> 0     # -> {"nav_goal":"X= Y= Z="}; teleport there for a valid start
```
The spawned `BP_Character` auto-creates its own camera (id ≥ 1; camera 0 is the free/top camera).
Resolve the eye-cam id by the new camera that appears after spawn (or the camera nearest the pawn).

Per step (physical, collision-aware walk):
```
vbp <name> set_move <v_angle[-30..30]> <v_linear[-100..100]>   # turn, forward throttle
vget /camera/<eye>/lit png                                     # FPV RGB
vget /object/<name>/location    # "x y z"            (cm)
vget /object/<name>/rotation    # "pitch yaw roll"   (deg)
vbp <name> get_hit                                             # collision flag -> turn away
```
We infer WSAD actions from the pawn pose deltas (normalized to CANON_RH_M), same as the UE track.
TPV: reposition camera 0 above/behind the pawn (`vset /camera/0/location|rotation`).

## Known quirks (this UnrealCV build)
- **Single client**: only the first TCP connection after env start works; reconnects hang. One env
  per worker; connect once, capture many episodes, then kill the env. For fan-out: one binary + one
  port (9000, 9001, …) per parallel A6000.
- **Restart**: after killing the binary, wait ~45 s for the :9000 socket TIME_WAIT to clear, else the
  new server logs `tcp server is not running` (bind fails).
- **Per-frame** ~0.45 s after a ~13 s first-frame shader/PSO warmup.
- **object_mask** returns a single uniform color in this headless/standalone build (known UnrealCV
  issue). RGB + depth + pose work. Segmentation is deferred (own track / CustomStencil instead).
- **Python**: run on duan78 via the `fpack` conda env (3.10); `unrealcv` installed with `pip --user`.

## Run
```
PYTHONPATH=. <python> -m datafarm.cli run --backend unrealzoo --scenes <id> \
  --episodes N --steps 64 --fps 16 --res 640x480 --out runs
```
`UnrealZooConfig.mode`: `"agent"` (default, ground BP_Character) or `"camera"` (free camera, demo).
