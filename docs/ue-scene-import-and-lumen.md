# UE5.5 无头:场景导入(.umap) + Lumen(SM6) 实现要点

> 由聚焦调研生成(源码+文档核实)。即使后续 base on UnrealZoo,SM6/Lumen 与场景导入知识仍适用。

# DataFactory 可构建实施计划（基于 findings + verdicts，已应用裁决修正）

## 0. 关键裁决修正（务必先读）

- **import_scene 在 5.5 是同步的**（裁决1）：旧的 5.0/5.1 异步崩溃是 bug，5.5 已拆分为同步 `import_scene` 与 `scripted_import_scene_async`。同步变体在调用内 flush 完成，**不需要** `on_scene_import_done`/C++ `WaitUntilDone`。但**不会自动持久化 actor** —— commandlet 不自动加载关卡、也不自动保存，必须显式 `new_level` + `save_current_level`。
- **FBX 场景组装并非不可能**（裁决2）：稳定 Import-Into-Level 路径支持 **glTF + MaterialX**（不是仅 glTF）；FBX 是实验性，靠 cvar `Interchange.FeatureFlags.Import.FBX=1` + `Interchange.FeatureFlags.Import.FBX.ToLevel=1` 开启（5.5 release notes 标为 beta）。仅在 cooked/无编辑器 runtime 下 FBX 才真正不可用。
- **`-vulkan -sm6` 在具体 A6000/L40S 上能否初始化无法从公开源证实**（裁决3）：需在节点实测。修正点：驱动下限是 **Linux 550+**（Epic 5.5 release notes），570+ 只是社区"稳"值；成功日志串**不是** "Vulkan (SM6)"，真实标识是 **`SF_VULKAN_SM6` / `VP_UE_Vulkan_SM6`** 及 RHI feature-level 行；失败串是 `Failed to load Vulkan Driver which is required to run the engine...`。
- **H100 上 SM6 可能失败的真实原因**（裁决4）：门不是 `IsSupported(SM6)`，而是 profile 校验 + `Vulkan device could not be created at the project's supported feature levels`（LinuxDynamicRHI.cpp ~185）。**RT 不是 SM6 初始化前置**；真正的卡点是 **bindless + `VK_EXT_mesh_shader` + `VK_KHR_compute_shader_derivatives`**，且这是 **5.5.4 新增**要求（5.5.3 不要求）。
- **headless `-RenderOffscreen` 并非"不支持"**（裁决5）：`-RenderOffscreen` + Vulkan 在 Linux 是官方支持（UE4.25+），多 GPU 用 `-graphicsadapter=N`。**未证实的只是** SM6+软件Lumen+Nanite+VSM 这一完整栈在 5.5.4 `-RenderOffscreen` 下出帧正确 + 多小时稳定 —— 需自测（5.5.x 相对 5.7.x 的 device-lost 回归更稳）。
- **positional map-URL 在 UnrealEditor-Cmd 上有效、无需 cook**（裁决6，CONFIRMED）。
- **NavMesh ini 段是 `[/Script/NavigationSystem.RecastNavMesh]`**（裁决7，CONFIRMED），不是 `/Script/Engine.RecastNavMesh`（那是 4.20 前）。`RuntimeGeneration` 定义在基类 `NavigationData` 但可在此段覆盖。
- **`CTF_UseComplexAsSimple` 确实喂给 navmesh**（裁决8，源码级 CONFIRMED，5.5.4）：`ExportRigidBodyTriMesh` 仅在该 flag 下导出复杂三角网；否则只有简单几何进 navmesh。另需 `UStaticMesh::bHasNavigationData=true`（默认开）。forum 417777 不是反例（那是 runtime 生成网格缺 per-asset flag）。

---

## 1. Headless Interchange 场景导入 GLB/FBX/USD -> 组装 .umap

编辑器命令行：`UnrealEditor-Cmd <proj.uproject> -run=pythonscript -script=compose.py -unattended`

