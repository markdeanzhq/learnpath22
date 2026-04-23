# 开题报告与实现对齐说明（Thesis Alignment Notes）

> 目的：独立记录"开题报告（2025-12-15）"与"当前实现（2026-04-16）"之间的差异、调整原因与合理化依据。供论文撰写与答辩准备时查阅。本文件遵循用户 2026-04-16 决策 Q7，作为论文调整的依据与工程合理化基线。

## 一、总体结论

当前实现**整体对齐开题报告**的研究目标、技术路线与功能范围，但在工程细节上存在多处"收缩/增强/替换"。所有调整均朝**可实现、可解释、可演示、可控**方向演进，不背离开题研究意图。**论文撰写口径（Q1 决策②）**：保留开题延续性，另设"实现调整说明"小节集中交代差异。

**差异类型分级**：
- 🟢 **一致**：实现与开题表述一致，论文直接沿用
- 🟡 **收缩/替换**：实现较开题口径有收缩或工程化替换，论文需正面说明
- 🔴 **潜在风险**：开题承诺但未交付的验证物或指标，需在后续阶段补齐或替换

---

## 二、评分公式对照表

### 2.1 开题报告（论证性公式）

```
Priority(v) = 0.30·Need(v) + 0.25·Importance(v) + 0.15·Preference(v)
              + 0.15·Bridge(v) − 0.15·Cost(v)

Need(v) = 0.40·gap_math + 0.30·gap_coding + 0.30·gap_domain
```

### 2.2 当前实现（`backend/app/planner/scoring.py` + `scoring_config.json`）

**补强评分（选择基础补强节点）** `calc_reinforce_score`:
```
Reinforce(v) = 0.45·gap_total + 0.20·foundation_bonus + 0.15·bridge_value
               + 0.10·main_path_bonus + 0.10·beginner_bonus
  (阈值 0.45 触发补强；单次规划最多补强 6 个节点)
```

**优先级评分（拓扑排序时多候选定序）** `calc_priority_score`:
```
Priority(v) = 0.28·importance_norm + 0.22·goal_relevance
              + 0.15·preference_fit + 0.10·main_path_bonus + 0.10·bridge_value
              − 0.10·difficulty_norm − 0.10·gap_total − 0.05·time_cost_norm
              + Δmode_adjust

其中 Δmode_adjust 由 steady / efficient / practice 三种模式提供微调：
  steady    :  +0.08·(1 − difficulty_norm) + 0.05·is_foundation
  efficient :  +0.08·goal_relevance + 0.05·(1 − time_cost_norm)
  practice  :  +0.08·practice_weight + 0.05·is_practice

Gap(v) = 0.40·gap_ml + 0.35·gap_math + 0.25·gap_coding   (归一化到 [0,1])
```

### 2.3 差异分析

| 维度 | 开题 | 实现 | 说明 |
|---|---|---|---|
| 评分层次 | 单层 Priority | 双层：**补强 Reinforce + 排序 Priority** | 🟡 实现引入"画像补强选择"阶段，让基础薄弱学习者额外获得前置支撑节点，开题未显式分层但不违背意图 |
| Need / Gap 权重 | math 0.40 / coding 0.30 / domain 0.30 | ml 0.40 / math 0.35 / coding 0.25 | 🟡 实现以 ML 领域为核心（突出目标领域匹配），与单领域落地定位一致；论文需重算并标注"领域包驱动的权重校准" |
| Importance | 直接项 +0.25 | 归一化 +0.28，并区分 importance_final 与 bridge_value | 🟢 等价细化 |
| Preference | 直接项 +0.15 | preference_fit 内部融合 theory/practice 比例 +0.15 | 🟢 等价 |
| Bridge | 直接项 +0.15 | 单独项 +0.10，另设 main_path_bonus +0.10 | 🟡 拆分为两项，更精确 |
| Cost | −0.15 | −0.10 difficulty − 0.10 gap − 0.05 time_cost | 🟡 拆分为难度、差距、时间三维惩罚 |
| 模式切换 | 未提 | 新增 steady/efficient/practice 三模式调整 | 🟡 实现**超出开题范围**的增强；建议论文作为创新点之一正面写 |
| 目标相关度 | 未提 | 新增 `goal_relevance`（反向 BFS 距离归一化） | 🟡 实现**超出开题范围**；建议论文作为创新点之一正面写 |
| 权重校准 | 承诺"启发式赋值，后续校准" | 权重集中在 `scoring_config.json`，可配置但**尚无消融实验数据** | 🔴 Q4 决策需补齐 |

