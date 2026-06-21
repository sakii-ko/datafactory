import numpy as np

from datafarm.pose import CoordFrame, Pose6DoF
from datafarm.schema import (
    ACTION_KEYS,
    Action,
    EpisodeMeta,
    FrameRef,
    LabelKind,
    Source,
    Step,
    Viewpoint,
)


def test_action_zero_and_named_access():
    a = Action.zero()
    assert a.to_list() == [0] * len(ACTION_KEYS)
    assert a.forward == 0 and a.attack == 0


def test_action_from_dict():
    a = Action.from_dict({"forward": 1, "jump": 1})
    assert a.forward == 1 and a.jump == 1 and a.back == 0
    assert a.to_list() == [1, 0, 0, 0, 1, 0]


def test_step_to_row():
    s = Step(
        index=3,
        t=0.5,
        rgb=FrameRef(path="frames/000003.png"),
        player_pose=Pose6DoF([1, 2, 3], [1, 0, 0, 0]),
        camera_pose=Pose6DoF([4, 5, 6], [1, 0, 0, 0]),
        action=Action.from_dict({"forward": 1}),
    )
    row = s.to_row()
    assert row["index"] == 3 and row["rgb"] == "frames/000003.png"
    assert row["player_x"] == 1.0 and row["cam_z"] == 6.0
    assert row["cam_qw"] == 1.0
    assert row["forward"] == 1 and row["back"] == 0


def test_episode_meta_roundtrip():
    m = EpisodeMeta(
        episode_id="ep0001",
        source=Source.MOCK,
        viewpoint=Viewpoint.TPV,
        label_kind=LabelKind.PRECISE_ACTION,
        scene_id="scene_a",
        character_id="char_b",
        fps=24.0,
        resolution=(1920, 1080),
        seed=42,
        coord_frame=CoordFrame.UE_LEFT_CM,
    )
    m2 = EpisodeMeta.from_dict(m.to_dict())
    assert m2 == m
