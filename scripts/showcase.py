#!/usr/bin/env python3
"""Asset-showcase grids for the UnrealZoo track.

  showcase.py lineup --scene SuburbNeighborhood_Day --out char_lineup.png   # needs an env on :9000
  showcase.py scenes --run runs/div1 --out scenes_grid.png                  # one frame per scene

`lineup` does a controlled close-up sweep of `set_app` (the 18 human appearances): spawn one agent,
park camera 0 in front of it, cycle the appearance id, grab a frame each -> a clean character sheet.
`scenes` builds a contact sheet (one FPV frame per scene) from a finished dataset run.
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def _grid(cells, out, cols, title, tw, th):
    rows = (len(cells) + cols - 1) // cols or 1
    img = Image.new("RGB", (cols * tw, rows * th + 22), (18, 18, 22))
    dr = ImageDraw.Draw(img)
    for i, (label, im) in enumerate(cells):
        x, y = (i % cols) * tw, (i // cols) * th + 22
        img.paste(im.resize((tw, th)), (x, y))
        dr.text((x + 4, y + 3), str(label), fill=(255, 235, 0))
    dr.text((4, 5), title, fill=(255, 255, 255))
    img.save(out)
    print("wrote", out, f"({len(cells)} cells)")


def lineup(a):
    from unrealcv import Client
    c = Client((a.host, a.port)); c.connect(timeout=15)
    for cmd in ("vrun r.EyeAdaptationQuality 0", "vrun r.EyeAdaptation.MethodOverride 2"):
        c.request(cmd)
    if a.scene:
        c.request(f"vset /action/game/level {a.scene}"); time.sleep(12)
    c.request("vset /objects/spawn_from_path /Game/SmartLocomotion/Blueprints/BP_Character.BP_Character_C sc")
    c.request("vbp sc set_phy 0")
    for _ in range(12):                                  # teleport to a navmesh point (clear ground)
        r = c.request("vbp sc generate_nav_goal 8000 0")
        try:
            xyz = [float(p.split("=")[1]) for p in json.loads(r).get("nav_goal", "").split() if "=" in p]
            if len(xyz) == 3:
                c.request(f"vset /object/sc/location {xyz[0]} {xyz[1]} {xyz[2]}"); break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    time.sleep(1)
    loc = [float(x) for x in c.request("vget /object/sc/location").split()]
    yawd = float(c.request("vget /object/sc/rotation").split()[1]); yaw = np.deg2rad(yawd)
    fwd = np.array([np.cos(yaw), np.sin(yaw)])
    cam = (loc[0] + a.dist * fwd[0], loc[1] + a.dist * fwd[1], loc[2] + a.height)   # in front of agent
    c.request(f"vset /camera/0/location {cam[0]:.1f} {cam[1]:.1f} {cam[2]:.1f}")
    c.request(f"vset /camera/0/rotation -6 {yawd + 180:.1f} 0")                     # look back at its front
    cells = []
    for app in range(a.lo, a.hi):
        c.request(f"vbp sc set_app {app}"); time.sleep(0.3)
        d = c.request("vget /camera/0/lit png")
        if isinstance(d, (bytes, bytearray)):
            cells.append((f"app {app}", Image.open(io.BytesIO(d)).convert("RGB")))
    c.disconnect()
    _grid(cells, a.out, a.cols, f"CHARACTERS - set_app {a.lo}..{a.hi - 1} ({a.scene or 'current'})", 220, 248)


def scenes(a):
    cells = {}
    for d in sorted(glob.glob(f"{a.run}/*/")):
        mp = Path(d) / "meta.json"
        if not mp.exists():
            continue
        m = json.loads(mp.read_text())
        sc, vp, fs = m.get("scene_id"), m.get("viewpoint"), sorted(glob.glob(f"{d}/frames/*.png"))
        if sc and fs and (sc not in cells or vp == "fpv"):
            cells[sc] = fs[len(fs) // 2]
    items = [(k, Image.open(v).convert("RGB")) for k, v in sorted(cells.items())]
    _grid(items, a.out, a.cols, f"SCENES ({len(items)})", 256, 192)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    lp = sub.add_parser("lineup")
    lp.add_argument("--scene", default=""); lp.add_argument("--host", default="127.0.0.1")
    lp.add_argument("--port", type=int, default=9000); lp.add_argument("--lo", type=int, default=1)
    lp.add_argument("--hi", type=int, default=19); lp.add_argument("--dist", type=float, default=200)
    lp.add_argument("--height", type=float, default=120); lp.add_argument("--cols", type=int, default=6)
    lp.add_argument("--out", default="char_lineup.png"); lp.set_defaults(fn=lineup)
    sc = sub.add_parser("scenes")
    sc.add_argument("--run", required=True); sc.add_argument("--cols", type=int, default=4)
    sc.add_argument("--out", default="scenes_grid.png"); sc.set_defaults(fn=scenes)
    args = p.parse_args(); args.fn(args)
