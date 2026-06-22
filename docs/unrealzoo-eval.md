# UnrealZoo 采用评估(对抗式)

# 决策建议：世界模型数据农场是否基于 UnrealZoo

## 结论（决断）

**走 HYBRID（双轨），但必须精确定义 HYBRID 的含义。**

把"HYBRID"拆成两种，结果完全相反：

- **"把我们的 TickCapture 插件塞进 UnrealZoo 场景"——否决。** UnrealZoo 分发的是已 cook 的封闭二进制（UnrealCV+ 插件已编译进去），无法再编译进新的 C++ 模块，且他们不分发未 cook 的 .umap/.uasset（那是买来的 Marketplace 资产）。这条物理上不可行。
- **"双轨：UnrealZoo 作为研究/引导/基准的内容后端 + 我们自有的 TickCapture 管线作为商业生产引擎"——采纳。** 这是唯一同时尊重 license 现实和 capture 保真度现实的路径。

一句话：**UnrealZoo 当研究脚手架和内容捷径（YES），不当商业数据农场的法律与吞吐地基（NO）；我们的 TickCapture + 编排器留作产品引擎。**

不要选"纯 BASE on UnrealZoo（弃用自研）"：会同时丢掉 tick 级保真度、踩上不可转让的资产 license、且物理上无法注入我们的插件。也不要选"纯保留 CUSTOM、无视 UnrealZoo"：那等于放弃一个能立即填上唯一真实缺口（无需 Epic/Fab 登录的多样化 headless 场景）的现成来源。

---

## 1. 诚实的权衡：现成场景 vs tick 同步 capture 保真度

UnrealZoo 的强项恰好是我们的弱项，反之亦然——这是它能互补而非替代的根本原因。

**UnrealZoo 赢在内容与起步速度：** ~100+ 张预编译、photoreal、game-like 的 UE5.6 场景（35 landscape / 28 community / 23 building / 15 indoor，最大 >16 km²），60+ 可控实体（人/动物/车/四足机器人/无人机），FPV+TPV，离散+连续动作（动作即标签），ground-truth 6DoF pose（比从视觉估计的 pose 干净），~70GB 一键从 ModelScope 拉，无需 Epic/Fab 登录。它直接、彻底地填上我们唯一真实的缺口。

**我们的 TickCapture 赢在世界模型最在意的那条轴：** 同一 tick 内 (RGB, 玩家 6DoF, 相机 6DoF, action) 的原子绑定、零时间偏移、固定 dt 的确定性帧节奏——这正是自回归 Matrix-Game-3.0 式世界模型学习 (frame_t, action_t → frame_{t+1}) 动力学所需。

**经 verdict 修正后，UnrealZoo 的 capture 缺陷比最初 findings 描述的要轻，但没消失：**

- **批内 pose 是一致的（修正）。** UnrealCV+ 服务端没有"原子批"这个单元，但游戏线程每 tick 用单个 `while(!PendingRequest.IsEmpty())` 循环排干整个队列、其间世界不推进——所以一个 `get_pose_img_batch` 内的对象 pose + 相机 pose 互相帧一致，常见情况下等效原子。残余风险：若 drain 在 N 条消息全部入队前启动，余下部分溢到下一 tick（可能 ~1 帧偏移）。
- **真正的偏移在"渲染图像 vs 游戏线程 pose"（修正）。** pose 取自游戏线程 transform，`lit` 像素来自渲染线程缓冲，运行态下渲染线程通常滞后 ~1 帧。这是渲染管线延迟，与批是否原子无关。`set_pause` 会同时消除该延迟，因此无法用"pause 是否消除偏移"来判断原子性。
- **depth 可能是独立一次往返。** `get_pose_img_batch` 的 `img_flag` 含 `use_depth` 可在一批内返回 depth，但 v3.0 实际路径里 depth 存在被单独 `get_depth()` 抓取的情况——多模态 depth 对齐需实测。
- **无固定时步、无 per-frame 时间戳。** gym step 循环不暂停、不记录 dt；`TimeDilationWrapper` 只是按墙钟把均值拉到 ~10 fps。WSAD-from-pose 推断需要我们补时间戳或固定 dt（或用 `set_pause` / CaptureActor 的 `record_add_timestamp`）。
- **`object_mask` 在 headless/Standalone "损坏"——证据不支持把它当成 UnrealZoo 的问题（重要修正）。** UnrealCV issue #282 是针对 mainline UnrealCV 5.2 分支、UE5.5、Windows 的 PIE-vs-Standalone 报告，**并非** UnrealZoo 的 UnrealCV+ 或其 UE5.6 二进制。UnrealZoo v3.0 自己把 object_mask 当一等公民依赖（tracking reward、批量多相机），其 ICCV 2025 基准实际上依赖它在 Standalone+headless 下工作，且无任何 UnrealZoo issue 报告它坏掉。共享血统意味着不能假定一定没问题——**要实测，但不要当成已知缺陷。**
- **吞吐是隐藏成本。** capture 走 socket 请求/响应；项目自己的 changelog 承认 lit 从 ~15 提升到 ~20 fps，README 的"60+ FPS"是最佳/聚合营销值。论文 Table 2（RTX 4090，640×480 单流）color 83 / mask 154 / depth 97；2 agent 降到 54、10 agent 降到 16。在 720p + 多模态 + pause-sync 下真实数据生成率会显著更低。这意味着"海量视频"靠的是多实例/多 GPU 扇出——而那是**我们的编排器**，UnrealZoo 不提供。

