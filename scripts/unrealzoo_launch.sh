#!/usr/bin/env bash
# Launch a UnrealZoo env binary headless on Linux + its baked-in UnrealCV server.
# The Vulkan startup GPU-benchmark crashes under bare -RenderOffscreen, so we give it a
# virtual X display (xvfb) instead — that is the working headless recipe (validated on A6000).
# Usage: unrealzoo_launch.sh <path/to/SceneLauncher.sh>   (UnrealCV port from its unrealcv.ini, default 9000)
set -u
BIN="$1"
exec xvfb-run -a -s "-screen 0 1280x720x24" "$BIN" -nosound -unattended
