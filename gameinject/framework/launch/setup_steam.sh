#!/usr/bin/env bash
# setup_steam.sh — stage the native Linux Steam client + steamcmd rootlessly on a headless box, for
# LEGITIMATE runs of an owned game (real Steam provides the ownership ticket Denuvo + Steamworks need).
# The interactive LOGIN (password + Steam Guard) is done by the user, not here. Usage: bash setup_steam.sh
set -u
SD="${GI_STEAMDIR:-$HOME/steam_setup}"; mkdir -p "$SD"; cd "$SD"

# steamcmd — used for the user's headless login (caches the session) + ownership/appinfo
if [ ! -x "$SD/steamcmd/steamcmd.sh" ]; then
  mkdir -p steamcmd
  curl -sqL https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz | tar zxf - -C steamcmd
fi
echo "steamcmd: $([ -x $SD/steamcmd/steamcmd.sh ] && echo ok || echo MISSING)"

# native Steam client (extract steam.deb with 7z — no root/dpkg needed)
if [ ! -e "$SD/steam/usr/bin/steam" ] && [ ! -e "$SD/steam/steam.sh" ]; then
  curl -sqLo steam.deb https://cdn.fastly.steamstatic.com/client/installer/steam.deb 2>/dev/null
  mkdir -p steam && cd steam
  7z x -y "$SD/steam.deb" >/dev/null 2>&1 && 7z x -y data.tar >/dev/null 2>&1 || true
  cd "$SD"
fi
echo "steam bootstrap: $(ls $SD/steam/usr/bin/steam $SD/steam/usr/lib/steam/* 2>/dev/null | head -1 || echo 'check extraction')"
echo "deb size: $(stat -c%s $SD/steam.deb 2>/dev/null) bytes"
ls "$SD/steam/usr/lib/steam/" 2>/dev/null | head
