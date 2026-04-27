# 系统设计文档

## 1. 系统定位

**LearnPath-KG** 当前交付物是一个面向“机器学习基础”场景的本科毕业设计原型，不是通用教育平台。系统目标是围绕单一领域完成一条可运行、可解释、可验证、可演示的学习路径规划闭环。

当前版本已经覆盖项目创建、画像采集、路径生成、解释、图谱查看与审核、项目级 overlay 扩展、进度追踪、重规划、资料搜索、运行时设置与健康检查等能力。图谱审核包含 baseline 节点/边审核与 project overlay 候选审核；`Stage` / `Resource` 扩展实体仍主要用于只读展示与图谱补充视图。

## 2. 当前实现架构

```text
┌──────────────────────────────────────────────────────────────┐
│                      前端 Vue 3 + Vite                       │
│  /project /knowledge /path /search /dashboard /settings     │
├──────────────────────────────────────────────────────────────┤
│                     FastAPI 后端 API 层                      │
│  projects / profiles / collector / plans / explanation      │
│  tracking / replans / graph / search / health               │
├──────────────────────────────────────────────────────────────┤
│                    业务与算法服务层                           │
│  goal_service / profile_collector_service / planner_service │
│  graph_service / graph_sync_service / overlay services      │
├──────────────────────────────────────────────────────────────┤
│                    规划引擎纯函数管线                          │
│  ProjectGraphSnapshot → closure → topology → audit         │
├──────────────────────────────────────────────────────────────┤
│                       数据与知识层                            │
│  SQLite（业务+overlay真源） + Neo4j（投影视图） + Pack JSON    │
└──────────────────────────────────────────────────────────────┘
```

## 3. 核心模块

### 3.1 Domain Pack（机器学习单领域知识包）

位置：`backend/app/domain_packs/machine_learning/`

当前领域知识包包含 **48 个 KnowledgeNode**，配套：
- `requires_edges.json` / `related_edges.json`：图谱依赖与语义关联
- `stages.json` / `resources.json`：静态阶段映射与学习资源
- `goal_templates.json` / `calibration_overrides.json` / `stage_rules.json`：目标映射、评分校准与阶段规则

当前版本在产品口径与接口层均收敛为 `machine_learning` 单领域；轻量 registry/contract 只用于把默认领域、支持的目标类型、默认策略和 pack hash 收口为统一框架边界，不表示多领域产品入口已经开放。`KnowledgeNode` 是规划主链事实源，`Stage` 与 `Resource` 主要承担展示与说明职责。

### 3.2 目标理解、Coverage Router 与画像采集

位置：`backend/app/services/goal_service.py`、`backend/app/services/goal_resolution_service.py`、`backend/app/services/coverage_router.py`、`backend/app/services/profile_collector_service.py`

目标理解链路被拆成受控状态机：

```text
用户自然语言
→ LLM GoalUnderstanding v1（主领域 / ML 相关性 / 边界判断 / 证据）
→ Domain Admission Policy
→ GoalFrame v1 + Coverage Router
→ candidate / partial / clarification / extension draft / boundary
→ user confirm
→ rule planner
```

LLM 在线时只承担开放语义理解，不直接生成正式学习路径，不直接确认 `target_node_ids`，也不写入图谱。系统准入策略根据 `domain_decision = in_domain | cross_domain | out_of_domain | ambiguous` 决定是否进入知识图谱节点校验、受控澄清或边界拒绝。

已实现能力：
- 学习目标支持 `domain`、`concept`、`problem` 三类公开输入，三类目标类型由当前 Domain Pack manifest 声明并在运行时校验
- 目标解析采用 LLM GoalUnderstanding 先行与 rules-first GoalFrame 抽取组合；LLM 缺失、失败、超时、非法 JSON、低置信度或策略不安全输出会 fail-closed 为受控澄清或安全拒绝，不会直接降级为可创建候选
- Coverage Router 使用封闭枚举：`covered`、`partial`、`in_domain_uncovered`、`adjacent_domain`、`cross_domain`、`out_of_domain`、`ambiguous`
- `cross_domain` 表示外部应用领域中包含机器学习方法意图，必须先澄清是否只按机器学习基础范围创建路径
- 目标预览对合法业务状态返回 `200` discriminated union，核心字段为 `goal_understanding`、`result_type` 与 `coverage_status`；非法转换、未知枚举、过期会话与 hash drift 返回 `4xx` 且没有写副作用
- 项目创建采用 `goal preview -> select candidate / accept partial -> create` 流程；项目目标重新确认采用同样的 project-scoped preview/confirm 流程
- `partial` 目标必须显式接受后才能规划，正式 audit 记录 `partial_accepted` 与 `missing_concepts`
- `ambiguous` 目标进入有 TTL、`turn_count/max_turns`、`pack_hash` 与 `project_graph_hash` 的 REST clarification session；自由文本答案必须先解析为受控 delta
- `in_domain_uncovered` 只提供显式 overlay 草稿入口，草稿复用 project overlay lifecycle，默认 planner-invisible
- `out_of_domain` 不调用 planner，不创建正式路径；`adjacent_domain` 只能映射到当前机器学习图谱内已有的前置/支撑节点

