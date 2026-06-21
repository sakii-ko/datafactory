# 用 Unreal Engine 在多卡 Linux 服务器上搭建交互式世界模型数据农场:完整技术报告

> 适用读者:不熟悉 Unreal Engine(以下简称 UE)、希望在 8×L40S / 8×A6000 Linux 服务器上做批量合成数据生产、用于训练交互式世界模型(world model)的工程团队。
> 说明:文中带「估算」标签的数字是工程经验值,无官方发布,务必在你的真实场景上实测;带「不确定」标签的是当前公开资料无法证实的点。

---

## 1. 一句话结论 + 关键事实校正

**一句话结论**:训练交互式世界模型的核心数据是「带逐帧动作标签的视频轨迹」((过去帧 + 过去动作) → 下一帧);用 UE 做合成数据是可行且已被验证的路线(Matrix-Game 2.0/3.0 是最直接的范例),但在你这个体量上,务实做法是**先用现成的 CARLA / UnrealCV / 现成 UE 场景跑通最小闭环**,再扩到自建场景与农场规模;农场的正确架构是**每张 GPU 跑一个独立的无头 UE 进程**(不是把一次渲染拆到多卡),真正的瓶颈往往是 GPU→CPU 回读 + 无损压缩 + 磁盘 IO,而**最大的非技术风险是 UE EULA 的「生成式 AI」限制条款**。

**关键事实校正(尤其是 "Matrix-Game 3.0"):**