**模态修正：** surface normal **可获得**（gym `ObservationType` 枚举里没有，但 UnrealCV+ 命令级 `read_image(cam_id,'normal')` → `vget /camera/0/normal png` 可用，论文也对其 FPS 做了基准）；optical flow **不可获得**（repo/docs/paper 全无,非 UnrealCV 原生 viewmode）——光流要从我们的 pose+depth 自己算。

---

## 2. 无论选哪条路都保留什么

我们已建的引擎无关 Python 核心几乎全部留存，且正是这部分让"换后端"变便宜：

- **`backends/base.py` 的 `CaptureBackend` 接缝**——整个低成本切换的前提。
- **`schema.py`**（D_t / Episode / EpisodeMeta，含 fpv/tpv 视角与 label_kind 分桶）——UnrealZoo 观测 1:1 映射。
- **`pose.py`**（Pose6DoF / CoordFrame / `.to(CANON_RH_M)`）——必需，用来把 UnrealCV 的 UE 左手 cm/度 pose 归一化到训练用的右手米制规范坐标。
- **`action.py`**（`infer_actions` / `movement_keys` / `plucker_rays`）——连续/Mixed 动作空间与相机相对 WSAD 标注需要；离散环境直接记录"已下发的命令动作"更可靠。
- **`qa.py` / `writers.py`**（帧/CSV/meta/WebDataset tar/NVENC 视频）+ **`manifest.py`**（schema 校验 + 索引/分桶）——这才是我们的数据集产品，UnrealZoo 一概不提供。
- **`orchestrator.py`**（GPU round-robin、重试、QA gate、quarantine、索引）——复用，并成为吞吐杠杆（N 二进制 × 端口 × GPU）。
- **TickCapture C++ 插件**——保留为**保真度天花板**，只服务于我们自行授权的 hero 场景轨道（见下）。这是我们的差异化，不丢。

ADOPT 路径下变冗余/退役的：`ExplorerCharacter` 漫游 agent、`SpawnTestScene` 运行时测试场景、`import_glb.py` / `make_test_map.py`、`ue_capture.sh`——这些当初存在只是因为没内容，被 UnrealZoo 场景 + NavMesh/waypoint 导航 + population control 取代。可复用的内核（覆盖/多样性意图）改写成 Python 策略给 `env.step()` 选动作。

---

## 3. 推荐的具体集成

**是的——在我们现有 `CaptureBackend` 接口后面实现 `UnrealZooBackend`。** 单文件 `datafarm/backends/unrealzoo.py`，核心保持引擎无关。

```
class UnrealZooBackend(CaptureBackend):  name = "unrealzoo"
```

- **plan(job)**：把 `job.scenes` 解析成 UnrealZoo env-id `Unreal{Task}-{Map}-{ActionSpace}{ObservationType}-v0`（如 `UnrealTrack-Map_ChemicalPlant_1-DiscreteColor-v0`；用 ColorMask/Rgbd 叠加 Mask/Depth）；fpv/tpv → 选哪个相机；按 scene × viewpoint × seed round-robin。
- **capture(plan, out_root, gpu)**：设 `CUDA_VISIBLE_DEVICES`（或 `-graphicsadapter`）+ 唯一 IPC/TCP 端口；`gym.make` → `reset(seed)` → 由我们的覆盖策略选动作 → `env.step()`。读取用 **`get_pose_img_batch(objs_list, cam_ids, img_flag)`**，**单次往返**返回 `(obj_pose_list, cam_pose_list, img_list, mask_list, depth_list)`；对齐要紧时在批前 `set_pause()`（注意 CaptureActor 录制子系统需 UnrealCV server ≥ 2.0.0，且 paused 帧有 TAA/Lumen 收敛问题，需 `set_warmup_frames`）。pose 用 `get_cam_pose(cam_id)` 取相机、`get_obj_pose(obj)` 取玩家（**没有** `get_player_pose/get_camera_pose` 这种名字）。把"已下发命令动作"作为 `label_kind=PRECISE_ACTION` 写入；`Pose6DoF(frame=UE_LEFT_CM)`。
- **复用 writer**：`write_episode(ep, out_root)` 原样调用。
- **小改动**：`schema` 加 `Source.UNREALZOO`；`pose.py` 加 UE 左手 `Euler[x,y,z,roll,yaw,pitch]→quat`（度→弧度）的 ingest；动作 remap（他们的 turn-left/right 是 yaw 转向 vs 我们的 strafe；他们有 crouch/hold、我们有 attack）。
- **healthcheck()**：验 `$UnrealEnv`/二进制存在、`import gym_unrealcv` OK、probe `gym.make+reset` 返回非空帧 + 有限 pose、GPU 可见。
- **orchestrator** 加 per-instance 端口/GPU launcher。

