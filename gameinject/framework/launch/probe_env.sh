#!/usr/bin/env bash
# probe_env.sh — check a box's readiness for the gameinject stack (Vulkan render, game reach,
# outbound net for downloads, writability, space). Run locally or: ssh <box> 'bash -s' < probe_env.sh
G="${GI_GAME_ROOT:-/root/nas/bigdata1/cjw/games/blackmyth}"
EXE="$G/b1/Binaries/Win64/b1-Win64-Shipping.exe"

echo "=== game reachable? ==="
if [ -e "$EXE" ]; then echo "YES ($(du -sh "$G" 2>/dev/null | cut -f1))"; else echo "NO ($EXE)"; fi

echo "=== A6000 Vulkan render capability ==="
vulkaninfo --summary 2>/dev/null | grep -iE "deviceName|deviceType|driverInfo|apiVersion" | head -8 \
  || echo "vulkaninfo failed/missing"

echo "=== outbound internet (need to download GE-Proton/umu/UE4SS) ==="
curl -sI -m 12 https://github.com 2>/dev/null | head -1 || echo "github unreachable"
curl -sI -m 12 https://objects.githubusercontent.com 2>/dev/null | head -1 || echo "ghcdn unreachable"

echo "=== game Win64 writable? (UE4SS proxy dll goes here) ==="
if touch "$G/b1/Binaries/Win64/.gi_wtest" 2>/dev/null; then echo "WRITABLE"; rm -f "$G/b1/Binaries/Win64/.gi_wtest"; else echo "READONLY"; fi

echo "=== home space + python ==="
df -h "$HOME" 2>/dev/null | tail -1
python3 --version 2>/dev/null || echo "no python3"
echo "=== Xvfb / Xorg present ==="
command -v Xvfb Xorg 2>/dev/null | tr '\n' ' '; echo
