#!/usr/bin/env bash
# headless_gpu_x.sh — bring up a REAL X server attached to one NVIDIA GPU, with no monitor.
# Proton/DXVK needs GPU-accelerated GLX/Vulkan; plain Xvfb is software-only and will NOT work.
# Two supported paths; pick per box capability. Prints the DISPLAY to use, holds the server in foreground.
#
# Usage: headless_gpu_x.sh <gpu_index> [display_num]
# Requires root for the Xorg path (writes a transient xorg.conf, binds the GPU's BusID).
set -euo pipefail
GPU="${1:-0}"
DISP="${2:-$((90 + GPU))}"

# Resolve the PCI BusID of the chosen GPU for a dedicated headless screen.
BUSID="$(nvidia-xconfig --query-gpu-info 2>/dev/null \
  | awk -v g="$GPU" '/GPU #/{n=$0} /PCI BusID/{c++; if(c==g+1){print $4; exit}}')" || true

# --- Path A: gamescope headless (no root; needs gamescope + a recent Mesa/NVIDIA) ---------------
if command -v gamescope >/dev/null 2>&1 && [ "${GI_X_BACKEND:-xorg}" = "gamescope" ]; then
  echo "[headless_x] gamescope --backend headless on GPU $GPU" >&2
  # NB: gamescope headless has open rendering-glitch bugs (#1984/#2017); validate output frames.
  exec gamescope --backend headless -W "${GI_W:-1280}" -H "${GI_H:-720}" -- sleep infinity
fi

# --- Path B: dedicated headless Xorg bound to the GPU (root) ------------------------------------
CONF="$(mktemp /tmp/xorg-gi-XXXX.conf)"
cat >"$CONF" <<EOF
Section "ServerLayout"
  Identifier "gi"
  Screen 0 "scr" 0 0
EndSection
Section "Device"
  Identifier "dev"
  Driver "nvidia"
  ${BUSID:+BusID "$BUSID"}
  Option "AllowEmptyInitialConfiguration" "true"
  Option "UseDisplayDevice" "none"
EndSection
Section "Screen"
  Identifier "scr"
  Device "dev"
  DefaultDepth 24
  SubSection "Display"
    Depth 24
    Virtual ${GI_W:-1280} ${GI_H:-720}
  EndSubSection
EndSection
EOF
echo "[headless_x] Xorg :$DISP on GPU $GPU (BusID ${BUSID:-auto}); conf=$CONF" >&2
echo ":$DISP"   # caller exports DISPLAY=:$DISP
exec Xorg ":$DISP" -config "$CONF" -noreset
