#!/usr/bin/env bash
# Run one headless TickCapture episode.
# Usage: ue_capture.sh <render_config.json> [gpu_index] [/Game/Maps/Map]
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
. "$HERE/scripts/ue_env.sh"
CONFIG="$1"; GPU="${2:-}"; MAP="${3:-/Game/Maps/Capture}"
PROJ="$HERE/ue/DataFarmCapture/DataFarmCapture.uproject"
ADAPTER=""; [ -n "$GPU" ] && ADAPTER="-graphicsadapter=$GPU"
exec "$UE_CMD" "$PROJ" "$MAP" -game -RenderOffscreen -unattended -nosplash -nosound -stdout \
  -CaptureConfig="$CONFIG" $ADAPTER -ExecCmds="r.VSync 0"
