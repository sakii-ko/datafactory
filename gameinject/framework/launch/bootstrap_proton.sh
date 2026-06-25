#!/usr/bin/env bash
# bootstrap_proton.sh — ROOTLESS userspace install of the injection runtime into a shared NAS dir.
# Downloads: GE-Proton (runs the Win64 game via Wine+DXVK/VKD3D), umu-launcher (run Proton WITHOUT a
# Steam client), UE4SS (Lua injection). Idempotent. Run on the GPU box (duan78); writes to the NAS so
# it's visible from every box. Usage: GI_RUNTIME=/path bash bootstrap_proton.sh
set -uo pipefail
RT="${GI_RUNTIME:-/home/lff/bigdata1/cjw/games/_gi_runtime}"
mkdir -p "$RT"/{proton,umu,ue4ss,dl} || { echo "cannot mkdir $RT"; exit 1; }
cd "$RT/dl"
log(){ echo "[bootstrap $(date +%H:%M:%S)] $*"; }
api(){ curl -s "https://api.github.com/repos/$1/releases/latest"; }
asset(){ api "$1" | grep -o '"browser_download_url": *"[^"]*"' | sed 's/.*"\(http[^"]*\)"/\1/' | grep -iE "$2" | head -1; }

# --- 1. GE-Proton -------------------------------------------------------------------------------
if [ ! -x "$RT/proton/proton" ] && ! ls "$RT/proton"/GE-Proton*/proton >/dev/null 2>&1; then
  # x86_64 build only — exclude the aarch64 asset (this box is x86_64).
  U="$(api GloriousEggroll/proton-ge-custom | grep -o '"browser_download_url": *"[^"]*"' \
       | sed 's/.*"\(http[^"]*\)"/\1/' | grep -E 'GE-Proton[0-9].*\.tar\.gz$' | grep -v aarch64 | head -1)"
  log "GE-Proton: $U"
  if [ -n "$U" ]; then
    curl -fL -o ge.tar.gz "$U" && tar -xzf ge.tar.gz -C "$RT/proton" && rm -f ge.tar.gz \
      && log "GE-Proton extracted -> $(ls -d "$RT/proton"/GE-Proton* 2>/dev/null|tail -1)" || log "GE-Proton FAILED"
  else log "GE-Proton url not found"; fi
else log "GE-Proton already present"; fi

# --- 2. umu-launcher (zipapp: run Proton without Steam) -----------------------------------------
if [ ! -e "$RT/umu/umu-run" ]; then
  U="$(asset Open-Wine-Components/umu-launcher 'umu-run$')"
  [ -z "$U" ] && U="$(asset Open-Wine-Components/umu-launcher 'Zipapp.*tar|umu-launcher.*tar')"
  log "umu: $U"
  if [ -n "$U" ]; then
    case "$U" in
      *umu-run) curl -fL -o "$RT/umu/umu-run" "$U" && chmod +x "$RT/umu/umu-run" && log "umu-run ok";;
      *)        curl -fL -o umu.tar "$U" && tar -xf umu.tar -C "$RT/umu" && log "umu tar extracted";;
    esac
  else log "umu url not found (will fall back to direct proton invocation)"; fi
else log "umu already present"; fi

# --- 3. UE4SS (Lua injection) -------------------------------------------------------------------
if [ ! -e "$RT/ue4ss/dwmapi.dll" ] && [ ! -e "$RT/ue4ss/xinput1_3.dll" ]; then
  U="$(asset UE4SS-RE/RE-UE4SS 'UE4SS_v.*\.zip$')"
  [ -z "$U" ] && U="$(asset UE4SS-RE/RE-UE4SS '\.zip$')"
  log "UE4SS: $U"
  if [ -n "$U" ]; then
    curl -fL -o ue4ss.zip "$U" && (cd "$RT/ue4ss" && unzip -oq "$RT/dl/ue4ss.zip") && rm -f ue4ss.zip \
      && log "UE4SS extracted: $(ls "$RT/ue4ss" | tr '\n' ' ')" || log "UE4SS FAILED"
  else log "UE4SS url not found"; fi
else log "UE4SS already present"; fi

# --- 4. portable Python >=3.10 for umu-launcher (its `match` stmts need 3.10+; duan's system py is 3.8)
if ! python3 -c 'import sys;exit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null; then
  if [ ! -x "$RT/python/bin/python3" ]; then
    U="$(api astral-sh/python-build-standalone | grep -o '"browser_download_url": *"[^"]*"' \
         | sed 's/.*"\(http[^"]*\)"/\1/' \
         | grep -E 'cpython-3\.11\.[0-9]+(%2B|\+)[0-9]+-x86_64-unknown-linux-gnu-install_only\.tar\.gz$' | head -1)"
    log "portable python: $U"
    if [ -n "$U" ]; then
      curl -fL -o py.tar.gz "$U" && tar -xzf py.tar.gz -C "$RT" && rm -f py.tar.gz \
        && log "python -> $RT/python/bin/python3 ($("$RT"/python/bin/python3 --version 2>&1))" || log "python FAILED"
    else log "portable-python url not found"; fi
  else log "portable python already present"; fi
else log "system python >=3.10 ok"; fi

log "DONE. Contents:"; ls -la "$RT"/proton "$RT"/umu "$RT"/ue4ss "$RT"/python/bin 2>/dev/null | sed 's/^/    /'
