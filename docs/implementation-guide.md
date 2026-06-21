# Matrix-Game-3.0 风格合成数据农场 · 可落地实施指南

适用对象:非 UE 专家工程团队;原则:能复用就不自建、优先选成熟方案;硬件:8×L40S / 8×A6000(48GB),无 Docker。

> 贯穿全篇的一个关键决策:**锁定 UE 5.5.4**。理由有三:(1) 本机已安装的就是 5.5.4(Engine/Build/Build.version 确认);(2) 社区与本团队核查均显示 **5.5 是 Linux/Vulkan 最后一个稳定可用版本**,5.6/5.7/5.8 仍有 `VK_ERROR_DEVICE_LOST` 回归;(3) 5.6/5.6.1–5.7.x 存在 Nanite + 硬件光追的 **VRAM 泄漏**(直到 5.8 才修)。不要追新版本。

---

## 领域 1:UE 无头逐 tick 捕获(RGB + 位姿 + 6DoF 相机 + 动作向量)

**推荐方案:自建 in-engine C++ 捕获组件,但以 fork 现成项目为骨架。** 这是唯一能匹配 MG3.0「零时间对齐误差」的路径——外部录制器(UnrealCV / Movie Render Queue / Take Recorder)做不到。
- **复用骨架**:fork `TimmHess/UnrealImageCapture`(https://github.com/TimmHess/UnrealImageCapture),它已解决最难的部分——`FRHIGPUTextureReadback` + `FRenderCommandFence` + `ENQUEUE_RENDER_COMMAND` 的非阻塞异步回读 + 异步落盘 + CustomStencil 分割 + 浮点 RT 深度。
- **自建部分**:在**同一个 tick 回调**里采样玩家 `GetActorTransform()`、相机 6DoF(`PlayerCameraManager`)、6 维动作向量,打上单调递增 frame index,并在同一回调内 `EnqueueCopy` 该帧的 GPU 回读;2–3 tick 后轮询 `IsReady()` 退役,写 `frame_<idx>.png` + 同 index 的 CSV/JSON 行。

**具体工具/API/flags**
- 回读:`FRHIGPUTextureReadback`(`RHIGPUReadback.h`,文档 https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/RHI/FRHIGPUTextureReadback)。**不要**用阻塞的 `FRenderTarget::ReadPixels`。
- RGB 取帧:
  - **第一人称(玩家真实视角,含后处理)** → `OnBackBufferReadyToPresent`(`FSlateRenderer` 委托,签名 `(SWindow&, const FTexture2DRHIRef&)`)。**已确认**该委托在 Linux/Vulkan + `-RenderOffscreen` 下会触发并给出有效 backbuffer——这正是 Pixel Streaming 的默认采集路径(https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-pixel-streaming-reference)。前提:必须是**带 viewport 的 game-client 构建**,**不是** `-nullrhi`,也**不是** commandlet / 纯 dedicated server。
  - **第三人称 / 多相机 / 深度 / 分割** → `USceneCaptureComponent2D` → 独立 `UTextureRenderTarget2D`(更干净,可控,headless 安全;代价是二次渲染)。
- 分割:**CustomDepth/CustomStencil**(runtime,headless 安全)。**禁用** MRQ Cryptomatte / ObjectId pass——那是 editor-only 的 HitProxy,`-game`/cooked/headless 下不工作(https://forums.unrealengine.com/t/objectid-cryptomatte-not-rendering-with-movie-render-queue/236478)。
- 确定性:`FApp::SetUseFixedTimeStep(true)` + `SetFixedDeltaTime(1.0/fps)`,或 `-benchmark -deterministic -fps=N`。遵循 CARLA 同步 tick 纪律(https://carla.readthedocs.io/en/0.9.9/adv_synchrony_timestep/),时间步 ≤0.1s 注意物理 substep。
- 编码:**离线** `ffmpeg -c:v h264_nvenc/hevc_nvenc`(NVENC 是独立 ASIC,不抢训练用的 CUDA 核)。**位精确训练数据请保留 PNG/raw**——NVENC "lossless" 不保证逐位一致(https://docs.nvidia.com/video-technologies/video-codec-sdk/13.0/ffmpeg-with-nvidia-gpu/index.html)。
- 启动 flags:`-RenderOffscreen -graphicsadapter=N -unattended -nosound -nosplash -log -ResX= -ResY=`。

**Linux-headless 注意**
- 回读延迟 ~2–3 帧是正常的(https://nicholas477.github.io/blog/2023/reading-rt/),但要警惕 **UE-71894 类回归**:某些版本的 lock 会触发 command-buffer flush,造成 ~15ms stall,抵消异步收益——**必须实现正确的双/三缓冲**并在 5.5.4 上实测确认无 flush(https://forums.unrealengine.com/t/ue-71894-causing-stalls-during-gpu-data-readback/455469)。
- 吞吐(fps/实例、实例/GPU)**无任何权威数字可引用**,必须实测;高分辨率 / 高帧率 / 无损输出时,**磁盘写入或编码可能成为瓶颈**,不要假设 I/O 不卡。
- 在 5.5.4 + Vulkan 上独立验证 `FRHIGPUTextureReadback` 与 backbuffer 路径(文档未枚举 RHI 支持矩阵)。

**难度/工作量:中–高。** fork + in-tick 采样器约 1–2 周;核心难点已被现成项目解决。

---

## 领域 2:NavMesh + RL 自主探索 agent

**推荐方案:先建 EQS/BT + NavMesh(Tier-1,无 RL,纯 C++/BP,headless 安全);RL 仅作为 Tier-2 可选,只替换「目标选择」节点。** MG3.0 的 RL 对"轨迹多样性"是过度工程——确定性 coverage 贪心 + EQS 打分即可复刻"coverage bonus + scene richness"。
- **先评估再自建**:在 dev 机跑 `UnrealZoo/unrealzoo-gym`(Apache-2.0,UE5.6,Linux headless,100+ 场景,已捕获 RGB+pose+action,https://github.com/UnrealZoo/unrealzoo-gym)。能用就 fork,别从零造。

**具体工具/API**
- 底层规划:`UNavigationSystemV1`(https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/NavigationSystem/UNavigationSystemV1)——`FindPathToLocationSynchronously`、`K2_GetRandomReachablePointInRadius`(探索采样核心)、`K2_ProjectPointToNavigation`(吸附)、`GetPathLength`(打分/超时估计);用 `AAIController::MoveToLocation` 驱动 pawn。NavMesh 用 **RuntimeGeneration=Static**,编辑器内 build 一次后 cook。
- 高层目标选择:**EQS**(https://dev.epicgames.com/documentation/en-us/unreal-engine/environment-query-system-overview-in-unreal-engine)——Points Donut/Grid 生成器(开 ProjectionData 吸附 navmesh)+ Trace 测试(可见性=场景丰富度代理)+ Distance + 自定义"未访问 cell"测试;用 `EEnvQueryRunMode::RandomBest25Pct` 注入随机性。coverage = floor(pos/cell) 哈希入 visited-set。
- 三重卡死检测:在 `TickComponent` 实现 (1) 位移窗口 < ε;(2) 路径超时 = `GetPathLength/speed*margin`;(3) AABB 对角线 < 阈值。配合 `OnMoveCompleted(EPathFollowingResult)` 与 `UNavigationPath::IsPartial()`。级联回退:定向覆盖 → 形状路线(Donut/Circle EQS) → 多半径重试。

**RL(Tier-2,可选)**
- 首选 **AMD Schola**(注意:prompt 里的 "NVIDIA Schola" 是误称,实为 AMD GPUOpen)——有显式 Linux 构建(`linux_dependencies.sh`)、gRPC 接 SB3/RLlib/Gymnasium、引擎内 ONNX 推理(`UNNEPolicy`,推理期无需 Python),https://github.com/GPUOpen-LibrariesAndSDKs/Schola(Schola 2.1 = UE5.5–5.7,与本机 5.5.4 匹配)。
- 次选 Epic **Learning Agents**:本机 5.5.4 的**确切类名**已核实——`ULearningAgentsManager`、`ULearningAgentsInteractor`、`ULearningAgentsPolicy`、`ULearningAgentsCritic`,以及 **LearningAgentsTraining 模块**里的 `ULearningAgentsPPOTrainer` + `ULearningAgentsTrainingEnvironment`(都继承 `ULearningAgentsManagerListener`)。**5.4 教程/代码不兼容**(5.4 是统一的 `ULearningAgentsTrainer`,5.5 已删除并拆分)。5.6/5.7 类名层面与 5.5 兼容。

**Linux-headless 注意**
- **关键区分**:nav/RL 纯逻辑可跑 `-nullrhi`;但**捕获 pass 必须 `-RenderOffscreen` + 真实 GPU**,`-nullrhi` 会出空白帧。
- **Learning Agents 的 Linux 端到端训练未被验证**:Linux 是官方支持的 PyTorch 平台,但所有官方教程都是 Windows;且其捆绑的 PyTorch 是 **cu118 旧版**,引擎会自动覆盖你手动升级的 torch。H100(sm_90)比 Blackwell 更可能被 cu118 覆盖,但**不保证**——依赖前必须在目标 GPU 上验证 CUDA kernel 真能跑(https://forums.unrealengine.com/t/is-it-possible-to-use-an-gpu-rtx-5000-series-for-learning-agents-there-is-a-problem/2682865)。

**难度/工作量:Tier-1 低–中(~1 周,全栈现成);Tier-2 中–高 + 工具链风险。**

---

## 领域 3:UE5 无头跑 Linux + 单 GPU 多实例(无 Docker)

**推荐方案:照搬 CARLA 模式(已被验证的现成路径)。**
1. **取引擎**:下载预编译的 "Unreal Engine for Linux" .zip(Epic 账号即可,无需 GitHub、无需 Docker,https://www.unrealengine.com/en-US/linux),解压跑 `Engine/Binaries/Linux/UnrealEditor`。**锁定 5.5.4**(见开篇)。只有要改引擎才从 GitHub 源码编译。
2. **cook 一次**:`RunUAT.sh BuildCookRun -platform=Linux -clientconfig=Shipping(或 Development 带 log) -cook -stage -package`,把独立二进制部署到各农场节点(节点无需编辑器)。
3. **多实例扇出**:每 GPU slot 一个进程:`./YourGame.sh -RenderOffscreen -graphicsadapter=<gpuId> -nosound -unattended -nosplash -ResX=1280 -ResY=720`。

**关键 flags / 隔离**
- **`-RenderOffscreen`(不是 `-nullrhi`)**:Vulkan 无头渲染需显式开启(UE4.25+),无 X server 也行。
- **GPU 绑定 `-graphicsadapter=N`(0-based)**。**`CUDA_VISIBLE_DEVICES` 被 UE 的 Vulkan 渲染器忽略**——但若同进程跑 CUDA 推理则需同时设它指向同一卡;CARLA 还设 `VK_ICD_FILENAMES` 强制 NVIDIA ICD(https://carla.readthedocs.io/en/0.9.11/adv_rendering_options/)。
- **无干净硬件隔离**:L40S/A6000 **不支持 MIG**;MPS 只隔离 CUDA 上下文,不隔离 Vulkan。用进程级绑定 + `systemd-run`/cgroups 限 CPU/RAM + 监控 nvidia-smi;**无法硬限单进程 VRAM**,只能靠计数 + 降 `r.Streaming` pool/质量/分辨率控制。
- **Shader/PSO warmup**:cooked 包已含 shader 字节码;残留的是 PSO 创建卡顿 → 开 **PSO Precaching**(5.3+,https://dev.epicgames.com/documentation/en-us/unreal-engine/pso-precaching-for-unreal-engine)+ 打包 bundled PSO cache。若走 commandlet 则用**共享 DDC**(网络盘,预热一次)。

**Linux-headless 注意(强制核查项)**
- **GPU 选择**:L40S(Ada)、A6000 是图形卡,适合;**H100 不适合图形渲染**——NVIDIA 官方说 H100 面向 HPC/AI,图形是非标准用途、需大量定制(https://forums.developer.nvidia.com/t/h100-pcie-doesnt-have-graphic-support/246884)。**H100 留给 ML 训练/推理(领域 5),不要拿来跑 UE 渲染。**
- **offscreen Vulkan 不保证不崩**:崩溃并非只在 4.24,5.6/5.7/5.8 仍有 `VK_ERROR_DEVICE_LOST`。**锁定 5.5.4 + 较新驱动,先做一整天 soak test(不是一次启动测试)**再投产。
- **密度"2–4 实例/48GB"是无来源估计,必须实测**。720p **不会**等比降 VRAM(VRAM 由场景内容主导,有案例 360p 仍占 1080p 的 ~90%)。务必**长时间运行下测 VRAM**(5.6/5.7 有泄漏,5.5.4 可规避但仍要验)。
- 加 supervisor(类 CARLA 的 Python 启动器)做 watchdog + 自动重启——多实例 UE 会偶发 GameThread 超时崩溃。

**难度/工作量:中。** 唯一自建是约 1 周的捕获插件(领域 1);其余抄 CARLA。

---

## 领域 4:模块化角色 + FPV/TPV 相机 + 动作随机化

**推荐方案:全部复用现成资产 + 薄 Blueprint/C++ 胶水。架构枢纽 = 统一到 UE5/UEFN Mannequin 骨架。**

**具体工具/API**
- **模块化拼装**:每槽位一个 `SkeletalMeshComponent`,父挂到 leader body,调 `SetLeaderPoseComponent`(UE5 重命名,原 Master Pose);运行时 `SetSkeletalMeshAsset` 换装、Dynamic Material Instance 调色。7 槽位 × ~14 选项 = 14⁷ ≈ 1.05e8,再乘材质参数轻松破 1e8(https://dev.epicgames.com/documentation/unreal-engine/working-with-modular-characters-in-unreal-engine)。
- **人群/吞吐**:开 SkeletalMerging 插件,`USkeletalMergingLibrary::MergeMeshes` 合并为单 mesh、单 draw call(代价:高 setup 成本、单动画、无 morph target 传递)。
- **资产**:免费 **Quantum Modular Character**(单 UE5 骨架,https://www.fab.com/listings/8e200050-3158-4762-b297-f785b5b1533d)。避开 Synty(非 Mannequin 骨架,需 IK 重定向)。
- **动画**:免费 **Game Animation Sample**(500+ mocap + motion matching:Pose Search/Motion Trajectory/Chooser,基于 UEFN_Mannequin,https://dev.epicgames.com/documentation/en-us/unreal-engine/game-animation-sample-project-in-unreal-engine);用 IK Rig + IK Retargeter 重定向一次;随机化用 `Blend Poses by Int`。
- **相机**:TP 用 `USpringArmComponent`(TargetArmLength≈300,bUsePawnControlRotation=true)+ `UCameraComponent`;FP 用挂头骨 socket 的第二个 `UCameraComponent`。**要在同一 tick 同时捕 FP+TP** → 两个 `USceneCaptureComponent2D` 各写独立 `UTextureRenderTarget2D`,6DoF 直接读 `GetComponentTransform()`。顺序切换用 `APlayerController::SetViewTargetWithBlend`。

**Linux-headless 注意**
- 上述全是 runtime 操作,配 `-RenderOffscreen` headless 安全。
- **MetaHuman strand/groom 头发:v1 默认用 card/mesh 头发,不用 groom strands。** 修正:旧的"Linux 必崩"主要是 4.27 时代;当前 5.6/5.8 文档已把 Linux 列入 Strands 支持平台(https://dev.epicgames.com/documentation/en-us/unreal-engine/groom-platform-support-in-unreal-engine)。但**没有任何来源验证 strands 在 headless `-RenderOffscreen` 离屏 Vulkan 下的表现**——所以若需照片级人物,**先在 5.5.4 的无头打包构建上实测**再决定;Groom Cards/Meshes 在所有平台都支持,是安全兜底。
- **核查 Fab 资产 License**:合成训练数据的生成与分发是否被各资产 EULA 允许(各包差异大)。

**难度/工作量:低–中。** 主要是装配 + Blueprint,无需手 K 动画。

---

## 领域 5:视频 → 相机 6DoF 位姿标注工具链(软件路线,单 H100 今天就能跑)

**推荐方案:全部复用成熟开源,只自建 ~30–100 行胶水。** 这条路镜像 MG3.0 的 ViPE + DPVO,且 H100 在这里是合适的(纯 ML 推理)。

**默认栈**
- **真实 + AI 生成视频再标注 → ViPE**(NVIDIA,https://github.com/nv-tlabs/vipe)。MG3.0 原文就用它统一再标注所有真实视频。
- **大批量游戏/citywalk 轨迹 → DPVO/DPV-SLAM**(MIT,60–120 FPS,2.5–4.9GB,https://github.com/princeton-vl/DPVO)。低显存 → 单卡可并发多进程(对应 MG3.0 的"多实例")。长序列加 `--opts LOOP_CLOSURE True`。
- **短片/低视差/SLAM 失败 → VGGT**(用 **VGGT-1B-Commercial** 商用 checkpoint,https://github.com/facebookresearch/vggt),长视频切重叠窗口。
- **离线精修/QA → COLMAP/GLOMAP**(BSD,https://github.com/colmap/colmap)。

**ViPE 正确用法(修正)**
- CLI:`vipe infer YOUR_VIDEO.mp4 --pipeline default`(或 `--pipeline dav3`)。**用 `vipe infer --help` 或 docs/usage.md 查参数,不要 `run.py --help`**(那是 Hydra 配置帮助)。输出在 `vipe_results/`。
- **没有 H100 专属 VRAM/FPS 公开数据**,论文只说"单 GPU 3–5 FPS",**必须自测**。
- **商用许可雷区(必须改配置)**:ViPE **默认** keyframe 深度是 `unidepth-l`(UniDepth-V2 = **CC BY-NC,非商用**);且**默认动态物体遮罩拉入 Segment-and-Track-Anything = AGPL-3.0 强 copyleft**——比 UniK3D 更严重。"换掉 UniK3D 就 Apache-only"是错的:这是**宽松许可的混合**。商用配置:走 `pinhole`/`wide_angle` pipeline,`keyframe_depth=metric3d`(BSD-2)或 `dav3`(Apache),`depth_align_model=null`(仅位姿)或宽松配方,`init.instance: null` 关闭 AGPL tracker。注意 **"DAv2" 不是可选的 metric/keyframe 深度模型**(它是相对深度);合法宽松替代是 Metric3D-v2 / DAv3 / MoGe。位姿质量不受影响——论文所有定量实验都用 Metric3D-v2。

**自建胶水**
- **动作标注器(~100 行,license 中性)**:把逐帧位置增量投影到相机局部系 `f=(cosθ_yaw, sinθ_yaw)`、`r=(sinθ_yaw, −cosθ_yaw)`,按 `⟨Δp,f⟩`/`⟨Δp,r⟩` 分 8 方向 → `a_t∈{0,1}^6`。WSAD 标签是**尺度无关**的,所以单目尺度模糊不影响它。
- **Plücker 编码器(~30 行)**:`d=normalize(R·K⁻¹[u,v,1]ᵀ)`,`o`=相机中心,`p=(o×d, d)∈R^6` → `(6,H,W)`,pixel-unshuffle 降到 latent 分辨率(参考 CameraCtrl https://github.com/hehao13/CameraCtrl)。**务必核对分量顺序 `(o×d,d)` vs `(d,o×d)` 与叉积符号要与下游 world-model 一致**,否则静默失效。
- **位姿坐标系归一化器**:把 ViPE/DPVO/VGGT/UE 各自输出对齐到**单一坐标约定**(UE 左手系、cm;SLAM 右手系、m)——这正是 ViPE 被引入消除"跨源不一致"的目的。
- **批处理编排器**:按 8 GPU 分片、每卡 N 进程的作业队列 + manifest。

**Linux-headless 注意**:全是 headless PyTorch 推理,无显示需求。production **避开** MASt3R-SLAM/MonST3R/UniDepth/Depth-Pro(非商用)。metric 深度商用干净的是 Metric3D-v2(BSD-2)、DAv2-Small(Apache)。

**难度/工作量:低–中。** 全复用 + 小胶水。

---

## 领域 6:AAA 游戏录制路线 + 合法性

**推荐方案:不要把它作为主路线;工具可复用,但范围必须收紧。** 三个结构性问题决定它不适合本团队:(1) 注入器全是 **Windows DLL 注入**且游戏必须**真渲染**才能录 → 无真无头,Linux 上需 Proton/Wine + Xvfb,**约 1 个重客户端/GPU**(与"单卡多无头实例"完全相反);(2) 法律上最"诱人"的标题最危险;(3) 帧版权归发行商,AI 训练 fair use 未定且倾向不利于整体复制。

**工具(若一定要做)**
- 注入器:GTA V `ScriptHookV`/`ScriptHookVDotNet`(读 `Game.Player.Character.Position`、`GameplayCamera`);RDR2 `ScriptHookRDR2`;Cyberpunk `Cyber Engine Tweaks`+`REDmod`;Palworld `RE-UE4SS`(`GetPlayerController().Pawn:K2_GetActorLocation()`);Hogwarts 被 Denuvo 封死,放弃。
- 录制:**OBS + obs-websocket v5**(OBS 28+ 自带,https://github.com/obsproject/obs-websocket)——`SplitRecordFile` 定时 60s 切片(用 Hybrid MP4 容器),订阅 `RecordFileChanged.newOutputPath` 事件把每段对应到 CSV。
- 动作推断:与领域 5 同法,**license 中性,自己写 ~100 行**。

**合法性(决策依据)**
- **GTA V / RDR2(Take-Two)、Hogwarts(WB):商用一律禁区。** EULA 禁止商用/衍生/逆向,Take-Two 积极诉讼(OpenIV、alt:V、RAGE:MP),GTA Online 上了 BattlEye 内核反作弊(永封)。
- **Cyberpunk(CDPR)、Palworld(Pocketpair):许可较宽,但明确"仅非商用"。** 只能作**非商用 R&D**,单机模式,绝不碰反作弊,任何帧进商用训练集前先过法务。
- 帧版权归发行商;美国版权局 2025-05 报告:整体复制作品通常不利于 fair use。

**Linux-headless 注意**:无真无头;Palworld Linux dedicated server 无渲染→出不了视频;Proton/Wine + Xvfb 下能否稳定 OBS 采集未经证实。

**难度/工作量:单工具低,但集成 + 法律高。不推荐作为主路线。**

---

## (a) 优先构建顺序(排名)

1. **领域 3 地基**:锁定 UE 5.5.4,dev 机装预编译编辑器,cook 一个最小 Linux 包,在**单张 L40S/A6000** 上验证 `-RenderOffscreen` + `-graphicsadapter` 并做一天 soak test。(为后续一切去风险)
2. **领域 1 捕获核心**:fork TimmHess,建 in-tick 同步采样组件(整套里唯一买不到的部分,且决定数据质量)。
3. **领域 4 内容**:Mannequin 统一骨架 + 模块化角色 + 双相机 rig + Game Animation Sample(给捕获提供可拍内容)。
4. **领域 2 Tier-1**:EQS/BT + NavMesh 探索 agent(无 RL),驱动 agent 跑动。
5. **领域 3 扇出**:supervisor + 多实例,实测每卡密度与吞吐。
6. **领域 5 标注胶水**:并行轨道,在 H100 上跑 ViPE/DPVO 给真实视频增广。
7. **领域 2 Tier-2 RL**:仅当启发式多样性不够时,只换目标选择节点(优先 AMD Schola)。
8. **领域 6**:至多作非商用 R&D 旁支,不投入主线。

## (b) 每个领域的最大风险

1. **逐 tick 捕获** — UE-71894 式回读 flush 回归会**静默重新引入 game-thread stall**、拖垮吞吐;必须在 5.5.4 + Vulkan 上验证真正的异步双/三缓冲。
2. **NavMesh+RL** — **RL 工具链在 Linux 未经端到端验证**(Learning Agents 捆绑 torch 是 cu118 旧版、会覆盖手动升级);缓解 = 坚持 Tier-1 启发式 / 用 Schola,并先验证目标 GPU 上 CUDA kernel 可用。
3. **UE-Linux 多实例** — offscreen Vulkan **崩溃**与每卡**密度**都未经证实且对版本极敏感(5.6/5.7 VRAM 泄漏、5.6+ Vulkan 回归);锁 5.5.4、soak test、实测密度,**别信"2–4"**,**别用 H100 做渲染**。
4. **模块化 + 相机** — MetaHuman groom strand 头发在 headless `-RenderOffscreen` 下表现**无人验证** → 默认用 card 头发;同时 Fab 资产 License 可能不允许合成数据再分发。
5. **位姿标注** — ViPE **默认深度(UniDepth,CC-BY-NC)+ 默认遮罩(Segment-and-Track,AGPL-3.0)会静默污染商用产出**;必须改成 `keyframe_depth=metric3d/dav3` + `init.instance=null` + `depth_align_model=null`。
6. **AAA 录制** — **法律/IP 暴露**(Take-Two 诉讼、版权、非商用条款)叠加**无法无头扩展** → 永远只作非商用 R&D,绝不作为主路线。