工作量：后端 ~300–500 LOC + pose ingest + 动作 remap + launcher；约 1–2 周出第一份真实标注数据集。长杆在 ops/吞吐/license，不在代码。

`assets.py`（AssetCatalog + GateConfig）从"资产库场景"改造成对 UnrealZoo env-id 的**白名单 + 质量/license 闸**（哪些场景/agent/obs-mode 可入数据集）。

---

## 4. License / headless 坑（已应用 verdict 修正）

**License（商业 go/no-go，比工程更关键）：**

- Apache 2.0 只覆盖**代码**，不授予任何资产权利。场景来自 UE Marketplace/Fab，受上游 **Epic Content EULA**（https://www.unrealengine.com/eula/content）约束。
- 修正：资产**并非绝对不可再分发**——EULA 允许在"作为 Project 不可分割的一部分以 object code 形式"分发（这正是 UnrealZoo 能合法分发打包二进制的依据）；被禁止的是"以独立形式"转让资产。
- 但把**渲染出的 2D 帧/视频作为独立训练数据集发布**——EULA 没明确覆盖，状态**模糊，发布前必须核实**。
- **最关键、最初 findings 漏掉的事实：Fab 的 NoAI 元标签**（https://support.fab.com/s/article/Generative-Artificial-Intelligence-AI）。被打 NoAI 标的资产"不得用于生成式 AI 数据收集"——对任何 NoAI 源资产，数据集用途不是"未说明"而是**可能被明确禁止**。必须逐资产核查 Fab license tier + NoAI 状态（参考 https://dev.epicgames.com/documentation/en-us/fab/licenses-and-pricing-in-fab）。
- **结论：研究/RL 基准用途 OK；商业世界模型训练数据 = 在拿到书面授权前，一律按"仅研究"处置。** 可发邮件问作者（zfw1226@gmail.com）是否存在商业/ML 训练授权；无书面授权则不要发布任何用其渲染训练的模型/数据集。这条对 ADOPT 和任何 hybrid 都适用。

**Headless（已修正，注意是 Vulkan 不是 EGL）：**

- 离线渲染机制**已确认**：launcher 发 `-RenderOffScreen`、`-graphicsadapter=N`、`-nullrhi`，**默认 Vulkan**（`-opengl` 才切 OpenGL）；user guide 明确写"Server deployment: offscreen=True"。非 docker 路径用 `subprocess.Popen` 直接跑、不注入 DISPLAY、不套 xvfb——**设计上支持 no-X headless**。
- 但"完全无 X server 的 turnkey"**未被任何 primary source 明说**，且他们自己的 docker 启动脚本硬编码了 `-e DISPLAY=$DISPLAY -e SDL_VIDEODRIVER=x11`——假定宿主有 X。所以零-X 路径要**自己在农场上验证**。
- **版本风险：UnrealZoo v3.0 二进制是 UE5.6**，正是我们 SPEC §3 因 Linux/Vulkan `VK_ERROR_DEVICE_LOST` 回归而**刻意避开**的版本；二进制预编译、无法降级。论文只在 RTX 4090 + Windows 下基准过，**没有任何 A6000/L40S 等数据中心 GPU 的 Linux headless 验证、无 device-lost 讨论**。我们 5.5.4 的锁在这里**不再保护**——必须 soak-test。
- **下载（修正）：** 无需 ModelScope/Alibaba 账号（数据集公开，匿名 302 到签名 CDN，206 返回真实字节）。但 README 宣称的"GitHub + ModelScope"双通道是**误导**——只有 ModelScope，且包是 74–76GB 的分卷 tarball（超 GitHub release 上限）。内容走中国区 CDN（`cdn-lfs-cn-1.modelscope.cn`），**无非中国镜像兜底**，境外下载速度**存疑/慢**，需提前规划。

---

## 5. 如果 UnrealZoo 不合适：单一最佳替代

**SimWorld**（NeurIPS 2025 spotlight，arXiv 2512.01078，https://github.com/SimWorld-AI/SimWorld）。