构建步骤（基于 `make_test_map.py` / `import_glb.py` 扩展）：
1. `les = LevelEditorSubsystem`；`les.new_level(mapp)` —— commandlet 不自动加载关卡，必须先建世界。
2. `params.is_automated=True`；`params.import_level = 当前 Level`；`params.override_pipelines = [DefaultGLTFSceneAssetsPipeline, DefaultSceneLevelPipeline, DefaultGLTFPipeline]`。
3. `manager.import_scene(dest, create_source_data(src), params)` —— **同步返回 bool**，调用内完成。
4. 对每个导入的 `StaticMesh` 设 `body_setup.collision_trace_flag = unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE`（行走 + navmesh 需要），并确保 `bHasNavigationData=True`、碰撞非 NoCollision。
5. **显式持久化**：`save_directory` + `save_current_level`（commandlet 不自动保存）。
6. 格式：
   - **glTF/GLB**：默认稳定路径，直接组装。
   - **FBX**：先开 cvar `Interchange.FeatureFlags.Import.FBX=1` + `Interchange.FeatureFlags.Import.FBX.ToLevel=1`（实验性/beta，headless 编辑器可用）。
   - **USD**：编辑器 USD Stage import / `AUsdStageActor` 作为可选 layout interchange 喂给 compose 阶段；不要 runtime 导入。
7. 待验证（在 5.5.4 实测）：同步 `import_scene` 在 `-run=pythonscript` 下确实落盘 actor；FBX 栈是否真能 headless 组装。

URL：
- https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/InterchangeManager?application_version=5.5
- https://dev.epicgames.com/documentation/unreal-engine/importing-assets-using-interchange-in-unreal-engine
- https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-5-5-release-notes

---

## 2. 在 headless offscreen capture 中经 SM6 Vulkan 启用 Lumen

三道门，全部清掉才出 Lumen。

**门1 —— 强制 SM6（当前 SM5 是根因）**
- 启动：`UnrealEditor-Cmd <proj> <map> -game -RenderOffscreen -vulkan -sm6 -CaptureConfig=<manifest.json>`（`-sm6` 由 `LinuxDynamicRHI.cpp` 解析，文档亦记为 "Force use SM6"）。
- 等价/兜底（cooked 必须）：`Config/DefaultEngine.ini` 加 `[/Script/LinuxTargetPlatform.LinuxTargetSettings]` `+TargetedRHIs=SF_VULKAN_SM6`（cooked 时去掉 SF_VULKAN_SM5）。
- 驱动：A6000/L40S 上需 **≥550（文档下限），建议 ≥570** 以稳过 5.5.4 新增的 `VK_EXT_mesh_shader` + `VK_KHR_compute_shader_derivatives`。
- profile 校验误拦时：加 `-SkipVulkanProfileCheck` 或 `r.Vulkan.UseProfileCheck=0`。
- 首次会触发一次性 SM6 shader 编译（当前 ShaderAutogen 仅有 VULKAN_SM5）。

**门2 —— 工程级 Lumen 设置** `[/Script/Engine.RendererSettings]`
```
r.DynamicGlobalIlluminationMethod=1
r.ReflectionMethod=1
r.GenerateMeshDistanceFields=True        ; 软件 Lumen 必需，需重建/重 cook
```
仅 A6000/L40S 加硬件 RT：`r.RayTracing=True`、`r.Lumen.HardwareRayTracing=1`，且 capture 内还需 `r.RayTracing.SceneCaptures=1`（默认 -1 仅看组件标志）。

**门3（决定性）—— 改 `TickCaptureManager.cpp` BeginPlay**
路径：`/root/nas/bigdata1/cjw/projs/datafactory/ue/DataFarmCapture/Plugins/TickCapture/Source/TickCapture/Private/TickCaptureManager.cpp`
SceneCapture 默认把 view 的 GI/Reflection 强制为 None（SceneCaptureRendering.cpp 880-882），必须在组件 PostProcessSettings 里覆盖回来，并提供持久 view state：
```cpp
SceneCapture->bAlwaysPersistRenderingState = true;                 // 持久 FSceneViewState，Lumen 必需
SceneCapture->bUseRayTracingIfEnabled = true;                      // 仅 HW-RT 时生效
SceneCapture->PostProcessSettings.bOverride_DynamicGlobalIlluminationMethod = true;
SceneCapture->PostProcessSettings.DynamicGlobalIlluminationMethod = EDynamicGlobalIlluminationMethod::Lumen;
SceneCapture->PostProcessSettings.bOverride_ReflectionMethod = true;
SceneCapture->PostProcessSettings.ReflectionMethod = EReflectionMethod::Lumen;
SceneCapture->PostProcessSettings.bOverride_LumenSurfaceCacheResolution = true; // 可选，0.5->1.0
SceneCapture->PostProcessSettings.LumenSurfaceCacheResolution = 1.0f;
```
保留 `CaptureSource=SCS_FinalColorLDR`（Lumen GI 在 tonemap 前已合入 scene color）。`warmup_frames` 从 8 提到 **16–30**，每个 warmup tick 继续 `CaptureScene()` 让 Lumen 时域历史收敛。注意：5.5.4 中常规 2D SceneCapture **不**被 `IsLumenFeatureAllowedForView` 排除（仅排 planar/reflection capture），所以**无需改引擎源码**。