### 2.4 论文建议写法

> "开题阶段拟定的单层 Priority 公式在原型实现过程中被拆分为**补强层**与**排序层**双层评分，并引入 `goal_relevance` 与模式调整两项扩展。这一调整保留了开题公式的主要因子（Need/Importance/Preference/Bridge/Cost），在单领域落地过程中按实际节点属性粒度细化，使学习者画像能对路径生成产生更具区分度的影响。扩展项不违背开题研究意图，权重通过 `scoring_config.json` 集中管理，便于后续消融实验校准。"

---

## 三、画像参数对照表

| 开题字段 | 实现字段 | 类型 | 差异说明 |
|---|---|---|---|
| `math_level` (1–5) | `math_level` (1–5) | int | 🟢 一致 |
| `coding_level` (1–5) | `coding_level` (1–5) | int | 🟢 一致 |
| `domain_level` (1–5) | `ml_level` (1–5) | int | 🟡 重命名以反映单领域定位（`machine_learning`） |
| `theory_preference` (0–1) | `theory_weight` (0–1) | float | 🟢 语义等价 |
| `practice_preference` (0–1) | `practice_weight`（= 1 − theory_weight） | float | 🟡 互补关系，减少冗余输入 |
| `weekly_hours` | `weekly_hours` | float | 🟢 一致 |
| `goal_depth`（入门/掌握/进阶） | `deadline_weeks`（周数预算） | int\|null | 🟡 替换：将主观"目标深度"改为客观"周数预算"，可直接用于时间预算校验；"入门/掌握/进阶"语义通过 `goal_templates.json` 目标模板隐式承载 |

---

## 四、功能模块对照表

| 开题模块 | 实现模块 | 状态 | 差异说明 |
|---|---|---|---|
| 学习目标输入与解析 | `goal_service.py`（LLM 优先 + 规则兜底） | 🟢 | 支持 domain / concept / problem 三类 |
| 学习者画像采集 | `profile_collector_service.py`（LLM 问卷 + 静态五题兜底） | 🟢 | 静态问卷为答辩时的稳妥降级路径 |
| 知识图谱构建与管理 | `domain_packs/machine_learning/`（8 个 JSON）+ `graph_sync_service.py` | 🟡 | 开题 8 步流程中"自动关系抽取"未实现；首版主干由人工整理，自动化部分仅用于搜索补充 |
| 路径规划 | `planner/` (closure/scoring/topology/staging/budget/audit) | 🟢 | 五步主链路完整落地 |
| 图谱可视化 | `frontend/src/views/Knowledge/`（Cytoscape.js） | 🟢 | Domain / Project 视图切换 |
| 学习进度追踪与重规划 | `tracking_service.py` + `replan_service.py`（双模式） | 🟢 | `progress_aware` / `profile_update` 实现完整 |
| 辅助问答模块 | `explanation_service.py`（**结构化 DTO**） | 🟡 | 开题"对话式问答"替换为结构化解释（节点/排序/阶段/依赖/预算）；Q6 决策：后续**补一层可选 LLM 润色**恢复开题承诺 |

---

## 五、图谱构建流程对照

| 开题 8 步 | 实现对应 | 状态 |
|---|---|---|
| ① 确定领域边界 | `manifest.json` + README 锁定 ML 单领域 | 🟢 |
| ② 种子节点表 | `nodes.json` 48 节点 | 🟢 |
| ③ 抽取前置/扩展关系 | `requires_edges.json` / `related_edges.json` | 🟡 **人工整理为主**，自动抽取未实现 |
| ④ 节点属性标定 | `nodes.json` 含 difficulty/importance/req_math/req_coding/req_ml/theory_weight/practice_weight/estimated_hours | 🟢 |
| ⑤ 图谱一致性校验 | `graph_sync_service.py` + 测试 | 🟢 |
| ⑥ 资源挂载与目标模板 | `resources.json` + `goal_templates.json` | 🟢 |
| ⑦ Neo4j 入库与接口化 | `graph_sync_service.py` + `/api/v1/graph` | 🟢 |
| ⑧ 规划应用与循环修正 | `calibration_overrides.json` + `stage_rules.json` | 🟢 |

