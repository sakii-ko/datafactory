from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

PORT_BASE, PORT_BAND = 9000, 8


class EnvCrashed(RuntimeError):
    pass


def slot_layout(n_envs: int, adapters: list[int]) -> list[tuple[int, int]]:
    # slot i -> (vulkan adapter index for -graphicsadapter, base UnrealCV port)
    return [(adapters[i % len(adapters)], PORT_BASE + i * PORT_BAND) for i in range(n_envs)]


def _ini_path(launcher: str) -> Path:
    p = Path(launcher)  # .../Linux/<Project>.sh -> .../Linux/<Project>/Binaries/Linux/unrealcv.ini
    return p.parent / p.stem / "Binaries" / "Linux" / "unrealcv.ini"


@dataclass
class UEProcess:
    launcher: str
    adapter: int
    port: int
    screen: str = "1280x720x24"
    log_path: str = ""
    proc: subprocess.Popen | None = None
    _log: object = None

    def start(self) -> None:
        # The binary reads its port from unrealcv.ini next to the binary (else default 9000).
        ini = _ini_path(self.launcher)
        ini.parent.mkdir(parents=True, exist_ok=True)
        ini.write_text(f"[UnrealCV.Core]\nPort={self.port}\nWidth=1280\nHeight=720\nFOV=90\n")
        self._log = open(self.log_path, "ab") if self.log_path else None   # noqa: SIM115
        out = self._log or subprocess.DEVNULL
        cmd = ["xvfb-run", "-a", "-s", f"-screen 0 {self.screen}",
               self.launcher, "-nosound", "-unattended", f"-graphicsadapter={self.adapter}"]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=out,
                                     stderr=subprocess.STDOUT, start_new_session=True)

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def kill(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        if self._log:
            self._log.close()
            self._log = None
        self.proc = None


class EnvSlot:
    def __init__(self, idx, adapter, base_port, launcher, proto, ready_timeout, launch_lock, log_dir):
        self.idx, self.adapter, self.base_port = idx, adapter, base_port
        self.launcher, self.proto, self.ready_timeout = launcher, proto, ready_timeout
        self.launch_lock = launch_lock
        self.log_path = str(Path(log_dir) / f"slot{idx}.log")
        self._off = 0
        self.proc = None
        self.backend = None
        self.current_level = None

    @property
    def port(self) -> int:
        return self.base_port + (self._off % PORT_BAND)

    def launch(self) -> None:
        # Serialize cold starts: all instances share one unrealcv.ini, so write-port -> start ->
        # wait-until-listening must be atomic per instance (the binary reads the ini at startup).
        with self.launch_lock:
            self.proc = UEProcess(self.launcher, self.adapter, self.port, log_path=self.log_path)
            self.proc.start()
            self.backend = self.proto.for_slot(self.adapter, self.port)
            self.backend._alive = self.proc.is_running
            self.backend.open(self.ready_timeout)   # connect + status gate; raises EnvCrashed
        self.current_level = None

    def relaunch(self) -> None:
        try:
            if self.backend:
                self.backend.close()
        finally:
            if self.proc:
                self.proc.kill()
        self._off += 1   # next port in the band -> dodge ~45s TIME_WAIT on the old one
        self.launch()

    def run_episode(self, plan, out_root):
        if not self.proc.is_running():
            raise EnvCrashed(f"slot{self.idx} dead pre-capture")
        ep = self.backend.capture(plan, out_root, gpu=self.adapter)
        if not self.proc.is_running():
            raise EnvCrashed(f"slot{self.idx} died mid-capture")
        self.current_level = plan.map or self.current_level
        return ep

    def teardown(self) -> None:
        try:
            if self.backend:
                self.backend.close()
        finally:
            if self.proc:
                self.proc.kill()


class LevelQueue:
    """Thread-safe plan queue grouped by scene (plan.map); hands a worker the level it already
    has loaded to avoid the ~12s reload, retries first, else the largest remaining level."""

    def __init__(self, plans):
        self._by = defaultdict(deque)
        for p in plans:
            self._by[p.map].append(p)
        self._retry = deque()
        self._lock = threading.Lock()

    def take(self, level):
        with self._lock:
            if self._retry:
                return self._retry.popleft()
            q = self._by.get(level)
            if q:
                return q.popleft()
            best = max((q for q in self._by.values() if q), key=len, default=None)
            return best.popleft() if best else None

    def requeue(self, plan):
        with self._lock:
            self._retry.append(plan)


@dataclass
class EpisodeResult:
    plan: object
    episode: object | None
    error: str | None
    attempts: int


class EnvPool:
    """W warm UnrealZoo envs (one per GPU/port), each owned by one worker thread that pulls
    episodes from a shared level-affinity queue. Crash -> kill+relaunch (never reconnect) -> requeue."""

    def __init__(self, plans, proto, launcher, adapters, n_envs, out_root,
                 ready_timeout=180.0, max_retries=2):
        self.layout = slot_layout(n_envs, adapters)
        self.queue = LevelQueue(plans)
        self.results = queue.Queue(maxsize=2 * n_envs)   # bounded -> backpressure on the QA consumer
        self.launcher, self.out_root = launcher, out_root
        self.proto, self.ready_timeout, self.max_retries = proto, ready_timeout, max_retries
        self.log_dir = Path(out_root) / "_envs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._stop = threading.Event()
        self._launch_lock = threading.Lock()
        self._slots = []
        self._threads = []

    def _cleanup(self) -> None:
        # Kill stale UE binaries from prior runs. Match the binary path ("<stem>/Binaries"), which the
        # farm process's own cmdline lacks (it carries "--binary .../<stem>.sh") — avoids self-SIGKILL.
        subprocess.run(["pkill", "-9", "-f", f"{Path(self.launcher).stem}/Binaries"],
                       stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        time.sleep(45)   # let the UnrealCV port TIME_WAIT clear before rebinding

    def _worker(self, idx):
        adapter, base = self.layout[idx]
        slot = EnvSlot(idx, adapter, base, self.launcher, self.proto, self.ready_timeout,
                       self._launch_lock, self.log_dir)
        self._slots.append(slot)
        try:
            slot.launch()
        except Exception:
            return   # other workers cover the shared queue
        try:
            while not self._stop.is_set():
                plan = self.queue.take(slot.current_level)
                if plan is None:
                    return
                att = plan.extra.get("_attempts", 0)
                try:
                    ep = slot.run_episode(plan, self.out_root)
                    self.results.put(EpisodeResult(plan, ep, None, att + 1))
                except (EnvCrashed, ConnectionError, OSError) as e:
                    plan.extra["_attempts"] = att + 1
                    if att + 1 <= self.max_retries:
                        self.queue.requeue(plan)
                    else:
                        self.results.put(EpisodeResult(plan, None, f"crashed {att+1}x: {e}", att + 1))
                    try:
                        slot.relaunch()
                    except Exception:
                        return   # plan already requeued/terminal above; don't double-count, just exit
                except Exception as e:   # non-crash capture error: keep the env, report this plan
                    self.results.put(EpisodeResult(plan, None, str(e), att + 1))
        finally:
            slot.teardown()

    def start(self):
        self._cleanup()
        self._threads = [threading.Thread(target=self._worker, args=(i,), daemon=True)
                         for i in range(len(self.layout))]
        for t in self._threads:
            t.start()
        return self._threads

    def shutdown(self):
        self._stop.set()
        try:
            while True:
                self.results.get_nowait()   # unblock any worker parked on a full results.put
        except queue.Empty:
            pass
        for s in list(self._slots):
            try:
                s.teardown()
            except Exception:
                pass
