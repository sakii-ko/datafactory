from __future__ import annotations

import io
import json
import time
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from ..action import infer_actions
from ..pose import CoordFrame, Pose6DoF
from ..schema import (
    Action,
    Episode,
    EpisodeMeta,
    FrameRef,
    LabelKind,
    Source,
    Step,
    Viewpoint,
)
from .base import BackendStatus, CaptureBackend, EpisodePlan, JobSpec, default_plan


@dataclass
class UnrealZooConfig:
    host: str = "127.0.0.1"
    port: int = 9000
    mode: str = "agent"          # "agent" = spawn a walking BP_Character (full package);
    #                              "camera" = drive a free camera (demo ExampleScene)
    cam_id: int = 0              # camera mode: which camera to drive
    agent_bp: str = "/Game/SmartLocomotion/Blueprints/BP_Character.BP_Character_C"
    agent_name: str = "df_agent"
    policy: str = "navmesh"      # "navmesh" = autopilot between navmesh goals (collision-free,
    #                              high yield); "wander" = manual forward+turn-on-hit
    eye_offset: tuple[float, float, float] = (20.0, 0.0, 0.0)   # eye 20cm forward of pawn
    speed: float = 200.0         # set_speed cap (cm/s)
    linear: float = 100.0        # set_move forward throttle [-100, 100]
    turn_max: float = 30.0       # set_move yaw input range [-30, 30] (deg)
    turn_jitter: float = 7.0     # per-step heading wander (deg) before clamp
    nav_radius: float = 8000.0   # navmesh start-goal sampling radius
    nav_speed: float = 220.0     # navmesh autopilot speed (cm/s)
    frame_dt: float = 0.25       # navmesh mode: seconds to let the agent walk between frame grabs
    goal_reach: float = 300.0    # cm: pick a new navmesh goal once within this of the current one
    scene_load_wait: float = 12.0  # seconds to wait after vset .../level for the map to stream in
    warmup_steps: int = 6        # discarded forward steps before recording
    req_timeout: float = 15.0    # per-request socket timeout (warm pool: bound, don't hang)
    ready_timeout: float = 180.0  # max wait for the UnrealCV server after process launch
    # console vars applied after connect: stop auto-exposure (eye adaptation) blowing out bright views
    exposure_cmds: tuple[str, ...] = (
        "vrun r.EyeAdaptationQuality 0",
        "vrun r.EyeAdaptation.MethodOverride 2",
    )
    action_deadzone: float = 0.01  # m/frame, in CANON_RH_M


def _yaw_quat(yaw: float) -> np.ndarray:
    return np.array([np.cos(yaw / 2), 0.0, 0.0, np.sin(yaw / 2)])


