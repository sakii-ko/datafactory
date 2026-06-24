#!/usr/bin/env bash
# Autonomously fetch a CC0 rigged glTF/GLB character and ingest it into the own-track UE project.
#   fetch_character.sh <id> <glb_url> [gpu]
# Downloads the GLB, Interchange-imports it (skeletal mesh + skeleton + anim), and prints the
# {mesh, anim} object paths to paste into content/characters.toml. No login required.
set -euo pipefail
ID="${1:?usage: fetch_character.sh <id> <glb_url> [gpu]}"
URL="${2:?usage: fetch_character.sh <id> <glb_url> [gpu]}"
GPU="${3:-0}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$HERE/scripts/ue_env.sh"
mkdir -p "$HERE/assets_in"
GLB="$HERE/assets_in/$ID.glb"
MAN="$HERE/assets_in/$ID.manifest.json"
echo "[fetch] $URL -> $GLB"
curl -sL --connect-timeout 20 --max-time 180 -o "$GLB" "$URL"
file "$GLB" | grep -qi "glTF\|data" || { echo "download not a glb"; exit 1; }
DF_SRC="$GLB" DF_DEST="/Game/DataFarm/Characters/$ID" DF_MANIFEST="$MAN" \
  "$UE_CMD" "$HERE/ue/DataFarmCapture/DataFarmCapture.uproject" -run=pythonscript \
  -script="$HERE/ue/scripts/import_glb_char.py" -unattended -RenderOffscreen -graphicsadapter="$GPU" \
  >"$HERE/assets_in/$ID.import.log" 2>&1 || true
echo "[fetch] ingested $ID:"; cat "$MAN" 2>/dev/null || { echo "import failed; see $ID.import.log"; exit 1; }