### 论文建议写法

> "知识图谱构建流程的**第 3 步（关系抽取）**在开题阶段原计划引入半自动化关系候选抽取，实际实现中出于图谱质量与答辩稳定性考量，首版收缩为**人工整理的 Domain Pack JSON**，自动化能力保留在联网搜索与资源补充层面，不直接回写主干图谱。此调整遵循开题报告中'主干宜半自动化、核心 REQUIRES 关系首版不宜完全自动化'的原判断。"

---

## 六、开题承诺但尚未交付的验证物（🔴 风险项，待补齐）

根据 Q3 / Q4 决策：

| 开题承诺 | 当前状态 | 补齐方案 |
|---|---|---|
| 依赖满足率 = 100% | 无量化脚本 | 【保留】写 `scripts/evaluate_dependency.py` 扫描 latest_plan，输出违反率 |
| 环与异常检查 | `closure.py` / `topology.py` 内含校验，抛 `ValueError` | 【保留】包装为独立评估并输出报表 |
| 教材目录顺序对比 | 无基线数据 | 【保留】手工整理《周志华/李航》章节序列作为基线，计算 Kendall τ 相关系数（替换"主观一致性"为**量化指标**） |
| 骨干节点覆盖率 | 无定义 | 【保留】在 `manifest.json` 中标记 backbone 节点，评估路径对骨干覆盖率 |
| 阶段划分合理性 | 无量化 | **替换指标**：建议用"**阶段内依赖闭包完整率**"（阶段 k 的节点所需前置是否都在 ≤k 阶段内）作为客观可计算指标 |
| 权重消融实验 | 无 | 【新增】3–5 组权重组合 × 3 个典型目标，输出对比矩阵 |

### 关于"合理化替换"的说明（Q3 决策延伸）

部分开题指标偏主观（如"教材顺序对比"、"阶段划分合理性"），建议按下列映射转为客观量化：
- 教材顺序对比 → **Kendall τ 秩相关系数**（系统序列 vs 教材目录序列）
- 阶段划分合理性 → **阶段依赖闭包完整率**（可 100% 量化）
- 骨干覆盖率 → **节点类型覆盖矩阵**（数学/编程/ML 概念/监督模型/评估 5 类覆盖比例）

---

## 七、开题报告中需要在论文中"正面说明"的不精确表述

| 开题原文 | 问题 | 论文调整建议 |
|---|---|---|
| "通用框架 + 单领域落地验证" | 实现仅做单领域，"通用"仅停留在代码抽象层 | 论文明确写"方法可迁移、工程未验证；后续工作项" |
| "AI 辅助生成路径解释文本" | 当前实现为规则 DTO | 通过 Q6 补 LLM 润色层恢复；论文写"结构化解释 + 可选 LLM 自然语言润色" |
| "联网搜索与 AI 抽取用于候选资源与关键词扩展" | 仅实现资源补充，未做关键词扩展回写 | 论文写"搜索仅用于在线资源增强展示，不回写图谱主干" |
| "辅助问答模块（围绕当前节点提供说明）" | 实现为结构化面板，非对话 | 论文将其归入"解释模块"，不单列问答子模块 |
| "候选资源抓取、关系候选抽取半自动化" | 实际只做资源抓取 | 论文收缩到"资源层半自动化，关系层人工" |

---

## 八、建议的论文章节映射

| 论文章节 | 本文件对应小节 |
|---|---|
| 第 3 章 系统设计 | § 2.1, § 3, § 4, § 5 |
| 第 4 章 路径规划算法实现 | § 2.2, § 2.3 |
| 第 4 章 "实现调整说明"小节 | § 2.4, § 3, § 7 |
| 第 5 章 实验与验证 | § 6 + 后续 plan 阶段补齐 |
| 第 6 章 总结与展望 | § 7 |

---

## 九、版本记录

- 2026-04-16 初版。对齐 8 项决策（Q1–Q8）并确立论文差异说明基线。
