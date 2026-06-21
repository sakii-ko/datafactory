#!/usr/bin/env bash
# Source this to set up the environment for launching/building UE5 headless on Linux.
# UE needs a Vulkan loader (libvulkan.so.1) it cannot always find; we prepend one and
# pin the NVIDIA ICD. On boxes where libvulkan.so.1 is already system-installed
# (e.g. duan78), the guard makes prepending a no-op.
: "${DATAFARM_UE_ROOT:=/root/nas/bigdata1/cjw/UnrealEngine_5.5.4}"
: "${DATAFARM_VK_LIB_DIR:=/root/nas/fastdata2/miniconda3/envs/ue5libs/lib}"
export DATAFARM_UE_ROOT

# Vulkan loader: prepend one only if the system lacks libvulkan.so.1 (no-op on e.g. duan78).
if ! ldconfig -p 2>/dev/null | grep -q 'libvulkan\.so\.1' && [ -d "$DATAFARM_VK_LIB_DIR" ]; then
  export LD_LIBRARY_PATH="$DATAFARM_VK_LIB_DIR:${LD_LIBRARY_PATH:-}"
fi
# Pin a *valid* NVIDIA ICD — the loader will NOT fall back if VK_ICD_FILENAMES points
# at a missing file. (On this box the real one is /etc/vulkan/icd.d, not /usr/share.)
if [ -z "${VK_ICD_FILENAMES:-}" ]; then
  for _icd in /etc/vulkan/icd.d/nvidia_icd.json /usr/share/vulkan/icd.d/nvidia_icd.json; do
    [ -r "$_icd" ] && export VK_ICD_FILENAMES="$_icd" && break
  done
fi
: "${XDG_RUNTIME_DIR:=/tmp/xdg-$(id -u)}"; mkdir -p "$XDG_RUNTIME_DIR" 2>/dev/null; export XDG_RUNTIME_DIR
export UE_CMD="$DATAFARM_UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd"
export UE_BUILD="$DATAFARM_UE_ROOT/Engine/Build/BatchFiles/Linux/Build.sh"
export UE_UAT="$DATAFARM_UE_ROOT/Engine/Build/BatchFiles/RunUAT.sh"
