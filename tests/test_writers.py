import shutil

import numpy as np
import pytest

from datafarm.schema import Action
from datafarm.writers import load_frame, pack_tar, read_episode, write_episode

from .conftest import make_episode


def test_write_read_roundtrip(tmp_path):
    ep = make_episode(n=6)
    ep.steps[2].action = Action.from_dict({"forward": 1, "jump": 1})
    d = write_episode(ep, tmp_path)
    back = read_episode(d)
    assert back.meta.episode_id == ep.meta.episode_id
    assert len(back) == len(ep)
    for a, b in zip(ep.steps, back.steps):
        assert np.allclose(a.player_pose.position, b.player_pose.position)
        assert a.action.to_list() == b.action.to_list()
        assert b.rgb.path == f"frames/{a.index:06d}.png"
    assert back.steps[2].action.forward == 1 and back.steps[2].action.jump == 1


def test_frames_written(tmp_path):
    ep = make_episode(n=4)
    d = write_episode(ep, tmp_path)
    assert (d / "frames" / "000000.png").exists()
    img = load_frame(d / "frames" / "000000.png")
    assert img.shape == (8, 8, 3)


def test_num_steps_in_meta(tmp_path):
    import json
    ep = make_episode(n=5)
    d = write_episode(ep, tmp_path)
    assert json.loads((d / "meta.json").read_text())["num_steps"] == 5


def test_pack_tar(tmp_path):
    import tarfile
    d1 = write_episode(make_episode(n=3, episode_id="ep_a"), tmp_path)
    d2 = write_episode(make_episode(n=3, episode_id="ep_b"), tmp_path)
    shard = pack_tar([d1, d2], tmp_path / "shard.tar")
    names = tarfile.open(shard).getnames()
    assert any("ep_a/meta.json" in n for n in names)
    assert any("ep_b/steps.csv" in n for n in names)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_encode_video(tmp_path):
    ep = make_episode(n=12)
    d = write_episode(ep, tmp_path, video=True)
    assert (d / "video.mp4").exists() and (d / "video.mp4").stat().st_size > 0