**场景灯光**：DirectionalLight + SkyLight + Unbound PostProcessVolume，匹配视口光照。

**如何验证 headless 下 Lumen 真的开了**
- SM6：grep 日志 **`SF_VULKAN_SM6` / `VP_UE_Vulkan_SM6` 及 RHI feature level SM6**（不是 "Vulkan (SM6)"），并确认**没有** `Failed to load Vulkan Driver...` 致命退出。
- cvar：`-ExecCmds="r.DynamicGlobalIlluminationMethod, r.ReflectionMethod, r.Lumen.DiffuseIndirect.Allow, r.Lumen.HardwareRayTracing"` 看是否为 1。
- GPU pass：`-ExecCmds="DumpGPU"`，确认 dump 里有 `LumenSceneLighting` / `LumenScreenProbeGather` / `DiffuseIndirectAndAO`。
- A/B：同轨迹 `r.DynamicGlobalIlluminationMethod=0` vs `=1` 比对间接光。

**A6000 / GPU caveats**
- **A6000（Ampere GA102，2 代 RT core）**：软件 + 硬件 RT Lumen 均可；驱动需 ≥570 稳过 mesh-shader/compute-derivatives；显存与每帧成本随多实例 fan-out 叠加，需实测每卡并发数。**L40S（Ada）最佳**。
- **H100/A100 无 RT core**，且 5.5.4 的 bindless/mesh-shader/compute-derivatives 可能令 `-sm6` 直接 hard-exit —— **不要用于 Lumen 光栅**，留给 compute/ingest。
- headless `-RenderOffscreen` 机制本身受支持；但 SM6+Lumen+Nanite+VSM 全栈 + 多小时 soak 在 5.5.4 上**未经公开源证实**，列为独立 soak 任务（监测 `VK_ERROR_DEVICE_LOST` / 显存爬升）。软件 Lumen（需对导入网格生成 Mesh Distance Fields）是更稳的第一目标。

URL：
- https://dev.epicgames.com/documentation/en-us/unreal-engine/lumen-global-illumination-and-reflections-in-unreal-engine
- https://dev.epicgames.com/documentation/unreal-engine/linux-development-requirements-for-unreal-engine
- https://forums.unrealengine.com/t/scene-capture-component-not-capturing-lumen-global-illumination/249871
- https://forums.unrealengine.com/t/unreal-engine-5-6-startup-vulkan-error-and-vk-ext-mesh-shader/2332700
- https://issues.unrealengine.com/issue/UE-356685
- https://dev.epicgames.com/documentation/unreal-engine/gpudump-viewer-tool-in-unreal-engine

---

## 3. 解耦 ingest / compose / capture 架构 + 真实场景源

三段以文件契约相连，全部内容寻址（在 `datafarm/assets.py` 加 `SceneCatalog`，与 `AssetCatalog` 平行）。

**A 摄取 INGESTION**（编辑器命令行，无需 GPU 渲染）
- `UnrealEditor-Cmd <proj> -run=pythonscript -script=ingest.py -unattended`，GLB/FBX -> uasset（`InterchangeManager.import_asset`）。
- 泛化现有 `ue/scripts/import_glb.py`：导入 -> 存到 `/Game/DF/Meshes/<uid>/` -> 写 manifest 行（uid -> /Game 路径、bounds、has_skeleton、license）。在此处同时做第 4 节的碰撞设置。
- 幂等、内容寻址；可跑在 H100 上（非渲染负载）。保持**编辑器时**摄取，不用 runtime glTF 导入。

**B 组装 COMPOSITION**（编辑器命令行 -> 一个 .umap）
- 输入 SceneSpec（JSON/TOML）：显式摆放 / PCG graph ref+seed+bounds / 引用现成关卡。
- 输出 `/Game/DF/Scenes/<scene_id>/<scene_id>.umap`，`scene_id = hash(SceneSpec)`。
- **在此烘焙 PCG**（`GenerationTrigger=GenerateOnLoad`，所有节点 seed 设 'From Component'，组件 Seed 来自 spec）-> 确定性 + cook 期 Nanite/LOD 优化。
- 灯光预设 + NavMesh bounds 也在此烘焙。**场景内零捕获代码**（只引用 `/Game/DF/Meshes` + Materials）。

