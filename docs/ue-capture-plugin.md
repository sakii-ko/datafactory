# TickCapture 插件设计 (P6)

UEBackend 的核心、唯一买不到的部分:在 UE5 无头进程里**逐 tick 同步**采集 M-G3 的
`D_t = (RGB, 玩家位姿, 相机6DoF, 6维动作)`,零时间对齐误差,异步回读不卡渲染线程。
参考骨架:`TimmHess/UnrealImageCapture`(已解决异步回读+落盘)。

## 形态

UE 插件 `ue/DataFarmCapture/Plugins/TickCapture/`,核心类 `ATickCaptureManager : AActor`。
进程启动时从一个 **render manifest(JSON)** 读配置(由 Python UEBackend 写),驱动整段采集,
产出与 `datafarm` schema 完全一致的 `frames/NNNNNN.png + steps.csv + meta.json`,
这样 `datafarm.writers.read_episode` 可直接读回、跑 QA、入库。

## render manifest(Python→UE 的契约)

```json
{
  "episode_id": "ue_00001",
  "out_dir": "/abs/out/ue_00001",
  "width": 1280, "height": 720, "fps": 16,
  "num_frames": 256,
  "viewpoint": "tpv",
  "seed": 12345,
  "scene": "/Game/Maps/Demo",
  "warmup_frames": 8
}
```

通过命令行 `-CaptureConfig=/abs/render_manifest.json` 传入。

## 采集机制(每 tick,固定时间步)

- **固定时间步**:`FApp::SetUseFixedTimeStep(true)` + `FApp::SetFixedDeltaTime(1/fps)`,
  保证帧间隔确定、与物理同步;或命令行 `-fps=N -benchmark`。
- **RGB**:`USceneCaptureComponent2D` → `UTextureRenderTarget2D`(RGBA8,关 HDR)。
  对 TPV/FPV 都用同一机制(摄像机组件随视角放置),headless 安全。可加第二个 capture
  出深度(RTF_RGBA32f→EXR)与分割(CustomStencil 后处理材质)——v1 先只出 RGB。
- **同 tick 采样**(`TickComponent`/`Tick`,在 `EnqueueCopy` 之前):
  玩家 `GetActorTransform()`、相机 `SceneCapture->GetComponentTransform()`、动作向量
  (来自 P7 agent 经 `SetAction(uint8[6])` 注入;P6 独立测试时为零)。打单调帧号。
- **异步回读**(关键,避免 game-thread stall):
  `ENQUEUE_RENDER_COMMAND` 里对 RT 的 `FRHITexture` 调 `FRHIGPUTextureReadback::EnqueueCopy`;
  入队一个 `FRenderRequest{readback, fence, frameIndex, pose-row}` 到 `TQueue`。
  每 tick 轮询队首:`fence.IsFenceComplete() && readback.IsReady()` → `Lock(rowPitch)` 拷贝 →
  `Unlock()` → 丢给 `FNonAbandonableTask` 异步存 PNG + 追加 CSV 行。**双/三缓冲**,
  绝不在 game thread 上 flush(TimmHess 强调的优化)。回读延迟 ~2–3 帧属正常。
- **结束**:采到 `num_frames`(+warmup 丢弃)后,等待队列排空 → 写 `meta.json` → `RequestExit`。

## CSV 列(对齐 datafarm schema)

`index,t,rgb,player_x..z,player_qwxyz,cam_x..z,cam_qwxyz,forward,back,left,right,jump,attack`
坐标系:UE 原生 = `ue_left_cm`(写入 meta.coord_frame),Python 侧用 `Pose6DoF.to(CANON_RH_M)` 归一。

## 风险(implementation-guide §b1)

- **UE-71894 类回读 flush 回归**会静默重新引入 stall → 必须实测异步无 flush(5.5.4+Vulkan)。
- ObjectId/Cryptomatte 分割是 editor-only → 分割走 CustomStencil runtime。
- 吞吐无权威数字 → 高分辨率/无损时磁盘写入可能成瓶颈,实测。

## 验证(P6 完成判据)

1. headless `-RenderOffscreen` 跑通,产出 N 帧 PNG + steps.csv,`read_episode` 能读回。
2. 帧号-位姿-动作严格同 tick(对齐误差 0):用一个已知运动的测试关卡核对。
3. 长跑无 game-thread stall(看 `stat unit` / 帧时间平稳)。
4. 先在 H100 验证产出正确性(慢可接受),再在 duan78(A6000)验证吞吐。
