# datafactory — 世界模型数据农场 · 工程规范 (v1)

> 目标:批量生产**带逐帧动作标签的第一/第三人称视频**,用于训练交互式世界模型(对标 Skywork Matrix-Game 3.0)。优先 UE 高画质合成数据(UEBackend)。
> 读者:不熟 UE 的工程团队。原则:**能复用就不自建;骨架引擎无关;每步充分测试**。
> 依据:`docs/matrix-game-3-data-system.md`(M-G3 数据系统一手拆解)、`docs/implementation-guide.md`(实现技术调研)、`docs/worldmodel-ue-data-farm-research.md`(领域综述)。

---

## 1. 一句话架构

农场 = **引擎无关的骨架(`datafarm/`,纯 Python,H100 上即可全测)** + **可替换的采集后端(`backends/`)**。
每条数据的本质是 M-G3 的逐帧元组 `D_t = (RGB, 玩家位姿, 相机6DoF, 动作向量)`,在采集源里**同 tick 同步**产生,落地为 `视频 + 逐帧 sidecar`,经统一 QA/过滤后打包为数据集。

```
 资产源                骨架(datafarm/, 引擎无关)                        产物
 asset-library ──┐    ┌─ assets   场景/角色/动画目录(消费, 带质量门控)
 (外部, 只读)     ├──► ├─ backends 采集后端接口 ───────────────────────┐
                 │    │    ├ MockBackend   合成假数据(测试骨架)        │
 Fab/Quixel ─────┘    │    ├ UEBackend     UE5 无头 tick 采集 ★主线     ├─► episodes/
                      │    ├ VideoIngest   视频→位姿(stub, 只留接口)    │   (video + 逐帧
                      │    └ AAABackend    商业游戏录制(stub, 只留接口) │    sidecar)
                      ├─ action   位姿→WSAD 动作推断 + Plücker 编码      │
                      ├─ pose     6DoF 位姿类型 + 坐标系归一            │
                      ├─ writers  帧/视频/CSV/JSON/WebDataset 写出 ◄─────┘
                      ├─ qa       重复帧/轨迹/速度/质量过滤
                      ├─ manifest episode/dataset 清单(schema + 校验)
                      └─ orchestrator  作业编排/种子/GPU 绑定/重试/看护
```

## 2. 范围(已定)

- **主线 = `UEBackend`**:UE5.5.4 无头逐 tick 采集,FPV + TPV。
- `MockBackend`:无 UE 时端到端测骨架(CI 友好)。
- `VideoIngestBackend`、`AAABackend`:**只留接口 stub**,不实现(AAA 仅学术研究,后续再说)。
- 资产**消费** `asset-library`,不重建采集管线(那是 `blackmyth-collect` 的职责);但对其内容加自己的质量门控,不假设可用。

## 3. 关键决策与理由(自主拍板)

| 决策 | 选择 | 理由 |
|---|---|---|
| 引擎版本 | **UE 5.5.4(锁定)** | 本机已装且经核实;5.5 是 Linux/Vulkan 最后稳定版(5.6/5.7 有 VK_ERROR_DEVICE_LOST 回归 + Nanite/RT 显存泄漏) |
| 采集机制 | **自建 in-engine C++ 组件**(fork `TimmHess/UnrealImageCapture` 为骨架) | 唯一能匹配 M-G3「零时间对齐误差」;外部录制器(UnrealCV/MRQ/TakeRecorder)做不到 |
| GPU 回读 | `FRHIGPUTextureReadback` 非阻塞异步 | 阻塞式 `ReadPixels` 会把帧率拖到 3–5 FPS |
| 分割真值 | CustomDepth/CustomStencil(runtime) | headless 安全;MRQ Cryptomatte 是 editor-only,`-game`/cooked 下不工作 |
| 探索 agent | **先 EQS/BT + NavMesh(无 RL)**;RL 仅可选(AMD Schola) | Learning Agents 在 Linux 无头未被端到端验证;启发式 coverage 足够复刻"多样性" |
| 角色 | 统一 **UE5/UEFN Mannequin 骨架** + per-slot SkeletalMeshComponent + Set Leader Pose | 现成模块化包 + Game Animation Sample 直接用,全 runtime/headless 安全 |
| 视频编码 | **离线 ffmpeg NVENC**;训练真值保留 PNG/raw | NVENC 是独立 ASIC 不抢训练算力;但 "lossless" 不保证逐位一致 |
| 渲染硬件 | UE 渲染**只在 L40S/A6000**;**H100 不做 UE 渲染** | NVIDIA 明确 H100 图形为非标准用途;H100 留给 ML(视频→位姿) |
| 包管理 | `uv` + `pyproject.toml`;依赖极简(numpy/pillow/jsonschema) | Karpathy 式精简 |

