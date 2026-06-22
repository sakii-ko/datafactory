# 状态与下一步(交接)

> 截至 2026-06-21 夜间自主开发。整套引擎无关骨架 + UE 无头采集 + agent 驱动捕获已端到端跑通并有测试(61 个)。

## 现在能做什么

```bash
# 1) 纯 Python,任意机器(CPU/H100):合成数据,验证骨架
uv venv .venv && uv pip install -e ".[dev]" && .venv/bin/python -m pytest -q
.venv/bin/datafarm run --backend mock --name demo --episodes 4 --steps 16 --out runs

# 2) UE5 无头采集(H100 开发机 / A6000 生产):agent 在场景里游走,相机第一/第三人称跟随
.venv/bin/datafarm run --backend ue --name ue_demo --episodes 2 --steps 64 \
    --res 1280x720 --viewpoints fpv,tpv --out runs
# 或直接跑一条:bash scripts/ue_capture.sh <render_config.json>
# 健康检查:.venv/bin/datafarm healthcheck --backend ue
```

产出:每个 episode 一个目录 = `frames/NNNNNN.png` + `steps.csv`(M-G3 的 `D_t`:逐帧 RGB + 玩家/相机 6DoF + 6 维动作)+ `meta.json`;数据集级 `index.jsonl` + 分桶汇总(按 `viewpoint/label_kind`)。

## 已验证

- 引擎无关骨架(`datafarm/`):schema/pose/action、manifest/writers/qa、assets 目录、Mock 后端、编排、CLI。
- UE5.5.4 Linux 无头:工具链可编 C++;Vulkan 在 H100 可用(ICD 修正);**渲染产线用 A6000/L40S**。
- `TickCapture` 插件:tick 同步采集 RGB + 6DoF + 动作,非阻塞 GPU 回读(已加 layout transition,无 Vulkan ensure),异步存 PNG;~每秒数十帧(固定时间步)。
- `AExplorerCharacter`:无 NavMesh 的开放地面游走(随机选点 + 朝向移动),相机 FPV/TPV 跟随。
- 动作标签:Python 用 `infer_actions` 从位姿增量反推 WSAD(M-G3 §4.2),与引擎解耦。

## 现在是占位、需要升级的

1. **场景**:目前是运行时 spawn 的"地板+几个立方体+光照"测试场景(`SpawnTestScene`)。**真实丰富场景**(City Sample / Fab / asset-library 里的场景)是产出质量的关键 —— 见下"需要你的部分"。
2. **角色**:目前是一个立方体身体的 `ACharacter`。换成 **Mannequin 骨架角色 + Game Animation Sample 运动动画 + 模块化换装**(>1e8 变体)才有 M-G3 的视觉多样性。需要素材。
3. **导航**:简单开放地面游走,无 NavMesh/避障。升级到 NavMesh + EQS(覆盖率/场景丰富度打分)做更自然的探索(implementation-guide §2)。
4. **帧格式**:当前 PNG 为 RGBA(回读自 BGRA);训练取 `[:,:,:3]` 即可,后续可改为直接写 RGB。

## 需要你定 / 提供资源的部分(挡住进一步自动推进)

1. **素材(最关键)**:真实 UE 场景 + Mannequin 角色/动画。途径:免费 City Sample、Fab(Quantum Modular Character + Game Animation Sample,部分需购买/账号)。这些需要你的 Epic/Fab 账号或采购决定。给我素材或获取方式后,我接 P7b(真实场景加载 + 角色装配)。
2. **量产扇出**:把 UE 部署到 `ssh duan`(8×A6000,已确认 Vulkan+docker 就绪,但**尚未装 UE、代码未同步**)。需要:把本仓库 + UE 5.5.4 同步过去(rsync/git)。之后我做多实例/卡的 supervisor 扇出并实测每卡密度与吞吐(P8 剩余)。
3. **EULA**:UE 生成式 AI 条款 —— 你已确认学术研究用途可接受。

## 路线对应 SPEC §8

P1–P6 ✅;P7 进行中(agent 完成,真实内容待素材);P8 进行中(UEBackend 接线✅,多实例扇出待 duan78);P9(视频/RL)按你要求暂不做。