理由：它精准解决 UnrealZoo 的两大致命弱点——**开源 UE5 + 同样基于 UnrealCV+**，意味着我们**可以把自己的 capture/插件集成进去、可编辑、可控 license**；程序化城市生成给出近乎无限的场景，量与可编辑性都胜过 UnrealZoo。代价：场景多样性/game-breadth 不如 UnrealZoo（偏城市/社会 agent），photoreal 质量为程序化拼装、成熟度未经生产级验证。

次选（按域）：**CARLA**（https://carla.readthedocs.io/）——免费、可编辑、headless Linux 成熟、license 干净，但仅驾驶/城市、FPV 是车载视角；适合做"城市驾驶切片"，不是 game-scene 主干。

而面向商业模型的**最干净长期路径**仍是：**自行授权 UE 场景**（Fab/Quixel 选允许 ML 用途且非 NoAI 的 tier、Synty/KitBash3D、免费 UE5 City Sample、或委托/自建），喂进我们自己的 TickCapture 管线——这才是 tick 保真度 + 可再分发 license 同时成立的地方。多源策略也有先例：Matrix-Game 2.0（arXiv 2508.13009）就是 615h UE + 153h Minecraft + 85h Sekai 混合训练的，单一固定来源不够。

---

## 6. 排序行动计划

1. **（本周）拉 UnrealZoo UE5.6 ~70GB 包并跑通 headless。** 从 ModelScope（https://www.modelscope.cn/datasets/UnrealZoo/UnrealZoo-UE5）下载（无需账号，但走中国 CDN、分卷、慢，预留带宽）；在一台 A6000 上做 `-RenderOffScreen` + `-graphicsadapter` 的 Vulkan 离线 soak 测试，专盯 `VK_ERROR_DEVICE_LOST`（UE5.6 是我们 SPEC 避开的版本，这是头号工程闸）。

2. **（并行，最高优先级）法务定性。** 逐资产核查 Fab license tier + NoAI 标；判定"用 UnrealZoo 渲染帧作为（商业）世界模型训练数据"是否可行。这是真正的 go/no-go，不是工程问题。同步发邮件 zfw1226@gmail.com 问商业/ML 授权。**在书面授权到手前，UnrealZoo 数据一律标记"仅研究"。**

3. **实现 `datafarm/backends/unrealzoo.py: UnrealZooBackend(CaptureBackend)`** + `Source.UNREALZOO` + pose Euler ingest + 动作 remap + orchestrator per-instance launcher。用它把整套引擎无关核心（schema/pose/action/qa/writers/manifest/orchestrator）端到端跑在真实多样场景上，产出**仅研究用 v0 数据集**，验证世界模型训练 loop 与 WSAD-from-pose 推断。

4. **跑两个量化对照实验。**（a）在 UnrealZoo 二进制上实测 `object_mask` 在 headless/Standalone 是否真的工作（不要因 issue #282 而假定它坏）；实测 `get_pose_img_batch` 内 depth 是否与 RGB 同帧。（b）在 1280×720 + pause-sync 下测单实例真实数据生成 FPS，据此给多实例扇出定容量。同时把 UnrealZoo socket capture 的对齐误差/吞吐 head-to-head 对比我们的 TickCapture，量化我们的优势。

5. **保留 Track B（商业生产引擎）：** TickCapture + 我们的 .uproject + orchestrator，喂自行授权场景（Fab/Quixel 非 NoAI tier、Synty/KitBash、City Sample、委托）。这是出货商业数据集的唯一合规且 tick 保真的轨道。从主线弃用 `SpawnTestScene` / `ExplorerCharacter` / import 脚本，TickCapture 收敛为 hero-scene 保真度轨道。

6. **若步骤 1 或 2 失败（headless 不稳 / license 禁用），切到 SimWorld**（开源 UE5、可注入我们的 capture、可控 license）作为内容主干，CARLA 作驾驶切片；不要回退到"纯无内容自研"。

---

**净结论：** UnrealZoo 对"它能否交给我们现成、可用、headless-Linux 的场景？"的回答是——**研究 YES、商业 NO**：内容技术上就绪，但法律上不归我们用来变现。因此 ADOPT 它做研究后端与基准（`UnrealZooBackend`），KEEP 我们的 TickCapture + 编排器做商业生产引擎，**拒绝**"把插件塞进其封闭二进制"式的 HYBRID。

相关文件：`/root/nas/bigdata1/cjw/projs/datafactory/datafarm/backends/base.py`、`/root/nas/bigdata1/cjw/projs/datafactory/datafarm/schema.py`、`/root/nas/bigdata1/cjw/projs/datafactory/datafarm/pose.py`、`/root/nas/bigdata1/cjw/projs/datafactory/datafarm/action.py`、`/root/nas/bigdata1/cjw/projs/datafactory/datafarm/orchestrator.py`，新增 `/root/nas/bigdata1/cjw/projs/datafactory/datafarm/backends/unrealzoo.py`。