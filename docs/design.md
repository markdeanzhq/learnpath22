# 系统设计文档

## 1. 系统定位

**LearnPath-KG** 当前交付物是一个面向“机器学习基础”场景的本科毕业设计原型，不是通用教育平台。系统目标是围绕单一领域完成一条可运行、可解释、可验证、可演示的学习路径规划闭环。

当前版本已经覆盖项目创建、画像采集、路径生成、解释、图谱查看与审核、进度追踪、重规划、资料搜索、运行时设置与健康检查等能力；其中图谱审核当前以节点/边审核与 `removed` 过滤为核心，`Stage` / `Resource` 扩展实体主要用于只读展示与图谱补充视图。

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
│  graph_service / graph_sync_service / search_service        │
├──────────────────────────────────────────────────────────────┤
│                    规划引擎纯函数管线                          │
│  closure → scoring → topology → staging → budget → audit   │
├──────────────────────────────────────────────────────────────┤
│                       数据与知识层                            │
│  SQLite（业务状态） + Neo4j（图谱展示） + Domain Pack JSON   │
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

### 3.2 目标解析与画像采集

位置：`backend/app/services/goal_service.py`、`backend/app/services/profile_collector_service.py`

已实现能力：
- 学习目标支持 `domain`、`concept`、`problem` 三类输入，三类公开目标类型由当前 Domain Pack manifest 声明并在运行时校验
- 项目创建采用 `preview -> select candidate -> create` 流程；项目目标重新确认采用 `project preview -> select candidate -> reconfirm` 流程
- preview 零候选严格返回 `422 EMPTY_CANDIDATES`，并携带稳定 `reason_code` 与面向用户的 `reason_text`
- 目标解析采用规则候选、词面召回与可选 LLM 补充的候选融合策略；候选排序使用确定性 tie-break，preview 不回退默认目标策略
- 画像采集支持两条链路：
  - LLM 在线生成结构化澄清问题
  - 静态五题问卷兜底
- 问卷答案会被确定性映射为画像参数并落库

核心画像维度包括：
- `math_level`
- `coding_level`
- `ml_level`
- `theory_weight`
- `weekly_hours`
- `deadline_weeks`

### 3.3 路径规划、解释与重规划

位置：`backend/app/planner/`、`backend/app/api/v1/plans.py`、`backend/app/api/v1/replans.py`

规划主链路如下：

```text
目标节点
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
- 节点解释、排序解释、阶段解释、依赖链解释、预算解释
- `progress_aware` / `profile_update` 两种重规划模式

### 3.4 图谱展示与审核

位置：`backend/app/api/v1/graph.py`、`frontend/src/views/Knowledge/`

已实现能力：
- Domain 级图谱查看（当前为默认机器学习领域视图）
- Project 级图谱查看（使用项目自身 `domain`）
- 路径相关子图查询
- 扩展实体（Stage / Resource）只读视图
- 节点/边审核状态维护
- `removed` 审核结果参与后续路径生成与重规划过滤

Neo4j 承担**展示与交互视图**角色，存储 `KnowledgeNode`、`Stage` 与 `Resource` 完整图谱模型；规划计算仍以本地知识包和业务数据为主，不依赖在线搜索结果直接入图。

### 3.5 资料搜索、资源增强与运行时设置

位置：`backend/app/services/search_service.py`、`backend/app/services/resource_recommendation_service.py`、`frontend/src/views/Search/`、`frontend/src/views/Path/`、`frontend/src/views/Settings/`

已实现能力：
- 资料搜索接入 Tavily
- 搜索页在缺少 `SEARCH_API_KEY` 时给出显式引导
- 路径页支持“路径后增强式资源补充”，可按阶段自动补充候选资源
- 搜索结果支持手动绑定到指定阶段，形成“静态资源保底 + 在线增强补充”的双层资源机制
- 运行时资源绑定写入 SQLite，不会直接回写 Domain Pack
- 设置页支持录入 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`、`SEARCH_API_KEY`
- `GET /api/v1/health/config` 与 `PUT /api/v1/health/config` 支持查询与更新运行时配置，并持久化到 SQLite
- `GET /api/v1/health/llm` 支持当前 LLM 配置连通性检查
- `GET /api/v1/health/search` 支持搜索依赖独立 readiness 检查
- `GET /api/v1/health/readiness` 返回双层 readiness 语义，并包含 `services.graph_sync`
- 前端 `normalizeReadiness` 对旧联调实例保留兼容归一化逻辑

需要强调的是：当前搜索与资源增强能力用于**在线补充学习资料与演示增强**，帮助学习者补充路径相关资源，不作为知识图谱构建或路径规划主链的硬依赖。

### 3.6 健康检查与环境基线

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

### 4.1 SQLite（10 张业务表）

当前已落地表：
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

其中：
- `LearningPath` / `PathStage` / `PathTask` 负责承载阶段化路径结果
- `TrackingEvent` 记录 `start` / `complete` / `skip` 等学习事件
- `GET /tracking/summary` 以最新路径版本中的节点集合作为统计口径，而不是历史累计节点全集
- `GraphReviewStatus` 存储节点与边的审核状态
- `resource_bindings` 用于保存项目/路径级别的阶段资源绑定结果，区分静态保底、在线增强与手动绑定来源

### 4.2 Neo4j

Neo4j 用于图谱展示与审核视图，存储对象包含 `KnowledgeNode`、`Stage` 与 `Resource` 实体。

支持的关系类型：
- `REQUIRES` / `RELATED_TO`：知识节点间的硬依赖与语义关联
- `PRECEDES`：阶段（Stage）间的先后顺序
- `CONTAINS`：阶段对知识节点的包含关系
- `HAS_RESOURCE`：阶段关联的推荐学习资源
- `COVERS`：资源对特定知识节点的覆盖关系

其职责是可视化与交互，不承担主规划结果的持久化职责。

## 5. 前端页面

| 页面 | 路由 | 当前实现功能 |
|------|------|-------------|
| 项目创建 | `/project` | 目标录入、候选预览、选择候选后创建项目、画像问卷采集入口；空候选错误展示 `reason_text` 与 `reason_code` |
| 知识图谱 | `/knowledge` | 图谱可视化、默认领域/project 切换、节点/边审核、按路由 `nodeId` 聚焦节点 |
| 学习路径 | `/path` | 阶段化路径展示、解释面板、按阶段自动补充推荐资源、路径页内搜索、搜索结果绑定到阶段、从任务卡片跳转到 Knowledge 定位节点 |
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
