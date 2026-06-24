# Data diversity plan

From the `diversity-strategy` multi-agent research (UnrealZoo inventory · free-asset survey ·
blackmyth assessment · framework design). Goal: many more characters, scenes, and natural motion.

## The key realisation
Character diversity does NOT require new assets to start: UnrealZoo's `BP_Character` already
supports **`vbp <agent> set_app <1..18>`** = 18 human appearances (+ robot-dog 20–33, **28 animals**
via `set_animal_appearance`), and the binary ships **drone** (`/Game/Drone_Pack/.../BP_drone01_C`)
and **~22 vehicle** BPs. So on the research (UnrealZoo) track we get character + viewpoint diversity
for free. TRUE new characters (Mixamo etc.) must go through the own-content (TickCapture) track.

## Autonomous wins (done / in progress tonight — no login)
- **W1 scenes** — registered 20 UnrealZoo scenes (was 6); a validation sweep prunes the ones
  without a navmesh. ~100 maps exist incl. free **day/night/weather pairs** (SuburbNeighborhood_Day/
  Night, ContainerYard_Day/Night, RainMap/SnowMap/SunsetMap/Arctic) — a free lighting axis to add.
- **W2 appearance** ✅ — `set_app <1..18>` per episode, seeded → 18 free human variants (`meta.app_id`).
- **W4 no-navmesh fallback** ✅ — scenes lacking a navmesh fall back to manual wander, not a frozen agent.
- **Navmesh dead-loop fix** ✅ — directed exploration (farthest-of-K goal) + stuck-recovery: trajectory
  coverage tripled (0.08→0.24), 0-movement drops gone.
- **W3 embodiment** (next) — rotate `agent_bp` per plan: human + drone (aerial, no navmesh) + vehicles.
- **W5/W6** (later) — multi-agent wanderers (`nav_random`) for moving NPCs/crowds; animation variety
  (jump/crouch/pickup) + gait via `set_max_speed`.

## Character-diversity build — own track (needs the morning + your logins)
The closed UnrealZoo binary can't take new characters; real character variety lives on `backend=ue`
(TickCapture). Plan: standard rig = **UE5 Manny**; `content/characters.toml` + `content/animations.toml`
registries (mirror `scenes.toml`); a `DataFarmIngest` commandlet (Interchange import → IK-retarget any
rig → Manny) + `DataFarmBuildLevel` (assemble + add NavMeshBoundsVolume → .umap); TickCapture runtime
upgrade (cube→skeletal mesh + animBP + navmesh steering, porting the proven farthest-of-K+stuck logic);
**modular wardrobe** (top/pants/shoes/hair sampled per seed) → thousands of looks from a few imports.
I can wire the Python plumbing + start the TickCapture C++ against the engine's built-in Manny tonight;
the ingest needs sample assets to validate retarget.

## Free assets — ranked (what I need from you)
1. **UE5 Manny/Quinn + engine locomotion anims** — ships with the engine, no login. Build against these.
2. **UnrealZoo's 18 humans + 28 animals** — already ours (W2), research track only.
3. **Mixamo** (mixamo.com) — best diversity/effort (100s of free rigged chars + mocap anims, all
   retarget to Manny). **Needs your free Adobe login** → please grab Y-Bot/X-Bot + a locomotion pack.
4. **Fab / Quixel Megascans** — free scene kits + props for the own-track. **Needs your Epic/Fab login.**
5. Sketchfab CC0 — the `asset-library/` already has ~20 rigged CC0 chars + 11 scenes cataloged; reuse first.

## blackmyth verdict: SKIP (for characters/motion)
The Wukong rip has **0 animations**, a rig fragmented across 4 skeletons, fake JSON materials,
un-assembled per-mesh GLBs, and is non-redistributable. Not worth it for a farm that needs
rigged+animated characters. Optionally salvage one temple as static scene dressing later. Keep
`_demo/` as proof the CUE4Parse path works.
