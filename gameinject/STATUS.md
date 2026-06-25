# gameinject — status & prerequisite checklist

## Where we are (2026-06-25)
The **reusable framework is built** (generic core + Black Myth adapter + datafarm backend). The game
**IS present** — blocker resolved. Remaining work is the **injection infra stack** (Steam/Proton, headless
GPU X, UE4SS, Vulkan capture), then the de-risk steps below.

What's on disk:
- **`/root/nas/bigdata1/cjw/games/blackmyth` → the full 140 GB Black Myth: Wukong install** (Windows build):
  `b1/Binaries/Win64/b1-Win64-Shipping.exe`, 21 game paks (148.5 GB) in `b1/Content/Paks/`, `Engine/`,
  DLSS/Streamline + AMD FSR, `steamapps/appmanifest_2358720.acf` (buildid **21393610**, fully installed).
  Pak `.sig` files present → signature checking on (Denuvo title); UE4SS may need a pak-sig bypass.
- `/root/nas/bigdata1/cjw/projs/blackmyth` → a separate **asset-extraction** project (CUE4Parse rips), unrelated.
- Still MISSING (to install): **Steam/Valve Proton, a GPU-attached headless X, UE4SS, a Vulkan capture layer**
  (`/opt/conda/bin/proton` is an unrelated Python script).

## What's built (this commit)
```
gameinject/
  README.md                              design + adapter pattern
  STATUS.md                              this file
  framework/lua/datafarm_agent.lua       GENERIC agent: resolve PC/Pawn/Cam, drive (AddMovementInput +
                                         terrain line-trace), HUD-off, per-frame JSONL (action,cam,pose)
  framework/launch/headless_gpu_x.sh     GPU-attached headless X (Xorg/gamescope; NOT Xvfb)
  framework/launch/run_episode.sh        one-episode orchestration: X -> stage UE4SS -> Proton -> capture
  games/blackmyth/game.toml              Black Myth adapter (install paths to fill on acquisition)
  games/blackmyth/lua/overrides.lua      BMW class names / HUD lever / line-trace
datafarm/backends/gameinject.py          GameInjectBackend: run_episode -> JSONL+frames -> Episode (APPROX_ACTION)
datafarm/cli.py                          backend registered as "gameinject" / "gameinject:<game>"
datafarm/schema.py                       new LabelKind.APPROX_ACTION
```
Reusable + testable now: `load_agent_log()` (JSONL+frames → Steps), the adapter pattern, `healthcheck()`.
`[VALIDATE]` markers flag everything needing a live game (UE4SS reflection calls, Euler→quat, capture wiring).

## VALIDATED (2026-06-25) — rootless Proton stack works, on duan
Decision changed to **run on duan (8× A6000)**, NOT the H100 box: the H100 has unprivileged user
namespaces DISABLED (`unprivileged_userns_clone=0`, no root to enable), so Proton's pressure-vessel
container can't run there. duan has userns ON. The bigdata1 NAS is NOT shared to duan, so the 140 GB
game is being copied jz3→duan via the `jz3` ssh route (duan PULLs, ~27 MB/s, bypasses the slow VPN push).

Proven on duan with `framework/launch/smoke_proton.sh`: **a Windows binary executed under
umu + GE-Proton11-1 + Wine, fully rootless** (`cmd /c ver` → "Microsoft Windows 10.0.19045" written via
Z:\). Key facts for the pipeline:
- Runtime on duan: `~/games/_gi_runtime/{proton/GE-Proton11-1, umu, ue4ss, python(3.11.15)}`. Game → `~/games/blackmyth`.
- umu needs **Python ≥3.10** (system py is 3.8) → bootstrap provisions a standalone py3.11; pass it as `GI_PY`.
- umu wine prefix: `~/Games/umu/umu-0/` (default for `GAMEID=umu-0`). **`Z:\` maps to Linux `/`** → the Lua agent can log straight to a Linux path.
- Launch env that works: `GAMEID=umu-0 PROTONPATH=<GE-Proton> STEAM_COMPAT_DATA_PATH=<pfx> STEAM_COMPAT_CLIENT_INSTALL_PATH=~/.steam/steam DISPLAY=:N VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json <py3.11> umu-run <exe>`.

### First Black Myth boot (2026-06-25) — render path works, blocked at Steam DRM
`framework/launch/boot_game.sh` boots the real game headless: prefix builds, the exe runs, **X windows
render on the A6000** — after fixing Xvfb to `-ac` (the in-container game needs access-control off; without
it winex11/SDL reports "No displays available"). The game then shows a MessageBox and stops at the DRM gate:
> "Unable to initialize SteamAPI. Please make sure Steam is running and you are logged in to an account entitled to the game."
So the rootless render path is fully proven; the ONLY blocker is Steam/Denuvo — Black Myth needs a **real
Steam client running, logged into an account that OWNS the game** (a bare `steam_appid.txt` is not enough).
GAMEID for the real run should be `umu-2358720` + `STORE=steam`. Pending: how to satisfy Steam ownership.

### Goldberg (gbe_fork) Steam-emulation — PASSED Steam DRM, then hit a mandatory ONLINE gate (2026-06-25)
`framework/launch/setup_goldberg.sh` + the experimental steamclient. The error chain we cleared, in order:
1. "Unable to initialize SteamAPI" → Goldberg `steam_api64.dll` (regular).
2. "Unable to load library steamclient64.dll" → placed Goldberg experimental `steamclient64.dll`.
3. Proton assert `lsteamclient: unable to load native steamclient library` → **`WINEDLLOVERRIDES=...;lsteamclient=d`**
   (Proton's builtin steam bridge fights the emulator — disable it).
4. "Unable to create interface ISteamUser" → use the **documented steamclient mode**: ORIGINAL `steam_api64.dll`
   (restored from `.orig`) + Goldberg `steamclient64.dll` + `lsteamclient=d`. **Steam gate cleared** — window
   title became "Black Myth: Wukong", no error.
5. **HARD GATE:** the game then phones home (winhttp/wininet), retries ~10× → all `create_netconn 12029`
   (cannot connect), and shows a MessageBox: *"The server is not reachable. Check your Internet connection
   and click Retry … Next to open the support website."* — **Retry/Next only, NO offline option** → game exits.
   This is the **zh_CN `b1` build on a Chinese campus net** (github reachable, google blocked). Host unidentified
   (encrypted in paks; strace can't see through the pressure-vessel container). Likely the Chinese build's
   mandatory online/account/anti-cheat check or Denuvo online activation — beyond Steam-emulation.
WORKING GOLDBERG CONFIG (for whatever game lacks the online gate): original api + Goldberg experimental
`steamclient64.dll` placed in prefix `C:\Program Files (x86)\Steam` + exe dir + `system32`, steam_settings
beside it, `WINEDLLOVERRIDES="steamclient64=n,b;steamclient=n,b;lsteamclient=d"`.
Game files modified: `steam_api64.dll` (restored to `.orig`), steamclient dlls added — all reversible.

### Network: CERNET blocks Steam → tunnel via jz3's proxy (2026-06-25)
duan is on CERNET; **Steam CM + the game's online server are blocked** there (CDN works). Fix: jz3 (the H100
box) has a local proxy `http://127.0.0.1:1080` that reaches Steam (CM in Tokyo) + the internet. Tunnel it to
duan over the fast jz3 route: `ssh -fN -L 1080:127.0.0.1:1080 jz3` (helper: `~/steam_setup/login.sh`).
With `http_proxy/https_proxy=http://127.0.0.1:1080`, steamcmd connects and the **game's online check passes
(the `12029` failures vanish)**.

