#!/usr/bin/env bash
# run_episode.sh — capture ONE gameinject episode end-to-end on one GPU.
# Called by datafarm GameInjectBackend.capture() with env:
#   GI_GAME GI_EPISODE GI_OUT GI_FRAMES GI_FPS GI_SEED GI_GPU GI_W GI_H
#
# Pipeline: load adapter -> headless GPU X -> stage UE4SS+agent -> Proton launch (inject) ->
#           Vulkan capture (RGB[+depth]) -> wait for agent JSONL to reach GI_FRAMES -> teardown.
# Everything game-specific comes from gameinject/games/$GI_GAME/{game.toml,lua/overrides.lua}.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"            # repo root
GI="$ROOT/gameinject"
GAME="${GI_GAME:?}"; OUT="${GI_OUT:?}"; GPU="${GI_GPU:-0}"
ADAPTER="$GI/games/$GAME"
TOML="$ADAPTER/game.toml"
mkdir -p "$OUT/frames" "$OUT/depth"

# --- read adapter (TOML) via python --------------------------------------------------------------
read_toml() { python3 -c "import tomllib,sys;d=tomllib.load(open('$TOML','rb'));print(eval('d'+sys.argv[1],{'d':d}))" "$1"; }
GAME_ROOT="$(read_toml "['install']['game_root']")"
EXE_REL="$(read_toml "['game']['exe_relpath']")"
UE4SS_DIR="$(read_toml "['install']['ue4ss_dir']")"
PROTON_DIR="$(read_toml "['proton']['proton_dir']")"
DLL_OVERRIDES="$(read_toml "['proton']['wine_dll_overrides']")"

if [ -z "$GAME_ROOT" ] || [ ! -e "${GAME_ROOT/#\~/$HOME}/$EXE_REL" ]; then
  echo "[run_episode] ABORT: game not installed (install.game_root unset/invalid in $TOML)." >&2
  echo "[run_episode] See gameinject/STATUS.md — acquire the game before running." >&2
  exit 3
fi
GAME_ROOT="${GAME_ROOT/#\~/$HOME}"; PROTON_DIR="${PROTON_DIR/#\~/$HOME}"; UE4SS_DIR="${UE4SS_DIR/#\~/$HOME}"

# --- 1. headless GPU X ---------------------------------------------------------------------------
"$HERE/headless_gpu_x.sh" "$GPU" & XPID=$!
sleep 2; export DISPLAY=":$((90 + GPU))"
cleanup() { kill "$XPID" "${CAPPID:-}" "${GAMEPID:-}" 2>/dev/null || true; }
trap cleanup EXIT

# --- 2. stage UE4SS Lua agent (generic framework + this game's overrides) -------------------------
MODS="$UE4SS_DIR/Mods/datafarm"        # UE4SS scans Mods/; one mod dir = our agent
mkdir -p "$MODS/Scripts"
cp "$GI/framework/lua/datafarm_agent.lua" "$MODS/Scripts/main.lua"
cp "$ADAPTER/lua/overrides.lua"           "$MODS/Scripts/overrides.lua"
# episode params -> gi_runtime.lua (merged by overrides.lua)
cat >"$MODS/Scripts/gi_runtime.lua" <<EOF
return { log_path = [[$OUT/agent.jsonl]], num_frames = ${GI_FRAMES:-900},
         fps = ${GI_FPS:-30}, seed = ${GI_SEED:-1} }
EOF
echo "datafarm" >> "$UE4SS_DIR/Mods/mods.txt" 2>/dev/null || true   # enable the mod [VALIDATE format]

# --- 3. Vulkan capture (RGB[+depth]) -> OUT/frames ------------------------------------------------
# obs-vkcapture writes via a Vulkan layer the game loads (VK_INSTANCE_LAYERS). [VALIDATE under Proton #204]
export OBS_VKCAPTURE=1
# TODO[VALIDATE]: wire obs-vkcapture/ReShade-Proton frame dump to "$OUT/frames/%06d.png" at GI_FPS,
#                 and ReShade depth tap to "$OUT/depth/%06d.exr". Capture-under-Proton is the soft spot.

# --- 4. launch the game under Proton with UE4SS injected -----------------------------------------
export WINEDLLOVERRIDES="$DLL_OVERRIDES"
export STEAM_COMPAT_DATA_PATH="$OUT/compat"; mkdir -p "$STEAM_COMPAT_DATA_PATH"
export STEAM_COMPAT_CLIENT_INSTALL_PATH="${STEAM_COMPAT_CLIENT_INSTALL_PATH:-$HOME/.steam/steam}"
export VK_ICD_FILENAMES="/usr/share/vulkan/icd.d/nvidia_icd.json"
echo "[run_episode] launching $GAME under Proton on GPU $GPU / $DISPLAY" >&2
"$PROTON_DIR/proton" run "$GAME_ROOT/$EXE_REL" & GAMEPID=$!

# --- 5. wait until the agent has logged GI_FRAMES rows, then stop ---------------------------------
for _ in $(seq 1 $(( ${GI_FRAMES:-900} / ${GI_FPS:-30} + 120 )) ); do
  [ -f "$OUT/agent.jsonl" ] && [ "$(wc -l < "$OUT/agent.jsonl")" -ge "${GI_FRAMES:-900}" ] && break
  kill -0 "$GAMEPID" 2>/dev/null || { echo "[run_episode] game exited early" >&2; break; }
  sleep 1
done
echo "[run_episode] done: $(wc -l < "$OUT/agent.jsonl" 2>/dev/null || echo 0) frames logged -> $OUT" >&2