GoalFrame 的权威边界：
- 可以影响的 planner-compatible 参数只有 `path_mode`、`theory_weight/practice_weight`、`weekly_hours/deadline_weeks` 与 `explanation_focus`
- `target_node_ids` 只是候选提示，不能覆盖用户确认的 `confirmed_target_node_ids`
- 不能删除硬 `REQUIRES` ancestors，不能把 overlay 草稿节点标记为正式目标，不能直接写 `LearningPath`
- 正式 planner 的目标事实源始终是用户确认候选或显式接受 partial 后的 covered target set

画像采集支持两条链路：
- LLM 在线生成 schema-constrained 澄清问题
- 静态五题问卷兜底

问卷答案会被确定性映射为画像参数并落库。核心画像维度包括：`math_level`、`coding_level`、`ml_level`、`theory_weight`、`practice_weight`、`weekly_hours`、`deadline_weeks`。

`path_mode_preference`、`persona_label`、`persona_summary`、`persona_evidence` 属于展示与解释字段，仅进入 audit/report 快照，不作为 planner numeric scoring 的事实源。

### 3.3 路径规划、解释与重规划

位置：`backend/app/planner/`、`backend/app/api/v1/plans.py`、`backend/app/api/v1/replans.py`

规划主链路如下：

```text
目标节点 + ProjectGraphSnapshot
→ baseline-minus-review + planner-visible overlay
→ 前置闭包提取
→ 画像补强选择
→ 子图提取
→ 拓扑排序（多因子优先级）
→ 阶段划分
→ 时间预算
→ 审计日志与解释输出
```

当前已实现：
- 阶段化学习路径生成
- `standard`、`compressed`、`theory_first`、`practice_first` 路径模式
- compressed mode 保留目标与全部硬依赖 ancestors，不裁剪 mandatory closure
- 路径变体使用 TTL preview session 展示 `standard`、`compressed`、`theory_first`、`practice_first` 多种方案；preview 不写最新路径、跟踪状态、资源绑定或解释缓存，确认一个 variant 才写入一个正式 `LearningPath` 版本
- 自然语言反馈重规划使用 V1 intent preview/confirm：`compress_time`、`increase_practice`、`increase_theory`、`adjust_deadline`、`mark_known_nodes`；unsupported/low-confidence 反馈只澄清或拒绝，不改变正式路径
- `mark_known_nodes` 先创建 known-node confirmation draft，二次确认后才可影响反馈 replan，不会删除硬依赖
- 节点解释、排序解释、阶段解释、依赖链解释、预算解释
- audit 记录 GoalFrame snapshot、derived planner parameters、coverage decision、selected candidate、confirmed targets、partial acceptance、missing concepts、clarification trace、overlay lineage、variant/feedback intent、authority labels、decision chain、included/excluded nodes、exclusion_reason、path_mode 与 budget_status
- `progress_aware` / `profile_update` 两种传统重规划模式，并与普通规划消费同一 ProjectGraphSnapshot

`ProjectGraphSnapshot` 是规划入口使用的项目图谱快照：它把 Domain Pack baseline、项目级 `removed` 审核状态和 planner-visible overlay 合成为 pack-compatible 结构。`project_graph_hash` 由 pack hash、removed baseline 集合和 planner-visible node/edge overlay 的 canonical 内容共同决定；review/planning 变化会影响 hash，纯 UI metadata 与 resource-only 变化不影响 hash。

系统明确区分 review graph 与 planning graph：Knowledge 中的 project graph 用于审核与可视化，可展示 active overlay node/edge/resource 候选；planner 只消费 validation=`valid`、review=`confirmed`、planning_enabled=true、未 promoted 且 session 可编辑的 node/edge。resource 是 planning-opaque 对象，只影响资源展示和 promotion 资格，不进入 `ProjectGraphSnapshot`、path graph、goal resolution、planner 或 replan。

### 3.4 图谱展示、Overlay 与审核

位置：`backend/app/api/v1/graph.py`、`frontend/src/views/Knowledge/`