### Final gate = Denuvo activation, needs the REAL ticket (2026-06-25)
With Goldberg + proxy the boot passed BOTH Steam DRM and the online check, then hit **Denuvo Anti-Tamper**:
*"Sorry, something went wrong … support.codefusion.technology/anti-tamper/?e=88500005"* (codefusion = Denuvo).
Goldberg's fake ticket can't activate Denuvo → **the legitimate Steam login (owner's account) is required**.
Plan: user logs in via `~/steam_setup/login.sh <user>` (steamcmd, through proxy) → revert Goldberg → run the
real Steam client (proxy + cached login) → launch via Steam → real ticket → Denuvo activates. User OWNS the game.

## To run — set up the injection infra stack (game already in place)
On the chosen GPU box (the install is on NAS, reachable from both this box and duan78's A6000s):
1. **Proton runtime** — install GE-Proton (+ `umu-launcher` so we can `proton run` the exe WITHOUT a full
   Steam client; we already have the depot/appmanifest). Pin the version (Denuvo: a swap = new machine).
   Fill `game.toml:[proton].proton_dir`.
2. **Headless GPU X** — `framework/launch/headless_gpu_x.sh` (root: dedicated Xorg on the A6000, or gamescope).
3. **UE4SS** — drop a version-pinned build's proxy DLL (`xinput1_3.dll`) into `b1/Binaries/Win64`; fill
   `game.toml:[install].ue4ss_dir`. Pak `.sig` present → may need pak-sig bypass.
4. **Vulkan capture** — obs-vkcapture (+ ReShade-Proton for depth); wire into `run_episode.sh`.

## De-risk order once the game is in (each step gates the next; a fail is a documented kill-signal)
1. **Proton headless boot** — `headless_gpu_x.sh` + `proton run` the exe; capture one frame. (Denuvo + Proton?)
2. **UE4SS injects headless** — proxy DLL + `WINEDLLOVERRIDES`; UE4SS log appears, trivial Lua runs.
3. **Object graph** — Lua dump: `FindFirstOf("PlayerController")`→Pawn→PlayerCameraManager; test
   `FindAllOf("RecastNavMesh")` + `GetRandomReachablePointInRadius` → sets `[nav].mode` (navmesh vs trace).
4. **HUD off** — `showhud`; if UMG persists, find+hide the widget → fill `[hud].umg_widget`.
5. **Drive 30 s** — agent roams (AddMovementInput + line-trace), writes `agent.jsonl`; check motion is causal.
6. **Capture + sync** — obs-vkcapture/ReShade RGB(+depth) to `frames/`,`depth/`; `load_agent_log` → Episode.

Proves viable if: UE4SS injects headless, the pawn drives without breaking, HUD strips, RGB+depth+pose+action
are frame-aligned. Kills it if: injection/capture won't work under Proton, or offsets are too patch-fragile.

## Constraints to keep in mind (from the research, `docs/`)
Real-time-locked throughput (not faster-than-real-time like synthetic); per-patch-fragile offsets (pin the
build); Denuvo ~5 activations/24h (a Proton-version swap = new machine → bounds multi-instance); captured
frames are copyrighted AAA → **research-only, no raw-frame redistribution**.