## 4. 数据模型(`datafarm/schema.py`)

核心镜像 M-G3 的 `D_t`,字段对齐 `blackmyth` 的内容寻址/manifest 惯例。

- `Pose6DoF`: `position: (x,y,z)`、`rotation: 四元数 (w,x,y,z)`、`frame: CoordFrame`(坐标系约定枚举:`UE_LEFT_CM` / `SLAM_RIGHT_M` / …)。
- `Action`: 6 维离散 `{0,1}^6` = `forward,back,left,right,jump,attack`(对齐 M-G2/M-G3);相机 yaw/pitch 由 `camera_pose` 表达,不进离散向量。
- `Step`(= `D_t`): `index:int`、`t:float`、`rgb:FrameRef`、`player_pose:Pose6DoF`、`camera_pose:Pose6DoF`、`action:Action`、可选 `depth/segmentation:FrameRef`。
- `Episode`: `steps`、`meta: EpisodeMeta`。
- `EpisodeMeta`: `episode_id`、`scene_id`、`character_id`、`viewpoint: FPV|TPV`、`fps`、`resolution`、`seed`、`label_kind: PRECISE_ACTION|VIDEO_ONLY`、`source: ue|mock|video|aaa`、`coord_frame`、时间戳。
  - `viewpoint` 与 `label_kind` **从数据结构层分桶**(M-G3 FPV/TPV 分别训练;带精确动作 vs 仅视频分档训练)。

`FrameRef` = 帧的引用(磁盘相对路径或内存 ndarray),避免把大数组塞进元数据。

## 5. 资产数据结构(`datafarm/assets.py`,消费 `asset-library`)

分类**分开维护**(用户要求):`scene` / `character` / `animation`(+ `prop`/`material`)。
沿用 `blackmyth` 的三层 + 内容寻址惯例,但 datafactory 侧只读消费 + 自己的质量门控:

```
asset-library/                     # 外部, 只读 (blackmyth-collect 产出)
  manifests/<uid>.meta.json        # 每资产一份(category/has_skeleton/standard_rig/license/...)
  derived/<uid>/<uid>.glb
  library.db                       # SQLite 索引
```

`assets.py` 接口:
- `AssetCatalog(library_root)`:读 `library.db`/`manifests/`。
- `.scenes(filter) -> [SceneAsset]`、`.characters(filter) -> [CharacterAsset]`、`.animations(...)`。
- 过滤默认门控:`render_status=ok`、`license` 在 allowlist、character 需 `has_skeleton & standard_rig=ue5_manny`。
- **本地 datafactory 资产覆盖层**:`assets/catalog.toml` 登记我们自建/采购、不在 asset-library 里的资产(场景/角色),与 library 合并。

## 6. 后端接口(`datafarm/backends/base.py`)

```python
class CaptureBackend(ABC):
    def plan(self, job: JobSpec) -> list[EpisodePlan]: ...      # 把作业展开成 episode 计划(场景×角色×视角×种子)
    def capture(self, plan: EpisodePlan, out: Path) -> Episode: ...  # 产出一个 episode(帧+逐帧状态)落到 out
    def healthcheck(self) -> BackendStatus: ...                 # 依赖/GPU/引擎就绪自检
```