- **Matrix-Game 3.0 是真实存在且完全开源的,不是传闻。** 它在 2026 年初发布(一处二手来源称 2026 年 3 月),代码 + 权重 + 技术报告 PDF 全部开源,采用 MIT 许可。官方定位为「720p @ 40FPS、5B 模型、分钟级记忆一致性、在 Unreal Engine + AAA 游戏上训练」。注意:**它的技术报告只以 PDF 形式放在 GitHub 仓库里(`Matrix-Game-3/assets/pdf/report.pdf`),没有 arXiv 预印本**,因此 3.0 的确切数据规模(小时数/帧数)从未公开披露。来源:[GitHub](https://github.com/SkyworkAI/Matrix-Game)、[HuggingFace](https://huggingface.co/Skywork/Matrix-Game-3.0)、[项目页](https://matrix-game-v3.github.io/)、[官方 X 公告](https://x.com/Skywork_ai/status/2039305679966720411)。
- **Matrix-Game 三个版本全部真实存在、全部 MIT 开源**(代码 + 权重)。UE 在三代数据管线中都是核心,且作用逐代扩大。
- 校正一(1.0):此前说「1.0 的 UE 部分占比无法量化」**不准确**。论文实际给了大致比例——「约一半 labeled 数据来自 MineRL 场景(覆盖 14 个 Minecraft biome)」,即另一半大致来自 UE 程序化仿真,**约 50/50**(只是没列出完整 UE 资产清单)。同时,把 1.0 的 UE 场景称为「Minecraft 风格 biome」是**错误的**:UE 环境是高保真、可脚本化的场景,涵盖 urban(城市,这根本不是 Minecraft 的 biome)、desert、forest,专门用来超越 Minecraft 提升视觉多样性和控制精度。来源:[arXiv:2506.18701](https://arxiv.org/html/2506.18701v1)。
- 校正二(Oasis 数据来源):此前说「Oasis 训练数据官方未披露,只是从 DIAMOND 血统推断与 VPT 有关」——**这是错的,已被推翻**。Oasis 的共同开发方 Etched 官方账号在 X 上(2024-11-01 前后)明确说:「它纯粹训练于开源数据 VPT,即 OpenAI 开源的 Minecraft 数据集(MIT 许可)」。所以**数据来源是官方披露过的**。两点保留:(a) 披露来自 Etched 而非 Decart(Decart 自己的页面、open-oasis README、HF 卡片均未提);(b) 说「VPT 承包商数据」是过度具体化——Etched 只笼统说了「VPT」,而 VPT 同时含约 2k 小时承包商演示 + 约 70k 小时 IDM 标注的网络视频。来源:[Etched X](https://x.com/Etched/status/1852387549580496918)、[OpenAI VPT](https://openai.com/index/vpt/)。
- 校正三(UE 多卡选卡):`-graphicsadapter=N` **不能假定**映射到固定物理卡,也**不能假定**等于 CUDA/NVENC 的设备序号(详见第 5、7 节)。可靠做法是每个实例独占一卡的容器化隔离。
- 校正四(UE EULA 生成式 AI 条款):该条款确实存在,但**流行的引文是变更日志的转述,不是正式条文**;正式条文有限定语(详见第 9 节)。

---

## 2. 世界模型数据管线全景:谁用了 UE 合成数据,谁用真实/网络视频

下面把主流交互式/可玩/生成式世界模型按**数据来源**分类。判断「是否用了 UE 渲染合成数据」时要区分三种情况:① 真正搭建了 UE 合成数据生产管线;② 数据恰好来自某个用 UE4 做的商业游戏(帧是 UE 渲染的,但属于真人/网络录制,不是合成生产);③ 完全不涉及 UE。

### 2.1 Matrix-Game 家族(Skywork AI)——本报告最相关的标杆

| 版本 | 模型 | 数据来源(UE 角色) | 关键参数 |
|---|---|---|---|
| **1.0**([arXiv:2506.18701](https://arxiv.org/abs/2506.18701)) | 17B image-to-world DiT(仅 Minecraft) | Matrix-Game-MC:~2,700h 无标注 + ~1,200h(65 帧训练)/~1,026h(33 帧训练)有标注;有标注约 **50% 来自 MineRL+VPT 代理**,另约 50% 来自 **UE 程序化高保真场景**(urban/desert/forest,逐帧真值:离散动作、连续注视向量、运动学、交互结果) | 720p,16Hz;6 键盘 + 8 鼠标方向动作;3D Causal VAE(8×空间/4×时间);flow matching |
| **2.0**([arXiv:2508.13009](https://arxiv.org/abs/2508.13009)) | 1.8B 实时流式自回归扩散(基于 Wan 2.1 I2V) | **核心 ~800h 有标注**:UE **615h** + Minecraft 153h + Sekai(真实步行视频)85h;**额外微调**:GTA5 驾驶 574h + Temple Run 560h。注意「~1200h」头条数字 = UE+GTA5 管线产出(615+574≈1189),**不含** Minecraft/Sekai/Temple Run | 352×640,25 FPS(单张 H100);57 帧片段;Self-Forcing 蒸馏 + 因果 DiT + KV-cache |
| **3.0**([GitHub/Matrix-Game-3](https://github.com/SkyworkAI/Matrix-Game/tree/main/Matrix-Game-3)) | 记忆增强 DiT,5B base + 28B-MoE(2×14B) | **三支柱「工业级无限数据引擎」**:① UE 合成场景(可控、全标注)② 大规模**自动化采集商业 AAA 游戏** ③ 真实视频增强;产出 **Video-Pose-Action-Prompt 四元组**。规模未公开 | 720p(704×1280),40 FPS;Plücker 相机记忆;error-buffer 自纠错;DMD 蒸馏 + INT8 + MG-LightVAE(~5.2× 加速) |

演进脉络:**仅 Minecraft(1.0)→ UE/GTA5/真实视频混合(2.0)→ AAA 游戏 + UE + 真实视频走向照片级开放世界(3.0)**。

**2.0 的 UE 数据生产法(最值得抄)**:UE 原生 NavMesh 路径规划(查询延迟 <2ms)+ PPO 强化学习代理自动探索(奖励 R = α·避碰 + β·探索效率 + γ·轨迹多样性)+ UE「Enhanced Input」系统毫秒级捕获多键同按并与渲染帧同步 + 四元数双精度相机控制(旋转误差 ~0.2%)+ 冗余帧过滤与基于速度的非物理运动剔除。GTA5 部分用「Script Hook」+ C# mod 导出 JSON 动作,与 OBS 录制的 MP4 同步,域随机化车辆密度[0.1,2.0]、NPC 密度[0.2,1.5]。

### 2.2 其它世界模型:数据来源对照

**(A)以大规模网络视频为主(无 UE 合成管线):**
- **Genie 1**([arXiv:2402.15391](https://arxiv.org/abs/2402.15391)):11B,纯公开网络游戏视频,从 ~24.4 万小时/5500 万片段过滤到 **3 万小时/680 万 2D 平台游戏片段**(ResNet18 质量分类器),160×90 @10fps。**无游戏引擎合成数据**;用 VQ-VAE 学 8 个**无监督潜动作码**(无需任何动作标签)。
- **Genie 2 / 3**([Genie 2](https://deepmind.google/blog/genie-2-a-large-scale-foundation-world-model/)、[Genie 3](https://deepmind.google/blog/genie-3-a-new-frontier-for-world-models/)):仅披露「大规模视频数据集」;SIMA 智能体只用于**评测**生成世界,不是训练数据来源。无 UE 披露。(不确定:2/3 的「网络视频」假设是从 Genie 1 外推,未经证实。)
- **Vista**([arXiv:2405.17398](https://arxiv.org/abs/2405.17398)):~2,000h OpenDV-YouTube 驾驶视频 + nuScenes,纯真实,无合成。
- **Mirage**(Dynamics Lab,[blog](https://blog.dynamicslab.ai/)):公司宣称训练于「海量网络游戏视频 + 真人交互」,无论文/数据集,**可信度低**。
- **Lucid**(YC,[launch](https://www.ycombinator.com/launches/Mpr-lucid-generative-simulations-powered-by-fast-world-models)):宣称 ~200h Minecraft、RTX 4090 上 20+ FPS,仅创业宣传,**可信度低**。

**(B)真实第一方游戏/驾驶日志:**
- **Microsoft WHAM/Muse**([Nature](https://www.nature.com/articles/s41586-025-08600-3)、[HF](https://huggingface.co/microsoft/wham)):~10 亿图像 + 手柄动作 = 7 年 / ~50 万真人 Bleeding Edge 对局,300×180。**关键细节**:Bleeding Edge 本身是 UE4 游戏,所以**帧是 UE4 渲染的,但这是真人日志,不是合成生产管线**。开源权重 + 样本数据。
- **Wayve GAIA-1/2/3**([GAIA-2](https://wayve.ai/thinking/gaia-2/)):真实车队驾驶视频(GAIA-1 ~4,700h 英国;GAIA-3 ~9 国),训练中**无引擎合成数据**。

**(C)程序化代理/引擎数据:**
- **GameNGen(DOOM)**([arXiv:2408.14837](https://arxiv.org/abs/2408.14837)):PPO 代理在**真实 VizDoom/id Tech 引擎**里玩(1000 万环境步),录制约 **9 亿帧**;SD1.4 衍生模型从过去 64 帧 + 64 动作预测下一帧。**不是 UE**。这是「RL 代理采集 + 动作条件下一帧训练」最清晰的蓝图。
- **GameFactory(GF-Minecraft)**([arXiv:2501.08325](https://arxiv.org/abs/2501.08325)):MineDojo API 采集 70h/2000 片段,平衡化原子动作,**无 UE**。
- **Oasis / open-oasis**([GitHub](https://github.com/etched-ai/open-oasis)):DIAMOND 式扩散,360p @20fps;**官方披露训练于 VPT(OpenAI 开源 Minecraft 数据,MIT)**(见第 1 节校正);学的是 Minecraft 像素,非引擎渲染合成。
- **NVIDIA Cosmos**([arXiv:2501.03575](https://arxiv.org/abs/2501.03575)):~2000 万原始视频小时 → ~10⁸ 片段,9 大类;其中**「合成渲染」仅占 4%,且论文未说明用什么引擎**(已核实:全文无 Omniverse/Isaac/Unreal/Unity/Blender 字样)。注意 Cosmos 把「电子游戏画面」过滤**出**主语料。另有 [Cosmos-Drive-Dreams](https://arxiv.org/abs/2506.09042) 用世界模型本身**生成**合成驾驶数据(而非游戏引擎渲染)。

**(D)引擎来源「模糊/未命名」:**
- **Tencent GameGen-X**([arXiv:2411.00769](https://arxiv.org/abs/2411.00769)):OGameData ~100 万片段/150+ 商业游戏,YouTube + 本地 Steam 录制 +「游戏引擎直出」,**无专门 UE 管线**。
- **Tencent Hunyuan-GameCraft**([arXiv:2506.17201](https://arxiv.org/abs/2506.17201)):100+ AAA 游戏 100 万+ 录像(1080p)+ 微调用 ~3,000 条从精选 3D 资产渲染的运动序列,**渲染引擎未命名**(可能是 UE / Blender / 自研)。
- **UniSim/UniPi**([arXiv:2310.06114](https://arxiv.org/abs/2310.06114)):混合真实数据 + Habitat(HM3D)模拟器数据,**非 UE**。

**结论**:在整个领域里,**真正搭了 UE 合成数据管线的明确案例就是 Matrix-Game 2.0/3.0**。这也意味着你要走的路线是少数派、但有可复制的开源参考。

---

## 3. 训练交互式世界模型到底需要什么数据

### 3.1 数据的本质形态

不是「单帧配对」,而是**带滑动窗口的序列**:模型以**过去若干帧 + 过去若干动作**为条件预测下一帧。
- GameNGen:条件 = 自己预测的**过去 64 帧 + 过去 64 个动作**(~3 秒历史),帧 320×240 补到 320×256,4 步 DDIM,>20fps;训练时加噪增强(最大噪声 0.7、10 个 bucket)以稳定自回归。
- Genie:16 帧序列,160×90,10fps。

### 3.2 动作空间 = 人类游戏手柄

- **离散键(逐帧二值/one-hot 向量)**:WASD 移动、跳跃、攻击/使用、物品栏/快捷栏等。
- **连续鼠标/视角**:相机 pitch/yaw,记为标量(deltas),与帧同步。

最具可复用性的参考是 **open-oasis 的 `ACTION_KEYS`(已逐字节核实为 25 个,源自 VPT)**:`inventory, ESC, hotbar.1–9, forward, back, left, right, cameraX, cameraY, jump, sneak, sprint, swapHands, attack, use, pickItem, drop`。其中 23 个二值键约束在 [0,1];`cameraX/cameraY` 是连续轴,用 `max_val=20, bin_size=0.5, num_buckets=40` 分桶归一化到 [-1,1]。推理时把帧 resize 到 (360,640)=360p。这套编码可以直接拿来当你动作 JSON 的 schema。来源:[utils.py](https://raw.githubusercontent.com/etched-ai/open-oasis/master/utils.py)。

Matrix-Game 动作空间:离散 forward/back/left/right/jump/attack + 连续鼠标 pitch/yaw 标量,16Hz 同步。

### 3.3 分辨率、帧率、规模(都偏小、偏低)

| 模型 | 分辨率 | 帧率 | 规模 |
|---|---|---|---|
| Genie 1 | 160×90 | 10fps | 30k 过滤小时 / 680 万视频(无标注预训练路线) |
| GameNGen | 320×240 | >20fps | ~9 亿代理帧 |
| Oasis | 360p | ~20fps | 「数百万小时」(媒体说法,非仓库) |
| Matrix-Game 1.0 | 720p | 16Hz | ~2,700h 无标注 + ~1,200h 有标注 |
| Matrix-Game 2.0 | 352×640 | 25fps | 核心 ~800h + 微调 1134h |

注意:这些 fps 多是**生成/播放帧率**,不一定等于原始采集帧率。

### 3.4 如何拿到带动作标签的轨迹(四种方法)

1. **真人对局日志**:VPT 承包商录制成对的 `.mp4 + .jsonl`(逐 tick 动作)。
2. **RL/脚本代理日志**:代理的输入被直接记录——GameNGen 的 PPO@VizDoom、Matrix-Game 在 MineRL 的课程化 VPT 代理、**Matrix-Game 在 UE 里的 PPO 代理**。这是 UE 路线的核心。
3. **逆动力学标注(IDM)**:VPT 在小标注集上训 IDM,再自动标注 ~70k 小时无标注网络视频(非因果,用过去+未来帧)。
4. **完全无监督潜动作**:Genie 的 VQ-VAE 学 8 个离散潜动作码,**无需任何动作标签**——如果你拿不到真值动作,这是退路。

### 3.5 输出格式约定

- 逐帧 mp4/png + 动作 JSON/JSONL,**帧-动作精确对齐**(Matrix-Game 2.0:MP4 + JSON,基于速度过滤剔除静止帧,>99% 准确,120 万片段)。
- **WebDataset**:POSIX tar 分片(100MB–1GB,`shard-{000000..001000}.tar`),一个样本 = 共享 key 前缀的多文件(`000042.jpg / 000042.json / 000042.actions.npy`)——适合 PyTorch 高吞吐流式读取。[文档](https://huggingface.co/docs/hub/en/datasets-webdataset)。
- **RLDS / TFRecord**(Open X-Embodiment 用):episode-of-steps,每步 `{observation, action, reward, discount, is_first/is_last}`——动作标注序列数据的事实标准。[RLDS](https://research.google/blog/rlds-an-ecosystem-to-generate-share-and-use-datasets-in-reinforcement-learning/)。

### 3.6 确定性与可复现

用**固定时间步**(与墙钟解耦)+ RNG 种子,使「同种子 + 同动作序列」复现同一轨迹;MRQ 可逐帧确定性重渲染。多样性靠工程化:Matrix-Game 平衡 14 个 biome(每个 ~4–7%)、2.0 随机化车辆/NPC 密度并注入受控随机性。(不确定:世界模型论文本身很少写种子协议,这些可复现做法主要来自 UE-RL 工具链如 Falcon-Gym/Schola。)

---

## 4. UE 为什么/什么时候值得用,以及现成高保真场景资源

### 4.1 什么时候 UE 值得用 / 不值得用

**值得用 UE 的理由:**
- 你能拿到**完美的逐帧真值**:不仅是 RGB,还有离散动作、连续相机向量、深度、语义分割、光流、位置/速度/朝向、交互结果——这是真人/网络视频拿不到的。
- **可控 + 可脚本化 + 可程序化无限生成**:域随机化(天气/时间/密度)、确定性重渲染、相机轨迹精确控制。
- **照片级渲染**(Lumen 全局光照、Nanite 虚拟几何、Virtual Texture),接近 Matrix-Game 3.0 追求的开放世界质量。

**不值得/要谨慎的场景:**
- 你只需要 Minecraft/2D 这类风格——直接用 MineDojo API、VPT、open-oasis 更省事。
- 你有 EULA 顾虑(见第 9 节):UE 生成式 AI 条款对「合成数据训练」有解释模糊性。
- 你的目标域更接近物理 AI/机器人——**NVIDIA Omniverse/Isaac Sim 是更对口的替代路线**(见第 6 节)。

### 4.2 现成高保真场景资源(不用从零建场景)

- **City Sample**(《The Matrix Awakens》同款城市):Epic 免费发布的大型程序化城市样板工程,含大量建筑、车辆、人群,**开箱即用的大规模城市场景**,非常适合做导航/驾驶类轨迹。
- **Quixel Megascans**:海量照片扫描材质/植被/道具资产库,**已并入 Fab**,对 UE 用户基本免费。
- **Fab**(Epic 的统一资产市场,取代旧 Marketplace + Quixel Bridge + Sketchfab Store):成品场景、角色、道具,注意每个资产的授权条款。
- **Cesium for Unreal**:把真实地理空间/3D Tiles(全球地形、城市三维)流式加载进 UE,适合做真实城市级别的大场景。
- **PCG(Procedural Content Generation)框架**:UE 5.2+ 内置的程序化生成系统,用图(graph)规则批量铺设建筑、植被、道路;结合 Shape Grammar 可做确定性随机种子的程序化城市/建筑——**这是「无限场景」最关键的能力,直接对应 Matrix-Game 的程序化思路**。

> 工程建议:不熟 UE 的团队**先用 City Sample + Megascans 起步**,把农场管线跑通,再逐步引入 PCG 做程序化扩展。

---

## 5. UE 在 Linux 服务器上的无头渲染方案(可直接照抄的命令)

### 5.1 核心结论

UE5 在 Linux 上**无需显示器、无需 X server** 即可 GPU 加速无头渲染,核心是 **Vulkan RHI + `-RenderOffscreen`**(离屏 Vulkan 需 UE 4.25+;OpenGL 在无 X11 时会自动离屏)。来源:[unrealcontainers cloud-rendering](https://unrealcontainers.com/docs/use-cases/cloud-rendering)。

关键 flag 语义:
- `-RenderOffscreen`:抑制桌面窗口,**Vulkan 无 X server 时必须显式传**(不会自动开)。
- `-game`:跑未烘焙内容、无编辑器 UI。
- `-nullrhi`:**完全不渲染**(空 RHI),只用于烘焙/commandlet/数据处理/协调进程——**不能产出渲染帧**。
- `-Unattended`:无交互、抑制对话框。
- `-StdOut -allowStdOutLogVerbosity`:把详细日志打到 stdout 供渲染农场消费。

### 5.2 Movie Render Queue(MRQ)命令行——批量渲染主路径

Linux 二进制位于 `Engine/Binaries/Linux/UnrealEditor-Cmd`。标准调用(渲染输出路径来自保存的 Queue 资产,不是命令行):

```bash
UnrealEditor-Cmd MyProject.uproject Minimal_Default1 -game \
  -MoviePipelineConfig="/Game/Cinematics/myRenderQueue" \
  -RenderOffscreen -Log -StdOut -allowStdOutLogVerbosity -Unattended
```

加分辨率/其它:`-windowed -ResX=1280 -ResY=720 -NoLoadingScreen -notexturestreaming`(注意 `-ResX/-ResY` 是窗口大小,不是输出分辨率;输出分辨率在 Queue 资产里设)。来源:[offworld.live](https://knowledge.offworld.live/en/detailed-feature-guides/how-to-render-from-the-command-line-using-unreal-engine-movie-render-queue)、[Epic 教程](https://dev.epicgames.com/community/learning/tutorials/nZ2e/command-line-rendering-with-unreal-engine-movie-render-queue)。

**用 Python 自定义执行器做种子/场景模板化**(农场最有用的 hook):

```bash
UnrealEditor-Cmd Project.uproject MapName -game \
  -MoviePipelineLocalExecutorClass=/Script/MovieRenderPipelineCore.MoviePipelinePythonHostExecutor \
  -ExecutorPythonClass=/Engine/PythonTypes.MoviePipelineExampleRuntimeExecutor \
  -LevelSequence="/Game/Seq_1.Seq_1" \
  -windowed -StdOut -allowStdOutLogVerbosity -Unattended
```

注意点:**ObjectID(Cryptomatte)pass 需要完整编辑器,不能用 `-game`**——有些农场因此跑完整编辑器。Movie Render Graph(MRG)是 UE 5.4+ 实验性的图式新管线,通过相同的 MRQ 入口驱动。(不确定:MRG 在 5.5/5.6 是否能像经典 MRQ Queue 一样完全命令行驱动,需按你部署的 UE 版本实测。)来源:[Epic 论坛教程](https://forums.unrealengine.com/t/community-tutorial-command-line-rendering-with-unreal-engine-movie-render-queue/681764)、[MRP 文档](https://dev.epicgames.com/documentation/unreal-engine/movie-render-pipeline-in-unreal-engine)。

### 5.3 多卡选卡(重要校正)

`-graphicsadapter=N`(零基)在 Linux 下通过 Vulkan RHI 选卡,等价于在 `*Engine.ini` 设 `[/Script/Engine.RendererSettings] r.GraphicsAdapter=N`。**但**(经核实):
- 索引只在「单次启动内 N 一致指向 vkEnumeratePhysicalDevices 返回的第 N 个适配器」这种弱意义上确定;**具体是哪张物理卡由驱动决定,Vulkan 规范不保证顺序**,重启/BIOS 改动/PCI 重枚举可能改变。
- **不能假定 Vulkan 适配器索引 = CUDA/NVENC 序号**:CUDA 默认 `CUDA_DEVICE_ORDER=FASTEST_FIRST`(同构 8 卡机上并列卡的次序未定义),`nvidia-smi` 按 PCI 总线排序,只有显式设 `CUDA_DEVICE_ORDER=PCI_BUS_ID` 才对齐——且仍无契约把它与 Vulkan 顺序绑定。NVENC 绑定 CUDA context,跟 CUDA 序号走。
- `SDL_HINT_CUDA_DEVICE` 对无头 Vulkan **无效**。

**最可靠的 pinning(强烈推荐)**:让每个 UE 实例跑在**只暴露一张卡的容器**里,**按 UUID** 指定(`nvidia-smi -L` 查 UUID),然后容器内用 `-graphicsadapter=0`,再用宿主 `nvidia-smi` 确认物理落点:

```bash
docker run --rm --gpus '"device=GPU-xxxxxxxx-..."' \
  -e NVIDIA_DRIVER_CAPABILITIES=graphics,compute,utility,video \
  <ue-image> /path/UnrealEditor-Cmd ... -graphicsadapter=0 -RenderOffscreen -Unattended
```

来源:[r.GraphicsAdapter cvar wiki](https://indxzero.github.io/ue544cvarwiki/articles/r.graphicsadapter/)、[Epic 论坛](https://forums.unrealengine.com/t/explicitly-choosing-which-gpu-to-use/436698)、[CUDA env vars](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/environment-variables.html)、[Vulkan-Loader #153](https://github.com/KhronosGroup/Vulkan-Loader/issues/153)。

### 5.4 容器化(NVIDIA Container Toolkit)

GPU 透传是必需的,能力位要含 `graphics`(Vulkan/OpenGL)+ `compute`(CUDA)+ `video`(NVENC/NVDEC):

```bash
docker run --rm --gpus '"device=2,3"' \
  -e NVIDIA_DRIVER_CAPABILITIES=graphics,compute,utility,video <image>
```

镜像选择:
- **adamrehn/ue4-runtime**(社区):运行**已打包项目**,GPU 加速,tag 如 `20.04-vulkan`、`22.04-cudagl12`、`-x11`/`-noaudio` 变体。`docker run --gpus=all adamrehn/ue4-runtime:latest bash`。
- **adamrehn/ue4-docker**(社区):从源码**构建** Win+Linux 引擎/编辑器镜像(用于命令行 MRQ)。
- **Epic 官方** `ghcr.io/epicgames/unreal-engine`:tag 有 `dev`、`dev-slim`、`runtime`、`runtime-pixel-streaming`、`runtime-windows`。
- **evoverses/ue5-docker**:UE5 专用社区分支。

**获取门槛**:必须把 GitHub 账号关联到 Epic 账号并加入 EpicGames GitHub org(和克隆 UE 源码同一道门);Dockerfile 在 `Engine/Extras/Containers/Dockerfiles`。**EULA 限制**:含 Engine Tools 的镜像**只能私有分发**(不能推 Docker Hub 等公共仓库);仅含打包项目(无 Engine Tools/源码/未烘焙内容)的镜像可公开分发。来源:[ue4-runtime](https://github.com/adamrehn/ue4-runtime)、[官方镜像](https://unrealcontainers.com/docs/obtaining-images/official-images)、[EULA 限制](https://unrealcontainers.com/docs/obtaining-images/eula-restrictions)、[NVIDIA Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html)。

### 5.5 Pixel Streaming(交互式远程渲染,人在回路采集)

无头服务器上跑交互式 UE,需 NVENC:

```bash
# 启动打包应用
<App>.sh -PixelStreamingURL=ws://127.0.0.1:8888 -RenderOffScreen -AudioMixer
# 另起信令/Web 服务(SignallingWebServer/platform_scripts/bash,现已独立为 PixelStreamingInfrastructure 仓库)
```

需要 NVIDIA NVENC(或 AMD AMF);Epic 提供官方 `runtime-pixel-streaming` 镜像(在 cudagl 基础上加 NVENC),测过 Ubuntu 18.04/20.04。这是**人在回路 / 交互式世界模型数据采集**的路径。(不确定:flag 集随版本变化,旧版用 `-PixelStreamingIP/-PixelStreamingPort`,按部署版本核对。)来源:[Epic PS 文档](https://dev.epicgames.com/documentation/en-us/unreal-engine/getting-started-with-pixel-streaming-in-unreal-engine)、[tensorworks](https://tensorworks.com.au/blog/pixel-streaming-for-linux-425/)。

---

## 6. 现成合成数据工具与真值导出

不要从零写采集层。下表把可用工具按「是否 UE」「能给什么真值」「Linux/许可」「农场相关性」摊开。真值模态指 RGB、深度、语义/实例分割、表面法线、光流、6DoF 物体位姿、相机轨迹。

### 6.1 工具对照表

| 工具 | 是什么 | 提供的真值 | Linux | 许可 | 农场相关性 | 链接 |
|---|---|---|---|---|---|---|
| **UnrealCV** | UE4/5 插件,TCP 命令协议(`vget/vset/vbp`)控制相机/物体并抓图 | RGB、深度、表面法线、物体/实例 mask;新版加了光流(`/camera/[id]/optical_flow`) | 是(研究项目用预编译 Linux 包);无头多卡是弱项 | MIT | 任意 UE 场景的「提线木偶」:脚本化相机轨迹 + 读全模态;自带场景时最好用 | github.com/unrealcv/unrealcv |
| **UnrealZoo**(原作者出的「加强版」) | **注意:不存在叫 "UnrealCV-plus" 的项目**;原作者的现代扩展是 UnrealZoo——100+ 照片级 UE 环境 + UnrealCV 工具链 + Gym/Python 接口 | 同 UnrealCV(RGB/深度/分割/法线/光流)+ 智能体控制、多智能体 | 是(为 RL 数据采集设计) | 开放(研究,查仓库) | 最接近「开箱即用」的 UnrealCV:现成环境 + 轨迹/智能体控制 | arxiv.org/abs/2412.20977 |
| **EasySynth** | 无代码 UE 插件:渲一段相机序列自动输出多 pass | RGB、深度、法线、光流、语义分割(按物体指定颜色) | **Windows 优先,Linux 未文档化/未测** | MIT | 最快「拍一段带真值的视频」,但面向交互式/Windows 创作,非批量无头农场 | github.com/ydrive/EasySynth |
| **CARLA** | 成熟的 UE 自动驾驶模拟器,完整 Python/C++ API、交通、天气 | RGB、深度、**语义 + 实例分割**(实例自 0.9.14)、**光流相机**(自 0.9.13)、法线、LiDAR/语义 LiDAR、雷达、IMU/GNSS、2D/3D 框 | 是,**一等公民 `-RenderOffscreen`**,为远程服务器设计 | MIT | **最可生产的无头 UE 管线**,Python 传感器回调直写盘;无头 ~24–25 fps。局限:世界偏驾驶/城市 | carla.readthedocs.io/en/latest/ref_sensors/ |
| **Microsoft AirSim** | 无人机/车辆 UE 插件,**2022.7 已停更归档** | RGB、深度、视差、法线、分割(逐 mesh ID 0–255)、位姿 | 是(Docker 无头),但无人维护 | MIT | 历史意义(TartanAir 的底座),新项目改用 Colosseum | github.com/microsoft/AirSim |
| **Colosseum**(AirSim 继任) | 社区维护的 AirSim 分支,UE5.6(也有 UE4.27 分支),PX4/ArduPilot SITL/HITL | 同 AirSim:RGB、深度、视差、法线、分割、位姿 | 是,Ubuntu 20.04/22.04/24.04;**无头 Docker**(`Dockerfile_mesa` 无 GPU / `Dockerfile_nvidia` GPU) | MIT | 维护中的机器人/无人机路线,最贴近 TartanAir 管线 | github.com/CodexLabsLLC/Colosseum |
| **TartanAir / TartanGround** | 用 UE4+AirSim 建的参考**数据集 + 全自动管线**(非工具) | 立体 RGB、深度、语义分割、光流、视差、6DoF 相机轨迹、模拟多线 LiDAR、IMU;TartanGround 加 360° 多相机 + 语义占据图 | 管线跑在 UE+AirSim 上;数据集可下载 | 研究免费 | **你这农场的现成图纸**:占据图 → 采样相机轨迹 → UE 捕获 → 离线后处理标签。TartanGround ~15TB、1.44M 样本、17.3M RGB(6 立体相机→每样本 12 张)、640×640 | tartanair.org/tartanground.html |
| **NVIDIA Isaac Sim + Omniverse Replicator** | **不是 UE**——USD/PhysX/RTX 平台;Replicator 是其合成数据生成框架 | RGB、深度、语义 + 实例分割、2D/3D 框、法线、运动矢量(光流)、6DoF 位姿、遮挡、点云——用 annotator + writer | 是,**官方支持无头 Linux 容器**;**多卡**(`/renderer/multiGPU/enabled`) | 核心 **Apache 2.0**;容器走 NVIDIA EULA;**需 RTX 卡**(A100/H100 不支持渲染) | **内置域随机化 + 全真值 + 无头多卡** 最强;若接受 N 卡锁定,这是搭标注数据农场摩擦最小的路 | github.com/isaac-sim/IsaacSim |
| **Unreal PCG** | UE5 内置程序化内容生成(节点图,编辑器 + 运行时) | 不直接给真值——是造场景的工具 | 是(UE5 一部分) | 免费(UE EULA) | 生成程序化场景/轨迹多样性 → 世界模型需要的多样性 | dev.epicgames.com/.../procedural-content-generation-framework |
| **Cesium for Unreal** | 把 3D Tiles(含 Google 照片级 3D Tiles、地形)流式进 UE,全球地理配准 | 不直接给真值——提供大世界内容,配 UE/UnrealCV pass 出标签 | 是(UE 插件) | 插件 **Apache 2.0/免费**;Cesium ion + Google 照片级 Tiles 需账号/API key(有免费档 + 付费) | 行星级真实地理场景做户外/航拍轨迹,无需建美术 | github.com/CesiumGS/cesium-unreal |
| **Megascans / City Sample / Fab** | 现成高保真资产/场景。City Sample = 《The Matrix Awakens》背后的免费工程(整城 + 人群 + 车);Megascans = 扫描 PBR 资产;Fab = Epic 资产市场 | 不直接给真值——高质量内容供拍摄 | 是(UE5 资产) | 免费 / UE EULA(City Sample 免费;很多 Megascans/Fab 资产免费) | 让非美术立刻拿到照片级场景,City Sample 最适合城市世界模型 | fab.com(City Sample)/ quixel.com/megascans |
| **Movie Render Queue 渲染 pass / AOV** | UE 原生高质量渲染;装「MRQ Additional Render Passes」插件可出多层 EXR | 物体 ID(Cryptomatte)、世界深度、运动矢量(光流),以及 Final/Detail-Lighting/Unlit/Reflections 变体 | 是(UE 命令行 + `-RenderOffscreen` 无头) | 免费(UE EULA) | **不用第三方插件**就能拿深度/法线/物体 ID/运动。注意:给的是 Cryptomatte 物体 ID,不是干净的逐类语义 mask——后者需自定义 stencil/后处理 | dev.epicgames.com/.../cinematic-render-passes |

> **重要纠错**:网上常被提到的 **"UnrealCV-plus" 并不是一个真实项目名**。原作者的现代扩展是 **UnrealZoo**([arXiv:2412.20977](https://arxiv.org/abs/2412.20977));另有一个**不同**的工具叫 **UnrealROX+**([arXiv:2104.11776](https://arxiv.org/abs/2104.11776))。引用时别张冠李戴。

### 6.2 UE 编辑器自动化(场景搭建/编排,非实时输入注入)

- **Editor Python + remote_execution.py**:内嵌 `unreal` 模块 + UDP 多播 `239.0.0.1:6766`(PING/PONG 发现,TCP 下命令)做无人值守自动化、场景装配。
- **Remote Control API**:UE 内置 web 服务(REST/HTTP,社区常引默认端口 `:30010` + WebSocket),可调任意 Blueprint/Python 暴露的函数;打包构建默认关闭(`-RCWebControlEnable -RCWebInterfaceEnable`)。(不确定:`:30010` 与 `6766` 来自社区,按你的 UE 版本设置核对。)
- **取舍**:UnrealCV / Remote Control / Editor Python **适合场景装配、场景随机化、批量作业编排**,**不适合实时逐帧动作捕获**。实时轨迹用「**在引擎内的 AI 代理 + Enhanced Input 逐帧捕获 + 无头并行**」(Matrix-Game 2.0 的做法),高质量重渲染用 MRQ。

### 6.3 UE vs. NVIDIA Omniverse/Isaac Sim:给新手的选型(强烈建议先评估)

**一句话**:如果你的服务器是 NVIDIA RTX 卡(世界模型训练农场基本都是),且没有「必须用某个特定 UE 资产/世界」的硬需求,**对"批量生产带标注数据"这件事,Isaac Sim + Replicator 往往是更省事、更稳的路**——因为最难的部分(无头 Linux、多卡、域随机化、全套真值 annotator)都是开箱即用、可 Python 脚本化的。UE 能产出同样的模态、甚至更顶的照片级画质(Lumen/Nanite/City Sample/Megascans),但在无头多卡 Linux 上你通常得**采用一个已经解决了无头渲染的项目**(CARLA 的 `-RenderOffscreen`,或 AirSim/Colosseum 的 Docker);在远程多卡机上裸起 UnrealCV/MRQ 是最耗新手时间的环节。

| 维度 | UE 路线 | Omniverse/Isaac Sim 路线 |
|---|---|---|
| 开箱真值 | 分工具;最干净走 CARLA/Colosseum;MRQ 原生给深度/法线/物体ID/运动但非干净类别 mask | 内置 annotator 覆盖**全部**所需模态含 6DoF 位姿 |
| 域随机化 | 手动 / 靠 PCG / 逐项脚本 | **一等的 Replicator API**(资产/材质/光照/相机) |
| 无头 Linux | CARLA、AirSim/Colosseum 已解决;裸 UE/UnrealCV 脆 | **官方支持的容器**,为远程/云设计 |
| 多卡 | 各项目自理,非开箱 | 设置位即可开 |
| 免费照片级内容 | **极强**(City Sample/Megascans/Cesium/Fab) | 资产生态较小;可吃 USD/照片级 3D Tiles |
| 硬件 | GPU 厂商更灵活 | **必须 NVIDIA RTX**(A100/H100 不支持渲染) |
| 许可 | UE EULA(免费;生成式 AI 条款有模糊性,见第 9 节) | 核心 **Apache 2.0**;容器走 NVIDIA EULA |
| 新手摩擦 | 较高(引擎学习曲线 + 无头部署) | **就数据生成而言更低** |
| 何时选它 | 需要特定 UE 世界 / 极致照片级城市 / 已有 UE 资产 | 想快速搭一个可脚本化、随机化的标注数据农场 |

### 6.4 具体起步建议(先上 1–2 个工具)

- **首选(若可接受 N 卡锁定):NVIDIA Isaac Sim + Omniverse Replicator。** 它把你要的全部模态(RGB/深度/语义+实例分割/法线/运动矢量(光流)/2D-3D 框/6DoF 位姿/相机轨迹)通过文档化 annotator 给齐,外加**内置域随机化**——正好是世界模型训练集需要的多样性;且是这些选项里**唯一**有官方支持的无头 Linux 容器 + 多卡;Apache-2.0 核心降低法务风险。代价是 N 卡锁定(你本来就有)。
- **若坚持走 UE 路线:从 CARLA 起步。** 最成熟的无头 Linux UE 管线(`-RenderOffscreen`)+ 干净 Python API + 完整传感器(RGB/深度/语义+**实例**分割/**光流相机**/LiDAR/IMU/框),传感器回调直写盘。代价:世界偏驾驶/城市。要任意场景就 UE + **UnrealCV/UnrealZoo** + 现成内容(City Sample/Megascans/Cesium)+ **PCG** 做场景随机化。
- **无论走哪条引擎,都把 TartanAir/TartanGround 当蓝图研究**(UE + AirSim → 自动轨迹采集 → 离线后处理标签),它基本就是你要搭的农场的公开配方。
- **务实组合**:先用 Isaac Sim/Replicator 把标注数据生成跑顺(快、稳、全标注);若之后确实需要某个 UE 专属照片级世界(如 City Sample 那座城),再加一个仿 TartanAir 的 CARLA/Colosseum UE 采集阶段。

> 备注:NVIDIA SDG/Replicator 参考 [developer.nvidia.com/blog/generating-synthetic-datasets-isaac-sim-data-replicator](https://developer.nvidia.com/blog/generating-synthetic-datasets-isaac-sim-data-replicator/)(一个 demo 即生成 >9 万张标注图);若走该路线,编排用 NVIDIA Omniverse Farm。

---

## 7. 数据农场架构与多 GPU 吞吐方案

### 7.1 核心架构原则:多进程 > mGPU

**不要用 Epic 的 NVLink mGPU(把一次渲染拆到多卡,需 NVLink、最多 2 卡)。** 对 8 卡机,正确模式是 **N 个独立无头 UE 进程,每个钉到一张卡**。Epic 自己的说法:「Multi-GPU 用最大 GPU 拓扑,Multi-Process 要求最小 GPU 拓扑。」在数据农场场景 mGPU 反而**降低**吞吐。来源:[Epic mGPU→Multi-Process](https://dev.epicgames.com/documentation/en-us/unreal-engine/converting-from-mgpu-to-multi-process-rendering-in-unreal-engine)。

### 7.2 CARLA 式 fan-out 蓝图(可直接移植到 8 卡节点)

```bash
# 主进程:只跑物理/同步,不渲染
./CarlaUE4.sh -nullrhi -carla-primary-port=2002
# 每张卡一个渲染从进程,绑定 GPU 并连主进程
./CarlaUE4.sh -RenderOffScreen \
  -ini:[/Script/Engine.RendererSettings]:r.GraphicsAdapter=0 \
  -carla-primary-host=<primary_ip> -carla-primary-port=2002
```

主进程把传感器分发给从进程;客户端透明收数据。来源:[CARLA 多卡](https://carla.readthedocs.io/en/latest/adv_multigpu/)。

无头采集进程的常用 flag 组合:`-RenderOffScreen -unattended -nosplash -nosound -windowed -ResX=<W> -ResY=<H> -vulkan -graphicsadapter=N`(或容器内 `=0` + 单卡隔离)。

### 7.3 每卡几个实例 + 资源占用(估算)

**估算(无官方数字,Epic 仅给「8GB 或更多」笼统建议,必须实测):**
- 48GB 的 L40S/A6000 上,大致可装 **2–6 个无头 UE5 实例**:重场景(Lumen + Nanite + Virtual Texture)偏 **2–3 个**;轻场景/低设置偏 **6–8 个**。
- 每实例 VRAM 约 **4–10GB**(社区报告:较简单实例 ~1–4GB,有报 ~3.6GB/exe、4 个 exe 跑满 16GB 卡)。
- 每实例约 **4–8 CPU 核**(game + render + RHI + task 线程)+ **8–16GB 系统内存**。
- 典型 8 卡节点(~64–128 核 / 512GB–1TB 内存)上,**常常是 CPU 核数和 PNG/EXR 压缩先到顶,而不是 VRAM**。

务必用 `stat unit`、`stat gpu`、`nvidia-smi` 按场景实测。来源:[Epic 硬件规格](https://dev.epicgames.com/documentation/en-us/unreal-engine/hardware-and-software-specifications-for-unreal-engine)、[Azure Pixel Streaming at Scale](https://learn.microsoft.com/en-us/gaming/azure/reference-architectures/unreal-pixel-streaming-at-scale)。

### 7.4 两种吞吐模式:实时 vs 离线

| | 实时/游戏模式采集 | 离线 MRQ「终帧」渲染 |
|---|---|---|
| 速度 | ~24–60 fps/进程(CARLA 实测 ~24–25 fps;路径追踪 1080p ~30fps@RTX3060) | 秒级到分钟级/帧 |
| 用途 | **农场默认**,大批量 | 仅高保真子集 |
| Deadline 任务粒度 | — | 整个 shot 算一个 task |

**农场应默认实时游戏模式采集,MRQ 只留给需要终帧质量、可接受秒/帧的子集。** 来源:[Path Tracer](https://dev.epicgames.com/documentation/en-us/unreal-engine/path-tracer-in-unreal-engine)、[Deadline](https://aws.amazon.com/blogs/media/scheduling-epic-games-unreal-engine-pipelines-with-aws-thinkbox-deadline/)。

### 7.5 真正的瓶颈 + 存储估算

瓶颈通常**不是光栅化**,而是 **GPU→CPU 帧缓冲回读 + CPU 端无损压缩(PNG/EXR)+ 多模态真值落盘**。所以 CPU 核、内存、NVMe/存储带宽与 GPU 是同级约束。

**存储锚点(真实):** TartanGround ~15TB / 17.3M RGB 图像 → 约 **0.87 MB/张 RGB**(640×640 无损 PNG),或 ~10.4 MB/多相机样本。它平均偏低的真正原因(已校正):**① 分辨率低(640×640);② 光流/视差/LiDAR 不是每相机都存(光流只存前相机)**——而**存下来的都是无损 PNG/.npz,不是 EXR、不是有损**。

**估算(自标,按 1080p 各模态会更大):** RGB PNG ~1–3MB、16-bit 深度 EXR ~2–8MB、分割 PNG ~0.1–0.5MB、光流 EXR ~4–16MB;一套 RGB+深度+分割+光流约 **10–30MB/帧** → 100 万帧 ≈ **10–30TB**。架构上:每节点配 **NVMe scratch** 吸收写入突发 + 一层 NAS/对象存储做冷数据,并把**持续写带宽(GB/s)当一等约束**来规划。来源:[TartanGround](https://arxiv.org/html/2505.10696v2)。

### 7.6 NVENC 的正确用法

UE 的 NVENC(Pixel Streaming、CUDA-Vulkan interop)适合**把 RGB 存成压缩视频**;但**深度/分割/光流真值必须无损(16-bit PNG/EXR),NVENC 通常不承载这部分**。专业卡(A6000/L40S)**无并发会话上限**(消费级 GeForce 约 8 路)。

**L40S vs A6000(本工作负载):**
- L40S(Ada,48GB,18176 CUDA,91.6 TFLOPS FP32,864 GB/s,**3×NVENC+3×NVDEC、支持 AV1**,~350W)。
- A6000(Ampere GA102,48GB,10752 CUDA,38.71 TFLOPS FP32,768 GB/s,**单 NVENC、不支持 AV1 编码**,~300W)。
- 实务:**L40S 每卡帧率约 2× 于 A6000,硬件编码吞吐高得多**——把 RGB-视频密集的作业排给 L40S 节点,无损 EXR 作业两种节点都行。来源:[L40S](https://www.nvidia.com/en-us/data-center/l40s/)、[runpod 对比](https://www.runpod.io/gpu-compare/l40s-vs-rtx-a6000)。(注:A6000 单 NVENC/无 AV1 为公认 GA102 规格,本轮未再核对一手数据表。)

### 7.7 编排(orchestration)

- **AWS Thinkbox Deadline(+ Epic MRQ 插件)**:官方 UE/MRQ 路径,shot 级粒度,pool/group、指定 GPU worker、重试;**前 10 个 worker 免费**。适合 MRQ 终帧作业。
- **Slurm GPU 作业数组**:`--gres=gpu`,`sbatch` 数组下标 →(env, trajectory, seed),失败 requeue。适合上千个实时采集作业。
- **Kubernetes Indexed Jobs** + GPU device plugin + `backoffLimit` 重试。**注意:NVIDIA Container Toolkit 只支持 Linux 宿主 + Linux 容器(无 Windows GPU 容器)。**
- **Ray actors**:Python 驱动的采集循环(CARLA/AirSim API)。
- **NVIDIA Omniverse Farm**:若走 Isaac/Replicator 路线。

工程纪律:**输出幂等、以 seed/trajectory 为 key**,使重试安全;**按轨迹做 checkpoint** 限制失败损失。来源:[Deadline](https://aws.amazon.com/blogs/media/scheduling-epic-games-unreal-engine-pipelines-with-aws-thinkbox-deadline/)、[unrealcontainers GPU](https://unrealcontainers.com/docs/concepts/gpu-acceleration)、[Isaac Replicator](https://developer.nvidia.com/blog/generating-synthetic-datasets-isaac-sim-data-replicator/)。

### 7.8 轨迹脚本化(怎么让代理「自己玩」)

可扩展配方(抄 Matrix-Game 2.0):**UE 内 AI 代理 + NavMesh 路径规划(<2ms)+ PPO(奖励 = α·避碰 + β·探索 + γ·多样性)+ Enhanced Input 逐帧捕获键鼠 + 四元数双精度相机**,无头并行运行并录制(MP4 + 同步 JSON 动作日志,速度过滤剔除静止帧)。需要高质量版本时,把记录的轨迹喂给 **MRQ 确定性重渲染**。

---

## 8. 给不熟 UE 的人的落地路线图(分阶段 MVP)

> 原则:**先用别人写好的采集层 + 现成场景跑通最小闭环,再逐步自建。** 不要一上来就自己写 UE 插件和场景。

### 阶段 0:环境与法务前置(1 周内)
- 关联 GitHub↔Epic 账号、加入 EpicGames org,拿到 UE Linux 源码访问 + 官方容器镜像访问(否则后面所有容器路线都走不了)。
- **就 EULA 生成式 AI 条款向 Epic 法务书面确认**「用 UE 渲染输出训练世界模型」是否允许(见第 9 节)。**这步不要省**;同时评估 Omniverse/Isaac 作为法务更干净的并行路线。
- 跑通 NVIDIA Container Toolkit:`docker run --gpus all ... nvidia-smi` 正常,能力位含 `graphics,compute,video`。

### 阶段 1:最小闭环(2–4 周)——用 CARLA,先不碰 UE 编辑器
- **工具**:CARLA(MIT,开箱即用,自带传感器 + Python API + 多卡蓝图)。
- **目标**:在 1–2 张卡上无头跑 CARLA,采集 (RGB 帧 + 逐帧动作[转向/油门/刹车或键鼠] + 深度/分割),输出 MP4 + 动作 JSONL,打包成 WebDataset 分片。
- **同时**:用 open-oasis 的 `ACTION_KEYS` 思路定义你自己的动作 schema;参考 GameNGen 确定上下文窗口(如 32–64 帧 + 动作)。
- **坑**:`-RenderOffScreen` 必须显式传;选卡用容器单卡隔离(别赌 `-graphicsadapter` 的物理映射);帧-动作对齐要做速度过滤剔静止帧。

### 阶段 2:现成 UE 场景 + 采集插件(1–2 月)
- **工具**:City Sample/Megascans 现成场景 + UnrealCV 或 EasySynth(静态/相机路径真值)+ Colosseum/AirSim(带 Python API 的代理式采集,TartanAir 同款)。
- **目标**:把「占据地图 → 采样相机轨迹 → 无头捕获 → 离线后处理标签」这套 TartanAir 式管线在你的 UE 场景上跑起来;先单卡,验证每帧多模态真值正确。
- **坑**:UnrealCV 逐命令 socket 往返做实时轨迹会慢——实时轨迹改用引擎内代理 + Enhanced Input;ObjectID/Cryptomatte 真值需完整编辑器,不能 `-game`。

### 阶段 3:程序化 + 农场化(2–4 月)
- **工具**:PCG + Cesium 做程序化/真实地理无限场景;NavMesh + PPO 代理自动探索(抄 Matrix-Game 2.0);Slurm/Ray 数组编排上千作业;每卡 2–6 实例(实测定);NVMe scratch + NAS 分层。
- **目标**:8 卡 × N 实例稳定产出,输出幂等、按 seed/trajectory 命名,可断点重试;RGB 走压缩视频(L40S NVENC),真值走无损 PNG/EXR。
- **坑**:CPU/压缩/IO 先于 GPU 到顶,要监控全链路;每卡实例数务必实测;存储按 10–30TB/百万帧规划。

### 阶段 4:高保真子集 + 人在回路(按需)
- MRQ 对关键子集做终帧重渲染(Deadline 编排);Pixel Streaming 做人在回路交互采集。

每阶段都先用现成开源件验证再自研——这是不熟 UE 团队把风险降到最低的关键。

---

## 9. 风险、许可与注意事项

### 9.1 UE EULA「生成式 AI」条款(单一最大风险,务必重视)

**正式条文位置与原文(已核实,2026-04-19 存档)**:在 UE EULA **第 6 节「Other Restrictions on Your Use of the Licensed Technology」→ 子节 (e)「General Restrictions」** 的禁止活动列表里:

> "You must ensure that your activities with the Licensed Technology do not: … result in using the Licensed Technology as a training input to any Generative AI Program or as prompt-based input where the Generative AI Program trains on input data."

**校正要点:**
- 流行引文「training input or prompt-based input into any Generative AI Program」是**变更日志(EULA update 20)的宽松转述**,**不是正式条文**;正式条文的 prompt 那一支有限定语「**where the Generative AI Program trains on input data**」。
- 「Generative AI Program」定义很宽:「人工智能、机器学习、深度学习、神经网络或类似技术,旨在自动化或辅助生成新的音频、视觉或文本内容」——**世界模型显然落入这个定义**。
- **「合成数据(synthetic data)」「世界模型(world model)」字样在 EULA 里都不出现**。条款字面针对的是「把 Licensed Technology(引擎代码/工具)本身当作训练输入或 prompt 输入」;**而「引擎渲染出来的合成数据输出算不算 Licensed Technology 被当训练输入」并未明确,社区解读分歧**(有人认为只禁「用引擎代码训 AI」,有人认为「任何引擎输出喂模型」都禁)。

**结论**:这是整个项目最大的开放法律风险,**必须直接找 Epic 法务书面澄清**,不要自行假定。来源:[live EULA](https://www.unrealengine.com/eula/unreal)(对自动抓取返回 403)、[存档原文](https://web.archive.org/web/20260419053339id_/https://www.unrealengine.com/eula/unreal)、[变更日志](https://www.unrealengine.com/eula-change-log/unreal)、[论坛讨论](https://forums.unrealengine.com/t/new-eula-ai-restriction/2068913)。

### 9.2 其它许可与分发限制

- UE 本身免费;游戏类产品超过终身总收入阈值后付 5% 版税;非游戏/线性内容及部分席位制许可另有条款(本轮未逐一核实最新数字)。
- **云/内部渲染农场:允许**(自用)。**分发限制针对公开发布含 Engine Tools 的镜像**:含 Engine Tools 的容器只能私有分发或经 Epic 的 GitHub fork/Marketplace,**不能推 Docker Hub 等公共仓库**;仅含打包项目的镜像可公开。
- 各类资产(Fab/Megascans/City Sample)有各自授权,商用/再分发前逐个核对。
- **替代路线的许可优势**:NVIDIA Omniverse/Isaac(个人免费,面向 SDG)没有 UE 那条生成式 AI 模糊条款;CARLA(MIT)、AirSim/Colosseum(MIT)、UnrealCV(MIT)工具本身宽松,但**它们运行时仍依赖 UE,UE EULA 仍适用**。

### 9.3 实时 vs 离线渲染权衡

- **实时游戏模式采集**:高吞吐(~24–60 fps/进程)、适合海量数据,但单帧质量低于终帧渲染;**农场默认**。
- **离线 MRQ 终帧**:质量高(时序/空间子采样累积)、确定性可复现,但秒级到分钟级/帧;**只用于高保真子集**。
- 多卡:**多进程(每卡一进程)** 远优于 mGPU;选卡靠**容器单卡隔离 + UUID**,不要赌索引映射。
- 瓶颈是回读+压缩+IO,不是光栅化——**CPU/内存/NVMe 与 GPU 同级规划**。

### 9.4 数据来源相关的可信度提示(供你引用时注意)

- Matrix-Game 3.0 数据规模(小时/帧)**从未公开**,只有定性的三支柱描述;技术报告仅为仓库内 PDF,**无 arXiv**。3.0 的动作空间粒度、28B-MoE 是否为单独发布的 checkpoint(已发布的实时权重是 5B)等细节**不确定**。
- Genie 2/3、Mirage、Lucid 的数据披露极少或仅为公司宣传,**可信度低**。
- Cosmos 4% 合成切片的引擎**未披露**;Hunyuan-GameCraft 的 ~3,000 条合成序列渲染引擎**未命名**。
- Oasis 的「数百万小时」来自媒体而非仓库,**视为近似**;但「训练于 VPT」是 Etched 官方说法(见第 1 节)。

---

### 附:最值得直接复用的三件事
1. **数据 schema**:抄 open-oasis 的 25 键 `ACTION_KEYS` + 连续相机分桶([utils.py](https://raw.githubusercontent.com/etched-ai/open-oasis/master/utils.py));打包用 WebDataset/RLDS。
2. **UE 采集管线**:抄 Matrix-Game 2.0(NavMesh + PPO + Enhanced Input + 无头并行 + MRQ 重渲染)与 TartanAir(占据图→轨迹采样→捕获→离线标签);MVP 先用 CARLA。
3. **农场架构**:抄 CARLA 多卡 fan-out + 容器单卡隔离(UUID)+ Slurm/Ray 数组 + NVMe/NAS 分层 + 幂等输出。