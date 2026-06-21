import json

import numpy as np
from PIL import Image

from datafarm.backends import ue as ue_mod
from datafarm.backends.base import EpisodePlan
from datafarm.backends.ue import UEBackend
from datafarm.schema import ACTION_KEYS, Viewpoint

_HEADER = ("index,t,rgb,player_x,player_y,player_z,player_qw,player_qx,player_qy,player_qz,"
           "cam_x,cam_y,cam_z,cam_qw,cam_qx,cam_qy,cam_qz," + ",".join(ACTION_KEYS))


def _fake_ue(cfg: dict):
    """Simulate the UE plugin writing an episode into cfg['out_dir']."""
    out = ue_mod.Path(cfg["out_dir"])
    (out / "frames").mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(cfg["num_frames"]):
        Image.fromarray(np.zeros((cfg["height"], cfg["width"], 3), np.uint8)).save(
            out / f"frames/{i:06d}.png")
        # player moves +X (10/frame) facing +X; quat identity; zero actions (UE writes raw)
        vals = [10 * i, 0, 0, 1, 0, 0, 0, 10 * i, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        rows.append(f"{i},{i / cfg['fps']},frames/{i:06d}.png,"
                    + ",".join(str(v) for v in vals))
    (out / "steps.csv").write_text(_HEADER + "\n" + "\n".join(rows) + "\n")
    (out / "meta.json").write_text(json.dumps({
        "episode_id": cfg["episode_id"], "source": "ue", "viewpoint": cfg["viewpoint"],
        "label_kind": "precise_action", "fps": cfg["fps"],
        "resolution": [cfg["width"], cfg["height"]], "seed": cfg["seed"],
        "coord_frame": "ue_left_cm", "schema_version": 1, "num_steps": cfg["num_frames"],
    }))


def test_ue_capture_wiring(tmp_path, monkeypatch):
    captured = {}

    def fake_run(args, **kw):
        cfg = json.loads(ue_mod.Path(args[2]).read_text())
        captured["cfg"] = cfg
        captured["gpu"] = args[3] if len(args) > 3 else None
        _fake_ue(cfg)
        class R: returncode = 0
        return R()

    monkeypatch.setattr(ue_mod.subprocess, "run", fake_run)
    plan = EpisodePlan("ue_ep0", seed=5, viewpoint=Viewpoint.FPV, steps=8, fps=16.0, resolution=(64, 48))
    ep = UEBackend().capture(plan, tmp_path, gpu=3)

    assert len(ep) == 8
    assert ep.meta.source.value == "ue" and ep.meta.viewpoint.value == "fpv"
    assert ep.meta.coord_frame.value == "ue_left_cm"
    # actions inferred from pose deltas (forward motion facing +X) — not the raw zeros
    assert ep.steps[0].action.forward == 1
    # render_config.json written with plan-derived fields
    assert captured["cfg"]["num_frames"] == 8 and captured["cfg"]["width"] == 64
    assert captured["cfg"]["viewpoint"] == "fpv"
    assert captured["gpu"] == "3"
    assert (tmp_path / "ue_ep0" / "render_config.json").exists()


def test_ue_capture_raises_without_output(tmp_path, monkeypatch):
    monkeypatch.setattr(ue_mod.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})())
    plan = EpisodePlan("ue_ep1", seed=0, viewpoint=Viewpoint.TPV, steps=4, fps=16.0, resolution=(32, 32))
    import pytest
    with pytest.raises(RuntimeError):
        UEBackend().capture(plan, tmp_path)


def test_ue_healthcheck_returns_status():
    st = UEBackend().healthcheck()
    assert isinstance(st.detail, str)