class UnrealZooBackend(CaptureBackend):
    """Capture from a running UnrealZoo env (scene binary + baked-in UnrealCV server, launched
    headless via scripts/unrealzoo_launch.sh). Default mode spawns a BP_Character and walks it
    (collision-aware) for embodied FPV navigation data; camera mode drives a free camera (for
    the agent-less ExampleScene demo). Research-only content (Marketplace assets)."""

    name = "unrealzoo"
    warm_pool = True

    def __init__(self, config: UnrealZooConfig | None = None):
        self.cfg = config or UnrealZooConfig()
        self._client = None
        self._eye = self.cfg.cam_id
        self._agent_ready = False
        self._loaded_level = None
        self._alive = lambda: True   # EnvPool overrides with the slot process liveness probe

    def _connect(self):
        from unrealcv import Client
        if self._client is None or not self._client.isconnected():
            self._client = Client((self.cfg.host, self.cfg.port))
            self._client.connect()
            if not self._client.isconnected():
                raise RuntimeError(f"cannot connect to UnrealCV {self.cfg.host}:{self.cfg.port}")
        return self._client

    def _req(self, c, cmd: str):
        from ..farm.pool import EnvCrashed
        if not self._alive():
            raise EnvCrashed(f"UE dead before '{cmd}'")
        for _ in range(3):           # UnrealCV occasionally returns None; the gym retries similarly
            try:
                r = c.request(cmd, timeout=self.cfg.req_timeout)
            except TypeError:        # unrealcv build may lack the timeout kwarg
                r = c.request(cmd)
            except Exception as e:   # noqa: BLE001
                if not self._alive():
                    raise EnvCrashed(str(e)) from e
                r = None
            if r is not None:
                return r
            if not c.isconnected():
                raise EnvCrashed(f"client lost connection on '{cmd}'")
        if not self._alive():
            raise EnvCrashed(f"UE died on '{cmd}'")
        return None

    def plan(self, job: JobSpec) -> list[EpisodePlan]:
        return default_plan(job)

    # ---- warm-pool hooks (one backend per EnvPool slot) ----
    def for_slot(self, gpu: int | None, port: int) -> "UnrealZooBackend":
        return UnrealZooBackend(replace(self.cfg, port=port))

    def open(self, ready_timeout: float = 180.0) -> None:
        from ..farm.pool import EnvCrashed
        deadline, last = time.time() + ready_timeout, None
        while time.time() < deadline:
            if not self._alive():
                raise EnvCrashed("UE process died during startup")
            try:
                if self._req(self._connect(), "vget /unrealcv/status"):
                    return   # exposure_cmds are applied per-episode in capture() (covers the direct path too)
            except Exception as e:   # noqa: BLE001 — not ready yet
                last = e
                self._client = None
            time.sleep(2.0)
        raise EnvCrashed(f"UnrealCV {self.cfg.host}:{self.cfg.port} not ready in {ready_timeout}s ({last})")

    def alive(self) -> bool:
        try:
            return bool(self._req(self._connect(), "vget /unrealcv/status"))
        except Exception:   # noqa: BLE001
            return False

    def close(self) -> None:
        try:
            if self._client:
                self._client.disconnect()
        except Exception:   # noqa: BLE001
            pass
        self._client = None

    # ---- agent (BP_Character) helpers ----
    def _camera_ids(self, c) -> list[int]:
        ids = []
        for i in range(32):
            r = self._req(c, f"vget /camera/{i}/location")
            if not r or "error" in str(r).lower():
                break
            ids.append(i)
        return ids

    def _agent_loc(self, c, name) -> np.ndarray:
        return np.array([float(x) for x in self._req(c, f"vget /object/{name}/location").split()])

    def _nav_goal(self, c, name) -> list[float] | None:
        r = self._req(c, f"vbp {name} generate_nav_goal {self.cfg.nav_radius:.0f} 0")
        try:
            g = json.loads(r).get("nav_goal", "")
            xyz = [float(p.split("=")[1]) for p in g.split() if "=" in p]
            return xyz if len(xyz) == 3 else None
        except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
            return None  # navmesh sampling unavailable

    def _nav_start(self, c, name) -> None:
        xyz = self._nav_goal(c, name)
        if xyz:
            self._req(c, f"vset /object/{name}/location {xyz[0]:.1f} {xyz[1]:.1f} {xyz[2]:.1f}")

    def _setup_agent(self, c) -> None:
        n = self.cfg.agent_name
        before = set(self._camera_ids(c))
        self._req(c, f"vset /objects/spawn_from_path {self.cfg.agent_bp} {n}")
        self._req(c, f"vbp {n} set_phy 0")
        ex, ey, ez = self.cfg.eye_offset
        self._req(c, f"vbp {n} set_cam {ex} {ey} {ez} 0 0 0")
        self._req(c, f"vbp {n} set_speed {self.cfg.speed}")
        self._nav_start(c, n)
        after = self._camera_ids(c)
        new = [i for i in after if i not in before]
        if new:                                  # the pawn's auto-created camera
            self._eye = new[0]
        else:                                    # else the camera nearest the pawn
            loc = self._agent_loc(c, n)
            cams = [(np.linalg.norm(np.array([float(x) for x in
                     self._req(c, f"vget /camera/{i}/location").split()]) - loc), i)
                    for i in after if i != 0]
            self._eye = min(cams)[1] if cams else self.cfg.cam_id
        self._agent_ready = True

    def _hit(self, c, name) -> bool:
        r = self._req(c, f"vbp {name} get_hit")
        return "1" in str(r) or "true" in str(r).lower()

    def _agent_pose(self, c, name):
        loc = np.array([float(x) for x in self._req(c, f"vget /object/{name}/location").split()])
        yaw = np.deg2rad(float(self._req(c, f"vget /object/{name}/rotation").split()[1]))
        return loc, yaw

    def _nav_to(self, c, name, goal) -> None:
        self._req(c, f"vbp {name} nav_to_goal_bypath {goal[0]:.1f} {goal[1]:.1f} {goal[2]:.1f}")

    # ---- capture ----
    def capture(self, plan: EpisodePlan, out_root: Path, gpu: int | None = None) -> Episode:
        from PIL import Image

        from ..writers import write_episode

        c = self._connect()
        for cmd in self.cfg.exposure_cmds:
            self._req(c, cmd)
        rng = np.random.default_rng(plan.seed)
        agent = self.cfg.mode == "agent"
        if agent:
            need = (not self._agent_ready) or (plan.map and plan.map != self._loaded_level)
            if need:
                if plan.map and plan.map != self._loaded_level:   # load scene only on change (warm reuse)
                    self._req(c, f"vset /action/game/level {plan.map}")
                    time.sleep(self.cfg.scene_load_wait)
                    self._loaded_level = plan.map
                    self._agent_ready = False
                self._setup_agent(c)
            else:
                self._nav_start(c, self.cfg.agent_name)   # warm reuse: re-randomise the start each episode
        name, eye = self.cfg.agent_name, self._eye

        if not agent:                            # free-camera anchor (demo scene)
            loc = np.array([float(x) for x in self._req(c, f"vget /camera/{eye}/location").split()])
            yaw = np.deg2rad(float(self._req(c, f"vget /camera/{eye}/rotation").split()[1]))

        navmesh = agent and self.cfg.policy == "navmesh"
        goal = None
        if navmesh:                              # autopilot toward navmesh goals (collision-free)
            self._req(c, f"vbp {name} set_nav_speed {self.cfg.nav_speed}")
            goal = self._nav_goal(c, name)
            if goal:
                self._nav_to(c, name, goal)

        if agent and self.cfg.warmup_steps:      # let the agent start moving + auto-exposure settle
            for _ in range(self.cfg.warmup_steps):
                if navmesh:
                    time.sleep(self.cfg.frame_dt)
                else:
                    self._req(c, f"vbp {name} set_move 0 {self.cfg.linear:.1f}")
                self._req(c, f"vget /camera/{eye}/lit png")

        steps = []
        v_ang = 0.0
        for i in range(plan.steps):
            if navmesh:
                time.sleep(self.cfg.frame_dt)    # let the agent walk along its navmesh path
                png = self._req(c, f"vget /camera/{eye}/lit png")
                loc, yaw = self._agent_pose(c, name)
                if goal is None or float(np.hypot(loc[0] - goal[0], loc[1] - goal[1])) < self.cfg.goal_reach:
                    goal = self._nav_goal(c, name)
                    if goal:
                        self._nav_to(c, name, goal)
            elif agent:
                hit = self._hit(c, name)
                v_ang = (rng.choice([-1.0, 1.0]) * self.cfg.turn_max if hit
                         else float(np.clip(v_ang + rng.normal(0, self.cfg.turn_jitter),
                                            -self.cfg.turn_max, self.cfg.turn_max)))
                v_lin = 0.0 if hit else self.cfg.linear
                self._req(c, f"vbp {name} set_move {v_ang:.1f} {v_lin:.1f}")
                png = self._req(c, f"vget /camera/{eye}/lit png")
                loc, yaw = self._agent_pose(c, name)
            else:
                yaw += float(rng.normal(0, 0.06))
                loc = loc + 400.0 * np.array([np.cos(yaw), np.sin(yaw), 0.0])
                self._req(c, f"vset /camera/{eye}/location {loc[0]:.2f} {loc[1]:.2f} {loc[2]:.2f}")
                self._req(c, f"vset /camera/{eye}/rotation 0 {np.rad2deg(yaw):.2f} 0")
                png = self._req(c, f"vget /camera/{eye}/lit png")
            arr = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
            pose = Pose6DoF(loc.copy(), _yaw_quat(yaw), CoordFrame.UE_LEFT_CM)
            steps.append(Step(i, i / plan.fps, FrameRef(array=arr), pose, pose, Action.zero()))

        if len(steps) > 1:
            acts = infer_actions(
                [s.player_pose.to(CoordFrame.CANON_RH_M) for s in steps],
                [s.camera_pose.to(CoordFrame.CANON_RH_M) for s in steps],
                deadzone=self.cfg.action_deadzone,
            )
            for s, a in zip(steps, acts):
                s.action = a

        h, w = steps[0].rgb.array.shape[:2]
        meta = EpisodeMeta(
            episode_id=plan.episode_id, source=Source.UNREALZOO, viewpoint=Viewpoint.FPV,
            label_kind=LabelKind.PRECISE_ACTION, scene_id=plan.scene_id or plan.map,
            fps=plan.fps, resolution=(w, h), seed=plan.seed,
            coord_frame=CoordFrame.UE_LEFT_CM,
            extra={"license": "research-only", "mode": self.cfg.mode},
        )
        ep = Episode(meta, steps)
        write_episode(ep, out_root)
        return ep

    def healthcheck(self) -> BackendStatus:
        try:
            c = self._connect()
            ok = bool(self._req(c, "vget /unrealcv/status"))
            return BackendStatus(ok, f"UnrealCV {self.cfg.host}:{self.cfg.port} ok")
        except Exception as e:  # noqa: BLE001
            return BackendStatus(False, f"UnrealCV not reachable: {e}")