已实现能力：
- Domain 级图谱查看（当前为默认机器学习领域视图）
- Project 级图谱查看，`scope=project` 表示 baseline-minus-review 加 active overlay 的项目全图
- `scope=path&path_id=latest` 最新路径子图入口，使用 latest plan node set 与 `ProjectGraphSnapshot` 构造 induced subgraph；无 latest plan 时返回 `empty_reason=project_latest_plan_missing`，非 `latest` path_id 显式报错
- 扩展实体（Stage / Resource）只读视图
- baseline 节点/边审核状态维护，`removed` 参与后续路径生成与重规划过滤
- overlay pasted text / search URL source 持久化
- extraction session 候选节点、边、资源的 schema 校验、去重、edge legality 与 DAG 校验
- overlay review 与 planning toggle 分离，互不隐式改写
- baseline review action set 为 `pending|confirmed|removed`，overlay action set 为 `pending|confirmed|rejected|removed`；未知 origin/lifecycle 在前端显示为安全未知状态并禁用 planner-affecting 操作
- no latest plan 但已有 overlay draft 时，项目图谱仍可展示 overlay 候选

SQLite 是 project overlay 的**真源**：source、session、candidate node/edge/resource、resource binding、persisted search result 与 promotion lineage 都以 SQLite 为准。Neo4j 承担**展示与交互投影**角色，baseline strict sync 只管理 pack-owned labels/entities；overlay projection 使用 project-owned metadata 幂等 upsert，不把 Neo4j 作为 overlay 写入真源。projection canonical status 固定为 `missing|empty|ok|drifted|error`，drift/missing/error 会暴露在同步状态与 Knowledge 状态区中，但不阻断 baseline readiness。

### 3.5 Promotion 与 Domain Pack 写入策略

Promotion 是把经过审核的项目级 overlay 候选提升为 Domain Pack baseline 的受控流程。

设计原则：
- preview 是 no-write dry-run，执行字段校验、重复检测、edge legality、DAG validation 与 pack reload validation
- commit 由 `DOMAIN_PACK_PROMOTION_ENABLED` feature flag 和 admin secret 双重保护
- Domain Pack JSON 写入通过 temp file 与原子替换完成
- commit 后执行 reload、canonical hash rebuild 与 Neo4j baseline sync
- 对用户可见语义是 all-or-nothing；失败时不把半成品暴露为成功推广
- promotion batch/item 记录 source project、session、sources、provenance、reviewer/admin、baseline pack hash 与 resulting pack hash

failure policy：SQLite overlay 仍是真源，promotion 或 Neo4j projection 失败不会破坏项目级草稿；promotion disabled/forbidden 时仅阻断写 Pack，不影响项目创建、画像、路径、解释、跟踪与重规划主链。commit 成功后 candidate 进入只读归档态，active overlay selector、session detail、project/path graph、planner 与 overlay projection 默认排除 promoted candidate；失败时记录 failed batch 与失败原因，candidate 不残留为 active promoted；重复 commit 已 promoted 集合返回安全 no-op/replay，不重复写 pack 或 history。

### 3.6 资料搜索、资源增强与运行时设置

位置：`backend/app/services/search_service.py`、`backend/app/services/resource_recommendation_service.py`、`frontend/src/views/Search/`、`frontend/src/views/Path/`、`frontend/src/views/Settings/`

