#!/usr/bin/env bash
# boot_game.sh — launch the shipped game via the validated rootless umu/Proton stack under Xvfb.
# For first-boot validation (Denuvo, render) and the basis of the capture pipeline.
# GAMEID=umu-<steam appid> + STORE=steam => umu applies the game's protonfix + a Steam shim (Denuvo needs it).
# Usage: GI_RUNTIME=~/games/_gi_runtime GI_GAME_ROOT=~/games/blackmyth bash boot_game.sh [seconds]
#   GI_UE4SS=1 to inject UE4SS (proxy from GI_PROXY, default xinput1_3).
set -u
RT="${GI_RUNTIME:?set GI_RUNTIME}"; GAME_ROOT="${GI_GAME_ROOT:?set GI_GAME_ROOT}"
EXE_REL="${GI_EXE_REL:-b1/Binaries/Win64/b1-Win64-Shipping.exe}"
SECS="${1:-180}"
PROTON="$(ls -d "$RT"/proton/GE-Proton*/ 2>/dev/null | head -1)"
UMU="$RT/umu/umu/umu-run"; PY="${GI_PY:-$RT/python/bin/python3}"
DISP=":${GI_DISP:-99}"
LOG="${GI_LOG:-$RT/boot.log}"; SHOT="${GI_SHOT:-$RT/boot_frame.png}"

export DISPLAY="$DISP"
export GAMEID="${GI_GAMEID:-umu-2358720}" STORE="${GI_STORE:-steam}"
export PROTONPATH="${PROTON%/}"
export STEAM_COMPAT_DATA_PATH="${GI_PREFIX:-$HOME/Games/umu/$GAMEID}"
export STEAM_COMPAT_CLIENT_INSTALL_PATH="$HOME/.steam/steam"
export VK_ICD_FILENAMES="${GI_VK_ICD:-/usr/share/vulkan/icd.d/nvidia_icd.json}"
mkdir -p "$STEAM_COMPAT_CLIENT_INSTALL_PATH" "$(dirname "$LOG")"
# Force the game to use Goldberg's native steam dlls instead of Proton's builtin lsteamclient bridge
# (which expects a real Linux Steam and asserts otherwise). Override string is configurable for iteration.
OVR="${GI_DLLOVERRIDES:-steam_api64=n,b;steamclient64=n,b;steamclient=n,b}"
[ -n "${GI_UE4SS:-}" ] && OVR="$OVR;${GI_PROXY:-xinput1_3}=n,b"
export WINEDLLOVERRIDES="$OVR"

# Steamworks needs to know the appid (Denuvo/Steam DRM init); write steam_appid.txt next to the exe.
APPID="${GI_APPID:-${GAMEID##*-}}"
case "$APPID" in [0-9]*) echo -n "$APPID" > "$GAME_ROOT/$(dirname "$EXE_REL")/steam_appid.txt" 2>/dev/null || true;; esac

# headless display: -ac disables X access control so the in-container game can connect (fixes
# "No displays available"); rendering itself goes to the A6000 via Vulkan, not Xvfb.
pgrep -f "Xvfb $DISP " >/dev/null 2>&1 || { Xvfb "$DISP" -screen 0 "${GI_W:-1280}x${GI_H:-720}x24" -ac -nolisten tcp >/dev/null 2>&1 & sleep 3; }

echo "[boot] $(date +%H:%M:%S) launching $GAME_ROOT/$EXE_REL  GAMEID=$GAMEID DISPLAY=$DISP for ${SECS}s" | tee "$LOG"
timeout "$SECS" "$PY" "$UMU" "$GAME_ROOT/$EXE_REL" >>"$LOG" 2>&1 &
GPID=$!

# after warmup, grab one frame of the Xvfb root to confirm the game actually rendered
sleep $(( SECS>90 ? 70 : SECS/2 ))
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -y -f x11grab -video_size "${GI_W:-1280}x${GI_H:-720}" -i "$DISP" -frames:v 1 "$SHOT" >/dev/null 2>&1
elif command -v import >/dev/null 2>&1; then
  DISPLAY="$DISP" import -window root "$SHOT" >/dev/null 2>&1
elif command -v xwd >/dev/null 2>&1; then
  xwd -root -display "$DISP" -silent 2>/dev/null | { command -v convert >/dev/null && convert xwd:- "$SHOT"; } 2>/dev/null
fi
echo "[boot] screenshot: $(ls -la "$SHOT" 2>/dev/null | awk '{print $5" bytes"}' || echo NONE)" | tee -a "$LOG"
echo "[boot] proc still up: $(kill -0 $GPID 2>/dev/null && echo yes || echo no)" | tee -a "$LOG"
wait "$GPID" 2>/dev/null
echo "[boot] exited rc=$? — last log lines:" | tee -a "$LOG"; tail -15 "$LOG"