**C 捕获 CAPTURE**（场景无关；TickCapture 插件）
- 插件**不得硬编码 map**：从 manifest 读 `map=/Game/DF/Scenes/<id>`。
- 加载方式二选一：启动 positional URL 参数（裁决6 CONFIRMED），或从极小 `BootCapture.umap` 调 `OpenLevel`。
- 绑定 `FCoreUObjectDelegates::PostLoadMapWithWorld`（或经 `?game=` 设 GameMode）在任意加载世界里生成 ExplorerCharacter + FPV/TPV 双相机 + `ATickCaptureManager`。
- 启动：`UnrealEditor-Cmd <proj> /Game/DF/Scenes/<id> -game -RenderOffscreen -vulkan -sm6 -graphicsadapter=N`。注意：positional map URL 必须紧跟 exe 或 mode flag、用正斜杠、`-game` 必带（否则只是"在该 map 打开编辑器"）；`-RenderOffscreen` 需 GPU（无 GPU 用 `-nullrhi`）。
- 编辑器-headless `OpenLevel` 可加载工程内**任意 .umap、无需 cook**（cooked 游戏只能加载 cook 列表内的 map）。

**哪些真实场景源是需要 Epic 授权的 .umap 关卡**
- **City Sample**（`Small_City_LVL`、`Big_City_LVL`，World Partition 流式）—— 是现成 .umap 关卡，需 Epic 账号 + Epic Games Launcher / Fab Library。
- **Fab 场景/环境包** —— 同样需 Epic 授权。
- **无原生 Linux Launcher，Linux Fab 插件长期损坏** -> 在 Windows/Mac 下载，rsync `Content/**.umap` + 依赖到农场；逐项清 EULA + UE 生成式 AI 条款。
- **Sketchfab GLB + Quixel Megascans 是散网格/材质，不是关卡** -> 必须走 B 阶段才能变 .umap。
- 注意：City Sample 跟随最新 UE，较新包可能拒绝在锁定的 5.5.4 打开；`Big_City` 下捕获 agent 的 PlayerController 即流式源，warmup 前用 `IsStreamingCompleted` 把关。
- 对标 CARLA（authored .umap + runtime spawn）、UnrealZoo（按名选 map）、TartanAir（离线轨迹回放）。

URL：
- https://dev.epicgames.com/documentation/en-us/unreal-engine/command-line-arguments-in-unreal-engine?application_version=5.5
- https://dev.epicgames.com/documentation/unreal-engine/city-sample-project-unreal-engine-demonstration
- https://forums.unrealengine.com/t/how-do-i-download-purchased-assets-without-the-fab-plugin-or-epic-games-launcher/2658224
- https://carla.readthedocs.io/en/latest/core_map/
- https://github.com/UnrealZoo/unrealzoo-gym/blob/v2.0/doc/addEnv.md

---

## 4. 真实已加载关卡上的 NavMesh

NavMesh 是 CPU/Recast，渲染器无关 —— 在 Vulkan SM5 / `-RenderOffscreen` / NullRHI 下行为一致（SM6 那条日志与导航无关）。需确认会话是**真正在 tick 的 -game 世界**，不是不 tick 的 commandlet。