已实现能力：
- 资料搜索接入 Tavily
- 搜索页在缺少 `SEARCH_API_KEY` 时给出显式引导
- 路径页支持“知识点优先”的资源补充，静态资源按 `node_ids` 挂载，Tavily 候选按路径节点自动补充，阶段资源仅作为总览保底
- 搜索结果支持保存为项目级 persisted search result，刷新后可恢复 selected、summary、quality 与 binding state
- persisted search result 可通过幂等 bridge 转为 overlay `search_url` source，Knowledge 创建 extraction session 时只提交 `source_ids[]`，不直接提交 result ID
- 搜索结果支持手动绑定到当前路径知识点或项目节点，形成“知识点静态资源保底 + 在线增强补充 + 阶段总览兜底”的资源机制
- 运行时资源绑定写入 SQLite，不会直接回写 Domain Pack
- 设置页支持录入 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`、`SEARCH_API_KEY`
- `GET /api/v1/health/config` 与 `PUT /api/v1/health/config` 支持查询与更新运行时配置，并持久化到 SQLite
- `GET /api/v1/health/llm` 支持当前 LLM 配置连通性检查
- `GET /api/v1/health/search` 支持搜索依赖独立 readiness 检查
- `GET /api/v1/health/readiness` 返回双层 readiness 语义，并包含 `services.graph_sync`
- 前端 `normalizeReadiness` 对旧联调实例保留兼容归一化逻辑

需要强调的是：当前搜索与资源增强能力用于**在线补充学习资料与演示增强**，帮助学习者补充路径相关资源，不作为知识图谱构建或路径规划主链的硬依赖。

### 3.7 健康检查与环境基线

位置：`backend/app/api/v1/health.py`、`backend/app/core/config.py`

`GET /api/v1/health` 当前输出：
- 项目名与版本
- Python 3.12 基线
- 实际 Python 运行版本
- 原型范围与交付阶段标识
- 运行时配置作用域
- SQLite / Neo4j / LLM / Search 的非敏感环境指纹

`GET /api/v1/health` 当前提供的是**环境基线**，用于答辩检查与后续验证证据复用；真正的聚合依赖判断由 `GET /api/v1/health/readiness` 提供。

当前 `GET /api/v1/health/readiness` 的设计语义为：
- `core_ready`：SQLite、Neo4j 与 `graph_sync` 是否全部就绪
- `demo_ready`：离线论文主链是否可演示；当前与 `core_ready` 一致
- `enhanced_ready`：LLM 与搜索等在线增强能力是否就绪
- `ready`：只有当 `demo_ready && enhanced_ready` 同时满足时才为 `true`

其中 `services.graph_sync` 直接来自图谱同步状态查询，用于说明 Neo4j 中的 Domain Pack 主图与扩展实体是否与当前代码包保持同步。

## 4. 数据模型

### 4.1 SQLite（业务状态与 Project Overlay 真源）

当前已落地核心业务表：
- `runtime_settings`
- `learning_projects`
- `learner_profiles`
- `knowledge_sources`
- `learning_paths`
- `path_stages`
- `path_tasks`
- `tracking_events`
- `graph_review_status`
- `resource_bindings`

Project overlay 相关表包括：
- `project_overlay_sources`
- `project_overlay_extraction_sessions`
- `project_overlay_nodes`
- `project_overlay_edges`
- `project_overlay_resources`
- `project_overlay_resource_bindings`
- `project_overlay_promotion_batches`
- `project_overlay_promotion_items`
- `persisted_search_results`

其中：
- `LearningPath` / `PathStage` / `PathTask` 负责承载阶段化路径结果
- `TrackingEvent` 记录 `start` / `complete` / `skip` 等学习事件
- `GET /tracking/summary` 以最新路径版本中的节点集合作为统计口径，而不是历史累计节点全集
- `GraphReviewStatus` 存储 baseline 节点与边的审核状态
- `resource_bindings` 用于保存项目/路径级别的节点或阶段资源绑定结果，区分静态保底、在线增强与手动绑定来源
- overlay source/session/candidate/resource/promotion/search 行随项目删除级联清理，避免孤儿数据

### 4.2 Neo4j

Neo4j 用于图谱展示与审核视图，存储对象包含 baseline `KnowledgeNode`、`Stage`、`Resource` 以及 project-owned overlay projection 实体。

支持的关系类型：
- `REQUIRES` / `RELATED_TO`：知识节点间的硬依赖与语义关联
- `PRECEDES`：阶段（Stage）间的先后顺序
- `CONTAINS`：阶段对知识节点的包含关系
- `HAS_RESOURCE`：阶段关联的推荐学习资源
- `COVERS`：资源对特定知识节点的覆盖关系

其职责是可视化与交互，不承担主规划结果或 overlay 真源的持久化职责。baseline sync 不删除 overlay projection；projection 失败只记录 drift，SQLite 中的项目级草稿仍保持可恢复。

## 5. 前端页面

| 页面 | 路由 | 当前实现功能 |
|------|------|-------------|
| 项目创建 | `/project` | 目标录入、GoalFrame/coverage 理解面板、候选选择、partial acceptance、clarification、boundary rejection、extension draft deep link、选择候选后创建项目、画像问卷采集入口；stale/hash drift 会清理不安全预览状态 |
| 知识图谱 | `/knowledge` | 图谱可视化、领域图/项目全图切换、overlay draft 入口、节点/边审核、planning toggle、按路由 `nodeId` / `sessionId` / `goalDraft` 恢复上下文；打开 deep link 不创建草稿、不改变 review/planning 状态 |
| 学习路径 | `/path` | 阶段化路径展示、解释面板、路径 variant preview、feedback replan preview、known-node draft 二次确认、confirm 后保存正式新版本、按知识点自动补充推荐资源、路径页内搜索、搜索结果绑定到知识点、从任务卡片跳转到 Knowledge 定位节点 |
| 资料搜索 | `/search` | 独立搜索页、配置缺失提示、结果列表 |
| 学习进度 | `/dashboard` | 进度统计、事件提交、状态概览、从进度列表跳转到 Knowledge 定位节点 |
| 设置 | `/settings` | 运行时配置录入、配置状态查看、LLM 连通性测试、双层 readiness 预检展示 |

## 6. 运行环境基线

- Python 基线：`3.12`
- Node.js：`18+`
- Neo4j：`5+`
- 搜索服务：Tavily（在线调用）
- LLM：OpenAI 兼容接口（运行时可切换 Base URL / Model）

环境基线口径要求如下：
- `README.md`
- `backend/Dockerfile`
- `GET /api/v1/health`

以上三处对 Python 主次版本应保持一致，避免答辩环境、容器环境与仓库声明出现冲突。
