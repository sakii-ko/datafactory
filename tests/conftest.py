import numpy as np
import pytest

from datafarm.pose import Pose6DoF
from datafarm.schema import (
    Action,
    Episode,
    EpisodeMeta,
    FrameRef,
    LabelKind,
    Source,
    Step,
    Viewpoint,
)


def make_episode(n=10, frames=True, fps=16.0, seed=0, static=False, episode_id="ep_test"):
    rng = np.random.default_rng(seed)
    steps = []
    for i in range(n):
        x = 0.0 if static else float(i)
        pp = Pose6DoF([x, 0, 0], [1, 0, 0, 0])
        cp = Pose6DoF([x, 0, 0], [1, 0, 0, 0])
        rgb = (
            FrameRef(array=rng.integers(0, 255, (8, 8, 3), dtype=np.uint8))
            if frames else FrameRef(path=f"frames/{i:06d}.png")
        )
        steps.append(Step(i, i / fps, rgb, pp, cp, Action.zero()))
    meta = EpisodeMeta(
        episode_id=episode_id, source=Source.MOCK, viewpoint=Viewpoint.TPV,
        label_kind=LabelKind.PRECISE_ACTION, fps=fps, seed=seed,
    )
    return Episode(meta, steps)


@pytest.fixture
def episode():
    return make_episode()
