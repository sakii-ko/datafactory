#!/usr/bin/env python3
"""Fetch Mixamo characters + animations via the internal API.

Needs a short-lived bearer token in the env (keep it in a gitignored file, never commit):
  export MIXAMO_AUTH='Bearer eyJ...'   MIXAMO_APIKEY='mixamo2'
Usage:
  mixamo_fetch.py <out_dir> <character_query> [anim_query ...]
Downloads the first character matching <character_query> (with skin) as <out_dir>/character.fbx,
plus the first motion matching each anim query (retargeted onto that character, in-place loop) as
<out_dir>/<anim>.fbx. Then ingest with ue/scripts/import_character.py.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

API = "https://www.mixamo.com/api/v1"
H = {
    "Authorization": os.environ["MIXAMO_AUTH"], "X-Api-Key": os.environ["MIXAMO_APIKEY"],
    "Accept": "application/json", "Referer": "https://www.mixamo.com/", "Origin": "https://www.mixamo.com",
}


def _req(url, data=None):
    body = json.dumps(data).encode() if data is not None else None
    h = dict(H)
    if body:
        h["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=h), timeout=60) as f:
        return json.load(f)


def search(query, typ):
    q = urllib.parse.urlencode({"page": 1, "limit": 1, "type": typ, "query": query})
    res = _req(f"{API}/products?{q}").get("results", [])
    return res[0] if res else None


def export_and_wait(char_id, body):
    _req(f"{API}/animations/export", data=body)
    for _ in range(50):
        m = _req(f"{API}/characters/{char_id}/monitor")
        if m.get("status") == "completed":
            return m["job_result"]
        if m.get("status") == "failed":
            raise RuntimeError(f"export failed: {m}")
        time.sleep(3)
    raise RuntimeError("export timed out")


def download(url, path):
    with urllib.request.urlopen(urllib.request.Request(url), timeout=180) as f, open(path, "wb") as o:
        o.write(f.read())
    return os.path.getsize(path)


def main():
    out, char_q = sys.argv[1], sys.argv[2]
    anims = sys.argv[3:] or ["Walking", "Running", "Idle"]
    os.makedirs(out, exist_ok=True)
    ch = search(char_q, "Character")
    assert ch, f"no character matching {char_q!r}"
    cid, cname = ch["id"], ch["name"]
    print(f"character: {cname} ({cid})")
    url = export_and_wait(cid, {
        "character_id": cid, "type": "Character", "product_name": cname,
        "preferences": {"format": "fbx7_2019", "skin": "true", "fps": "30", "reducekf": "0"}})
    print(f"  character.fbx <- {download(url, f'{out}/character.fbx')} bytes")
    for aq in anims:
        m = search(aq, "Motion")
        if not m:
            print(f"  (no motion {aq!r})")
            continue
        gh = _req(f"{API}/products/{m['id']}?character_id={cid}")["details"]["gms_hash"]
        body = {
            "character_id": cid, "type": "Motion", "product_name": m["name"],
            "gms_hash": [{"model-id": gh["model-id"], "mirror": False, "trim": gh.get("trim", [0, 100]),
                          "inplace": True, "arm-space": gh.get("arm-space", 0),
                          "params": ",".join(str(p[1]) for p in gh.get("params", []))}],
            "preferences": {"format": "fbx7_2019", "skin": "false", "fps": "30", "reducekf": "0"}}
        url = export_and_wait(cid, body)
        fn = aq.lower().replace(" ", "_") + ".fbx"
        print(f"  {fn} ({m['name']}) <- {download(url, f'{out}/{fn}')} bytes")


if __name__ == "__main__":
    main()