1. **Build.cs**（`TickCapture.Build.cs`）：`PrivateDependencyModuleNames` 加 `"AIModule"`、`"NavigationSystem"`。
2. **DefaultEngine.ini**：
```
[/Script/NavigationSystem.NavigationSystemV1]
bAutoCreateNavigationData=true
bGenerateNavigationOnlyAroundNavigationInvokers=true

[/Script/NavigationSystem.RecastNavMesh]   ; 裁决7: 正确段名，非 /Script/Engine
RuntimeGeneration=Dynamic
```
（按 ExplorerCharacter 胶囊设 AgentRadius/AgentHeight/AgentMaxSlope/CellSize 与 SupportedAgents。）
3. **碰撞（在 A 摄取阶段做，裁决8 源码确认）**：每个导入 StaticMesh 设 `body_setup.collision_trace_flag = unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE`，否则只有简单几何进 navmesh、导入地板无碰撞 -> navmesh 为空、agent 不能动。确保 `bHasNavigationData=true`、碰撞已启用。
4. **Agent**：优先 Nav Invoker（构造里加 `UNavigationInvokerComponent` 或 BeginPlay 调 `RegisterNavigationInvoker(this, 3000.f, 5000.f)`），对任意大场景免算 bounds。自定义 `AAIController`：`GetRandomReachablePointInRadius` + `MoveToLocation(Out.Location, 120.f, ..., bProjectDestinationToNavigation=true)`，`OnMoveCompleted` 重选点（替换原 open-floor `AddMovementInput`）。小场景兜底可 runtime 生成/缩放 `ANavMeshBoundsVolume` + `OnNavigationBoundsUpdated` + `Build()`。
5. **时序**：navmesh 异步生成，BeginPlay 时**未就绪**，`Build()` 不阻塞 -> 绑 `OnNavigationGenerationFinished` 或每 tick 轮询 `GetRandomReachablePointInRadius` 直到成功再首次 MoveTo；**捕获录制门控在首条成功路径之后**，剔除空导航起始帧。
6. **生成点**：`TickCaptureManager.cpp` 硬编码 `(0,0,150)` 须用 `ProjectPointToNavigation` 或向下 trace 投到真实地板，避免悬空/嵌入网格。
7. 真实包若用 World Partition，可能需 World Partitioned Navigation Mesh 路径。

URL：
- https://dev.epicgames.com/documentation/en-us/unreal-engine/using-navigation-invokers-in-unreal-engine
- https://dev.epicgames.com/documentation/en-us/unreal-engine/setting-up-collisions-with-static-meshes-in-unreal-engine
- https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/NavigationSystem/UNavigationSystemV1
- https://forums.unrealengine.com/t/how-can-i-use-navmesh-data-in-server-side/318281/6

---

## 5. 排序的构建顺序（ranked build order）

1. **解耦 capture 阶段为场景无关**：去掉 map 硬编码，改 manifest `map=` + positional URL/OpenLevel + `PostLoadMapWithWorld` 生成器。（裁决6 已确认，无阻塞，是其余一切的地基。）
2. **A 摄取 commandlet + 碰撞**：泛化 `import_glb.py`，导入后即设 `CTF_USE_COMPLEX_AS_SIMPLE` 并存 `/Game/DF/Meshes/<uid>/` + manifest。（裁决8，喂 navmesh + 行走。）
3. **NavMesh 上线**：Build.cs 加模块 + ini 三行 + NavInvoker AAIController + 生成点投影 + 录制门控。（CPU 侧，SM5 即可跑，先让 agent 在真实地板动起来，不依赖 SM6。）
4. **B 组装 commandlet**：SceneSpec -> `/Game/DF/Scenes/<scene_id>.umap`，烘焙 PCG（确定性 seed）+ 灯光 + NavMesh bounds；`SceneCatalog` 入库。
5. **SM6 启用 + 单节点验证**：A6000/L40S 上 `-vulkan -sm6`，grep `SF_VULKAN_SM6`/feature level、确认无 `Failed to load Vulkan Driver`；过 profile 校验（必要时 `-SkipVulkanProfileCheck`）。确认驱动 ≥570。（裁决3/4，per-node 实测。）
6. **TickCaptureManager Lumen 三项 PP 覆盖 + persist + warmup 16–30**，配 RendererSettings；先软件 Lumen（需 `r.GenerateMeshDistanceFields=True`），A/B + DumpGPU 验证间接光。（门3 是真正阻塞。）
7. **多小时 soak + 多实例 fan-out 定容**：监测 `VK_ERROR_DEVICE_LOST`/显存爬升，定每卡并发；Lumen 渲染钉 L40S/A6000，H100 仅 compute/ingest。（裁决5，未经证实部分必须自测。）
8. **接入真实关卡源**：Windows/Mac 下载 City Sample/Fab .umap -> rsync -> 注册为 B 阶段 external scene；验证能否在 5.5.4 打开 + Big_City `IsStreamingCompleted` 门控 + EULA/生成式 AI 条款合规。
9. **可选高保真分支**：必要时改用 primary-view（真实相机 + backbuffer 回读）或 Movie Render Queue（含 Warm Up Count，专为 Lumen 收敛设计），规避 SceneCapture 专属 Lumen 缺陷与硬件 RT（`r.Lumen.HardwareRayTracing=1` + `r.RayTracing.SceneCaptures=1`）。