#!/usr/bin/env python3
"""Append imported characters from a batch manifest to content/characters.toml.

  register_characters.py <manifest.json> [license] [tag]
manifest = [{id, mesh, anim}, ...] (from ue/scripts/import_characters_batch.py). Skips ids already
present + entries missing mesh/anim, so it's safe to re-run.
"""
import json
import re
import sys
from pathlib import Path

manifest = json.load(open(sys.argv[1]))
lic = sys.argv[2] if len(sys.argv) > 2 else "imported"
tag = sys.argv[3] if len(sys.argv) > 3 else "imported"
toml = Path(__file__).resolve().parents[1] / "content" / "characters.toml"
text = toml.read_text()
existing = set(re.findall(r'^id\s*=\s*"([^"]+)"', text, re.M))

blocks = []
for r in manifest:
    cid, mesh, anim = r.get("id"), r.get("mesh"), r.get("anim")
    if not (cid and mesh and anim) or cid in existing:
        continue
    blocks.append(
        f'\n[[character]]\nid = "{cid}"\nmesh = "{mesh}"\nanim = "{anim}"\n'
        f'standard_rig = "mixamorig"\nlicense = "{lic}"\ntags = ["humanoid", "{tag}"]\n')
    existing.add(cid)

if blocks:
    toml.write_text(text.rstrip() + "\n" + "".join(blocks))
print(f"registered {len(blocks)} new characters ({len(existing)} ids total)")
