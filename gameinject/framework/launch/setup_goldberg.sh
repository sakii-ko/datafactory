#!/usr/bin/env bash
# setup_goldberg.sh — replace a game's steam_api64.dll with the gbe_fork (Goldberg) Steam emulator so an
# OWNED game runs offline without a live Steam client. Backs up the original; configures offline + a
# fake owning user + DLC unlock. Reusable across games. Research/owned-content use only.
# Usage: GI_GOLDBERG=~/games/_gi_runtime/goldberg GI_DLL=<path to game's steam_api64.dll> GI_APPID=2358720 \
#        [GI_GB_BUILD=regular|experimental] bash setup_goldberg.sh
set -u
GB="${GI_GOLDBERG:?set GI_GOLDBERG (extracted gbe_fork dir)}"
DLL="${GI_DLL:?set GI_DLL (game steam_api64.dll to replace)}"
APPID="${GI_APPID:?set GI_APPID}"
BUILD="${GI_GB_BUILD:-regular}"
SRC="$GB/win/release/$BUILD/x64/steam_api64.dll"
[ -f "$SRC" ] || { echo "[goldberg] no $SRC"; exit 2; }
[ -f "$DLL" ] || { echo "[goldberg] target $DLL missing"; exit 2; }
DIR="$(dirname "$DLL")"

# 1) back up original once
[ -f "$DLL.orig" ] || cp -n "$DLL" "$DLL.orig"
# 2) drop in the emulator dll
cp -f "$SRC" "$DLL"
# 3) appid + steam_settings next to the dll
echo -n "$APPID" > "$DIR/steam_appid.txt"
SS="$DIR/steam_settings"; mkdir -p "$SS"
cat > "$SS/configs.main.ini" <<INI
[main::connectivity]
disable_networking=1
offline=1
disable_lan_only=0
[main::misc]
achievements_bypass=1
INI
cat > "$SS/configs.user.ini" <<INI
[user::general]
account_name=datafarm
account_steamid=76561197960287930
language=english
ip_country=US
INI
cat > "$SS/configs.app.ini" <<INI
[app::general]
branch_name=public
[app::dlcs]
unlock_all=1
INI
echo "[goldberg] installed $BUILD build -> $DLL"
echo "[goldberg]   backup: $DLL.orig ($(stat -c%s "$DLL.orig" 2>/dev/null) bytes)"
echo "[goldberg]   new dll: $(stat -c%s "$DLL" 2>/dev/null) bytes; appid=$APPID; steam_settings/ written"
echo "[goldberg]   revert: cp \"$DLL.orig\" \"$DLL\""
