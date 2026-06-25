# gameinject — high-fidelity roaming data by injecting shipped UE games

A reusable track for capturing **photoreal** world-model roaming data from shipped Unreal Engine games
on our **Linux GPU cluster**, by injecting **UE4SS (Lua)** under **Proton**. First target: **Black Myth:
Wukong** (UE5). Goal per clip: HUD-off RGB + full **depth** + **camera 6-DoF** + an agent that **drives
the character to roam** (terrain-aware), with the **action label known for free** (we author the input).

This complements the synthetic `datafarm` track (which stays the scalable, clean-label backbone). Game
injection is the *visual-fidelity* layer — its data is bucketed `label_kind = APPROX_ACTION | VIDEO_ONLY`
(not PRECISE_ACTION), because tick-sync and depth are best-effort, not engine-owned ground truth.

## Design: generic framework + per-game adapters

```
gameinject/
  framework/                 # GENERIC — reused across every UE game
    lua/datafarm_agent.lua   #   UE4SS Lua agent: find PlayerController/Pawn/CameraManager,
                             #   drive (AddMovementInput + line-trace terrain probing / nav if available),
                             #   toggle HUD, per-frame log (frame_id, action6, cam6dof, pose) -> JSONL
    launch/                  #   headless NVIDIA X + Proton launch + UE4SS injection + Vulkan capture
    capture/                 #   frame+depth grab glue (obs-vkcapture / ReShade-Proton)
  games/
    <game>/game.toml         # PER-GAME ADAPTER: install path, exe, Proton/UE4SS versions, class names,
    <game>/lua/overrides.lua #   HUD lever, nav mode, camera/pawn class — everything game-specific lives here
  tools/                     # convert captured frames + JSONL labels -> datafarm Episode schema
```

**Adding a new game = a new `games/<game>/` adapter** (a `game.toml` + a small `overrides.lua`); the
`framework/` core stays untouched. Python entry point: `datafarm/backends/gameinject.py` orchestrates an
episode (launch → roam+log → capture → read back into the `Episode` schema).

## The stack (per GPU, one instance)
1. **Headless NVIDIA X** bound to the A6000 (`nvidia-xconfig --use-display-device=none`, or gamescope
   `--backend headless`) — plain Xvfb does NOT give NVIDIA 3D accel for a Proton game.
2. **Proton** runs the Win64 game (D3D12→Vulkan via VKD3D-Proton). No cross-compile; runtime translation.
3. **UE4SS** injected (proxy DLL + `WINEDLLOVERRIDES`); its **Lua** drives + reads + logs.
4. **Vulkan capture** (obs-vkcapture / ReShade) dumps RGB (+depth); matched to the Lua log by `frame_id`.

## Status / de-risking order (see docs + git log)
Built incrementally, validating each layer before the next: (a) what the game install is + does it run
under Proton headless; (b) UE4SS injects headless; (c) object graph → camera/pawn/HUD/nav; (d) HUD-off;
(e) drive 30s roam + log; (f) RGB+depth capture + sync. A layer that can't pass is a documented kill-signal.

## Honest constraints (from the research, `docs/`)
Real-time-locked throughput (not faster-than-real-time like synthetic); per-patch-fragile reflection
offsets (pin the game build); Black Myth ships **Denuvo** (~5 activations/24h — bites multi-instance);
captured frames are copyrighted AAA content → **research-only, no raw-frame redistribution**.
