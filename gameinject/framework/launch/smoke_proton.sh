#!/usr/bin/env bash
# smoke_proton.sh — validate the ROOTLESS Proton stack on this box with a trivial Windows exe,
# BEFORE risking the real game. Confirms the full chain: Xvfb display + umu/pressure-vessel
# container (needs unprivileged userns) + GE-Proton Wine + nvidia Vulkan ICD.
# Usage: GI_RUNTIME=~/games/_gi_runtime bash smoke_proton.sh
set -u
RT="${GI_RUNTIME:?set GI_RUNTIME}"
PROTON="$(ls -d "$RT"/proton/GE-Proton*/ 2>/dev/null | head -1)"
UMU="$(ls "$RT"/umu/umu/umu-run "$RT"/umu/umu-run 2>/dev/null | head -1)"
[ -n "$PROTON" ] || { echo "[smoke] no GE-Proton in $RT/proton"; exit 2; }
[ -n "$UMU" ]    || { echo "[smoke] no umu-run in $RT/umu"; exit 2; }

export DISPLAY=":${GI_DISP:-99}"
export VK_ICD_FILENAMES="${GI_VK_ICD:-/usr/share/vulkan/icd.d/nvidia_icd.json}"
export STEAM_COMPAT_DATA_PATH="$RT/prefix_smoke"
export STEAM_COMPAT_CLIENT_INSTALL_PATH="${STEAM_COMPAT_CLIENT_INSTALL_PATH:-$HOME/.steam/steam}"
export GAMEID="umu-0"
export PROTONPATH="${PROTON%/}"
mkdir -p "$STEAM_COMPAT_DATA_PATH" "$STEAM_COMPAT_CLIENT_INSTALL_PATH"

# headless display for Wine's window (rendering itself goes to the GPU via Vulkan, not Xvfb)
pgrep -f "Xvfb $DISPLAY" >/dev/null 2>&1 || { Xvfb "$DISPLAY" -screen 0 1280x720x24 >/dev/null 2>&1 & }
sleep 3
echo "[smoke] PROTONPATH=$PROTONPATH"
echo "[smoke] DISPLAY=$DISPLAY  VK_ICD=$VK_ICD_FILENAMES  umu=$UMU"
echo "[smoke] userns: $(unshare -Ur true 2>/dev/null && echo OK || echo BLOCKED)"
echo "[smoke] first run bootstraps the umu steam-runtime container (download + bwrap) — the real test..."
# umu-launcher needs python >=3.10 (match stmt); invoke with GI_PY if the system python is older.
GI_PY="${GI_PY:-python3}"
echo "[smoke] umu python: $GI_PY ($($GI_PY --version 2>&1))"
# 1) wineboot --init: exercises umu -> pressure-vessel -> proton -> wine, builds the prefix
timeout "${GI_SMOKE_TIMEOUT:-900}" "$GI_PY" "$UMU" wineboot --init >/dev/null 2>&1
echo "[smoke] wineboot rc=$?"
# 2) definitive: run a Windows command that writes output to a file via Z:\ (= Linux /). If the file
#    contains the Windows version, the full rootless chain executes Windows binaries.
PROOF="$RT/.smoke_exec_proof"; rm -f "$PROOF"
WPROOF="Z:$(echo "$PROOF" | sed 's#/#\\#g')"
timeout 180 "$GI_PY" "$UMU" cmd /c "ver > $WPROOF" >/dev/null 2>&1
if grep -qi microsoft "$PROOF" 2>/dev/null; then
  echo "[smoke] PASS: rootless Proton executes Windows binaries -> $(cat "$PROOF" | tr -d '\r')"
else
  echo "[smoke] FAIL: no Windows output — inspect above (userns/container/runtime issue)"
fi