- `MockBackend`:确定性合成 RGB(随种子)+ 解析式相机轨迹 + 由轨迹反推动作 → 端到端可测,无外部依赖。
- `UEBackend`:`plan` 组合资产;`capture` = 渲染 manifest → 启动 `UnrealEditor`/cooked 包(`-RenderOffscreen -graphicsadapter=N`)→ 插件按固定时间步 tick 采集 → 收帧+sidecar → 回填 `Episode`。Python 侧(launch/collect/manifest)与渲染解耦,可在无 GPU 下用 fake-launcher 测。
- `VideoIngestBackend` / `AAABackend`:`raise NotImplementedError`,签名与 docstring 定义清楚,供后续填。

## 7. 目录布局

```
datafactory/
├── SPEC.md  README.md  pyproject.toml  .gitignore
├── docs/                 # 调研与设计文档
├── datafarm/             # 引擎无关骨架(纯 Python)
│   ├── schema.py action.py pose.py assets.py manifest.py writers.py qa.py orchestrator.py cli.py
│   └── backends/ base.py mock.py ue.py video.py aaa.py
├── ue/                   # UE 侧:TickCapture C++ 插件 + 最小项目(主线交付)
├── tests/                # pytest,覆盖每个骨架模块 + mock 后端 + 编排
├── scripts/              # 入库的辅助脚本(env 安装等)
└── scratch/              # 不入库(.gitignore):繁琐/本地实验脚本
```

## 8. 分阶段构建与测试计划

每阶段:实现 → 写 `tests/` → 跑通 → 提交。不追求一次到位。

- **P0 地基**:仓库骨架、pyproject、SPEC/README、git。✅
- **P1 核心纯逻辑**:`schema` + `pose`(坐标系归一)+ `action`(WSAD 反推 + Plücker)。**纯函数,优先做,全测。**
- **P2 IO**:`manifest`(schema+校验)、`writers`(帧/视频/CSV/JSON/WebDataset)、`qa`(重复帧/轨迹/速度/质量)。
- **P3 资产**:`assets`(读 library.db + 本地覆盖 + 门控)。
- **P4 后端+编排**:`backends/base` + `MockBackend` + `orchestrator`(种子/GPU 绑定/重试/看护)+ `cli`。**到此端到端可在 H100 跑通 mock 数据集并测。**
- **P5 UE 环境**:装 vulkan-loader;在 L40S/A6000 验证 `-RenderOffscreen + -graphicsadapter` 并做 soak test;cook 一个最小 Linux 包。
- **P6 UE 采集插件**:fork TimmHess → in-tick 同步采样组件(RGB+位姿+动作)→ 验证零对齐 + 异步回读无 stall。
- **P7 UE 内容+agent**:Mannequin 模块化角色 + 双相机 rig + Game Animation Sample;EQS/BT+NavMesh 探索 agent。
- **P8 UEBackend 接通 + 扇出**:Python UEBackend 串起来;supervisor 多实例;实测每卡密度/吞吐。
- **P9(并行/可选)**:VideoIngest 用 ViPE/DPVO(H100);RL(Schola)按需。

## 9. 测试策略

- 纯逻辑(pose/action/schema/manifest/qa):单元测试 + 数值/属性断言(往返一致、坐标系往返、动作反推已知轨迹)。
- writers:写后回读校验(帧数、CSV 行列、sidecar JSON schema)。
- MockBackend:确定性(同种子同输出)、与 schema/writers 端到端。
- UEBackend:Python 侧用 fake-launcher 单测;真实渲染走 farm 上的集成测试(标注 farm-only)。
- `pytest`,CI 只需 H100/CPU 即可跑 P1–P4 全量。

## 10. 风险登记(见 implementation-guide §b)

1. 回读 flush 回归(UE-71894 类)静默拖垮吞吐 → 5.5.4 上实测双/三缓冲。
2. offscreen Vulkan 崩溃 + 每卡密度版本敏感 → 锁 5.5.4 + soak test + 实测,别用 H100 渲染。
3. RL 工具链 Linux 未验证 → 坚持 Tier-1 启发式。
4. groom strand 头发 headless 未验证 → 默认 card 头发。
5. ViPE 默认深度/遮罩含非商用/AGPL → 配 `keyframe_depth=metric3d/dav3` + 关 tracker(仅 VideoIngest 阶段)。
6. asset-library 产出质量不稳 → datafactory 侧质量门控,不盲信。
