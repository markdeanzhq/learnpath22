# API 接口文档

> 完整交互式文档请访问: http://localhost:8000/docs (Swagger UI)

Base URL: `/api/v1`

## 项目管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /projects | 创建学习项目 |
| GET | /projects/{id} | 查询项目详情 |
| GET | /projects | 列出所有项目 |
| DELETE | /projects/{id} | 永久删除项目及其关联数据 |

### 项目创建真实流程

当前项目创建不是直接提交 `goal_type/domain` 后立即落库，而是采用三步确认流程：

```text
preview -> select candidate -> create
```

1. 调用 `POST /goal-resolution/preview`，提交学习目标文本与可选目标类型。
2. 后端返回候选目标列表、推荐候选与 `session_id`。
3. 前端展示候选，用户选择 `selected_candidate_id` 后调用 `POST /projects` 创建项目。

**目标预览请求体:**
```json
{
  "goal_text": "我想系统学习机器学习基础",
  "requested_goal_type": "domain"
}
```

说明：
- `requested_goal_type` 可选；省略时由后端自动识别
- 当前公开目标类型稳定为 `domain`、`concept`、`problem`
- `domain` 是兼容字段，公共创建流程不依赖前端传入 `domain`
- 当前版本为机器学习基础单领域原型，不开放多领域选择入口

**目标预览成功响应:**
```json
{
  "session_id": "<resolution_session_id>",
  "expires_at": "2026-04-24T12:00:00",
  "auto_detected_goal_type": "domain",
  "effective_goal_type": "domain",
  "recommended_candidate_id": "template:domain_ml_full",
  "candidates": [
    {
      "candidate_id": "template:domain_ml_full",
      "goal_type": "domain",
      "target_node_ids": ["ml_e07"],
      "mode": "steady",
      "description": "系统学习机器学习基础",
      "template_id": "domain_ml_full",
      "resolve_source": "template",
      "source_breakdown": {"template": 1.0, "lexical": 0.0, "llm": 0.0},
      "score": 0.86,
      "score_breakdown": {"final_score": 0.86},
      "explanation": "template 候选",
      "warnings": []
    }
  ]
}
```

**目标预览零候选响应:**
```json
{
  "error": "EMPTY_CANDIDATES",
  "code": 422,
  "reason_code": "negative_patterns_excluded_all",
  "reason_text": "当前目标文本命中了候选模板，但这些模板都被排除词命中，请改写目标描述后重试。"
}
```

说明：
- 零候选严格返回 `422 EMPTY_CANDIDATES`
- `reason_code` 为稳定机器可读枚举
- `reason_text` 为面向用户的单句说明，前端会优先展示它并带出 `reason_code`
- preview 不会回退到默认目标策略

**创建项目请求体:**
```json
{
  "title": "机器学习入门",
  "goal_text": "我想系统学习机器学习基础",
  "resolution_session_id": "<resolution_session_id>",
  "selected_candidate_id": "template:domain_ml_full"
}
```

说明：
- 创建时必须复用 preview 返回的 `resolution_session_id` 与候选 ID
- 后端会校验目标文本 hash、domain、pack hash 与候选归属，避免使用过期或漂移的预览会话
- `goal_type` 与 `domain` 仅保留兼容语义，不是公共创建流程的事实源

### 项目目标重新确认流程

当已确认目标节点被图谱审核全部移除，或需要重新确认项目目标时，使用项目级流程：

```text
project preview -> select candidate -> reconfirm
```

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /projects/{id}/goal-resolution/preview | 为已有项目创建目标候选预览 |
| PUT | /projects/{id}/goal-resolution | 使用选择的候选更新项目目标 |

项目级 reconfirm 会额外校验 `project_id` 与当前项目图谱 `graph_hash`，避免图谱审核状态变化后复用旧候选。

**删除项目响应示例:**
```json
{
  "id": "<project_id>",
  "message": "项目已删除"
}
```

说明：
- `DELETE /projects/{id}` 成功时返回 `200`
- `DELETE /projects/{id}` 为永久删除
- 删除项目时会级联删除该项目关联的画像、学习路径、路径阶段与任务、知识来源、学习跟踪、图谱审核状态等数据
- 删除不存在的项目会返回 `404`

## 学习者画像

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /projects/{id}/profiles | 提交画像参数 |
| GET | /projects/{id}/profiles/latest | 获取最新画像 |
| POST | /projects/{id}/collector/questions | 获取画像采集问题 |
| POST | /projects/{id}/collector/submit | 提交问卷答案 |

画像字段分为两类：
- 规划权威输入：`math_level`、`coding_level`、`ml_level`、`theory_weight`、`practice_weight`、`weekly_hours`、`deadline_weeks`
- 展示与解释字段：`path_mode_preference`、`persona_label`、`persona_summary`、`persona_evidence`

说明：
- `path_mode_preference` 支持 `standard`、`compressed`、`theory_first`、`practice_first`
- persona 字段只进入展示、解释与 audit 快照，不改变同一 numeric profile 下的规划排序
- LLM 自适应问卷必须输出 schema-constrained 结构；失败时回退静态问卷

## 路径规划

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /projects/{id}/plans | 生成学习路径 |
| GET | /projects/{id}/plans/latest | 获取最新路径 |
| POST | /projects/{id}/replans | 触发重规划 |

路径请求支持 `path_mode`：
- `standard`：默认完整路径
- `compressed`：保留目标与全部 `REQUIRES` ancestors，只裁剪 optional reinforcement / RELATED-only additions
- `theory_first`：理论内容优先，但不破坏硬依赖
- `practice_first`：实践内容优先，但不破坏硬依赖

未知 `path_mode` 返回 `422 INVALID_PATH_MODE`。当 compressed mode 的 mandatory closure 已超预算时，返回 `budget_status=over_budget_required_closure`，不会裁剪硬依赖链。

**路径响应结构:**
```json
{
  "id": "uuid",
  "version": 1,
  "stages": [
    {
      "stage_index": 0,
      "stage_name": "基础准备",
      "tasks": [
        {
          "node_id": "ml_a01",
          "name": "线性代数基础",
          "difficulty": 3,
          "importance": 5,
          "estimated_hours": 8,
          "order_in_stage": 0
        }
      ],
      "estimated_hours": 24
    }
  ],
  "budget_status": "feasible",
  "total_hours": 80,
  "audit": { ... }
}
```

**budget_summary 字段:**
```json
{
  "total_hours": 80,
  "weekly_hours": 10,
  "estimated_weeks": 8.0,
  "available_hours": 120,
  "feasibility_ratio": 1.5,
  "status": "feasible",
  "suggestion": "当前时间预算可支持完整路径"
}
```

**重规划响应补充字段：**
```json
{
  "id": "uuid",
  "version": 2,
  "mode": "progress_aware",
  "diff": {
    "completed": ["ml_a01"],
    "pending": ["ml_b02"]
  },
  "diff_details": {
    "completed": [
      {
        "node_id": "ml_a01",
        "node_name": "线性代数基础"
      }
    ],
    "pending": [
      {
        "node_id": "ml_b02",
        "node_name": "概率统计基础"
      }
    ]
  }
}
```

说明：
- `mode` 支持 `progress_aware` 与 `profile_update`
- `diff` 提供节点 ID 级差异
- `diff_details` 提供面向前端展示的可读名称，避免页面直接暴露节点 ID

## 结构化解释

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /projects/{id}/explanation | 获取路径解释 |

## 进度追踪

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /projects/{id}/tracking/events | 记录学习事件 |
| GET | /projects/{id}/tracking/events | 列出所有事件 |
| GET | /projects/{id}/tracking/summary | 获取按 `latest plan` 口径计算的进度汇总 |

**学习事件类型:** `start` / `complete` / `skip`

说明：
- `tracking/summary` 以当前最新路径版本中的节点集合为统计口径
- 已经被最新计划移除的节点不会继续计入 `total_nodes`
- 该口径同时用于 e2e 脚本、论文验证证据和前端 Dashboard 展示

## 知识图谱

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /projects/{id}/graph | 获取项目关联的图谱数据 |
| GET | /projects/{id}/graph/subgraph?node_ids=a,b | 获取指定节点的子图 |
| GET | /projects/{id}/graph/entities | 获取 Stage / Resource 等扩展实体的只读摘要 |
| POST | /graph/seed | 同步 Domain Pack 到 Neo4j（全局操作） |

`GET /projects/{id}/graph` 的 `scope` 语义：
- `scope=domain`：当前机器学习 Domain Pack 的完整领域图
- `scope=project`：项目全图，等于 baseline-minus-review 加 active overlay review graph
- `scope=path&path_id=latest`：最新路径子图；只接受 `latest`，非 `latest` 返回 `422 INVALID_GRAPH_PATH_ID`

path scope 使用 `LearningPath.latest` 中的节点集合和 `ProjectGraphSnapshot` 构造 induced subgraph，不再查询 baseline-only Neo4j 子图，也不在 path 缺失时回退 project/domain graph。响应会携带 `path_id`、`node_ids`、`missing_node_ids`、`is_empty`，无 latest plan 时返回空图并设置 `empty_reason=project_latest_plan_missing`。

非法 scope 返回 `422 INVALID_GRAPH_SCOPE`。所有图元素都会返回 `origin` 与 `scope`；overlay 元素额外返回 `validation_status`、`review_status`、`planning_enabled`、`promotion_status`、source/provenance/validation metadata。

说明：
- 无 latest plan 但已有 overlay draft 时，`scope=project` 仍返回项目图，不再把项目视为 `project_latest_plan_missing` 空态
- `graph/entities` 只返回扩展实体展示数据，不会触发图谱重同步
- 前端 Knowledge 页使用该接口展示 `Stage` / `Resource` 只读信息
- Path / Dashboard 的“在图谱中定位”会跳转到 Knowledge，并由图谱画布聚焦对应 `nodeId`

### Overlay Source、Extraction 与审核

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /projects/{id}/graph/overlay/sources | 创建 pasted text 或 search URL source |
| POST | /projects/{id}/graph/overlay/extraction-sessions | 从 source IDs 创建抽取会话 |
| GET | /projects/{id}/graph/overlay/extraction-sessions/{session_id} | 读取抽取会话详情 |
| PATCH | /projects/{id}/graph/overlay/nodes/{element_id}/review | 只更新 overlay node 的 review 状态 |
| PATCH | /projects/{id}/graph/overlay/edges/{element_id}/review | 只更新 overlay edge 的 review 状态 |
| PATCH | /projects/{id}/graph/overlay/resources/{element_id}/review | 只更新 overlay resource 的 review 状态 |
| PATCH | /projects/{id}/graph/overlay/nodes/{element_id}/planning | 只更新 overlay node 的 planning 开关 |
| PATCH | /projects/{id}/graph/overlay/edges/{element_id}/planning | 只更新 overlay edge 的 planning 开关 |
| PATCH | /projects/{id}/graph/overlay/resources/{element_id}/planning | 只更新 overlay resource 的 planning 开关 |

说明：
- baseline review 只允许 `pending|confirmed|removed`，`rejected` 返回 `422`；overlay review 允许 `pending|confirmed|rejected|removed`
- `review_status` 与 `planning_enabled` 独立更新，互不隐式改写 validation/source/provenance/promotion 字段
- unknown origin 或 unknown lifecycle status 在前端以安全未知状态展示，并禁用会影响审核或规划的操作
- resource `planning_enabled` 只影响 resource 自身显示/推广资格，不改变 node/edge planner-visible 集合、`ProjectGraphSnapshot`、path graph、goal resolution、planner、replan 或 `project_graph_hash`
- `custom_extension` mode 在创建 extraction session 前检查搜索 readiness；未就绪返回 `503 SEARCH_NOT_READY`
- 搜索未就绪只阻断 custom extension，baseline/project graph 浏览仍可用
- overlay ID 使用 `po:{project_id}:n|e|r:{hash}` 格式并做 collision 检查

### Promotion Preview 与 Commit

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /projects/{id}/graph/overlay/promotion/preview | 校验可推广候选并返回 dry-run 结果 |
| POST | /projects/{id}/graph/overlay/promotion/commit | 将合法 overlay 候选推广入 Domain Pack |
| GET | /projects/{id}/graph/overlay/projection/status | 查询 overlay projection canonical status |

说明：
- preview 执行 field validation、duplicate detection、edge legality、DAG validation 与 pack reload validation，不写入 Domain Pack
- commit 需要 `DOMAIN_PACK_PROMOTION_ENABLED=true` 且通过 admin secret 校验
- flag 未开启返回 `403 PROMOTION_DISABLED`，secret 校验失败返回 `403 PROMOTION_FORBIDDEN`
- commit 使用 temp file 写入、原子替换、reload、canonical hash rebuild 和 Neo4j baseline sync，保证用户可见 all-or-nothing 语义
- promotion batch/item 会持久化 source project、session、sources、provenance、reviewer/admin、baseline pack hash 与 resulting pack hash
- promoted overlay candidate 进入只读归档态，active graph、session detail、planner、path graph 与 overlay projection 默认隐藏；重复 commit 已归档集合返回安全 no-op/replay 语义，不重复写 pack、batch/item 或 Neo4j entity
- projection status 枚举固定为 `missing|empty|ok|drifted|error`：无 overlay payload 为 `empty`，有 payload 无 projection state 为 `missing`，hash 匹配为 `ok`，hash 不一致为 `drifted`，异常为 `error`；响应保留 `reason`、`overlay_hash`、`projected_hash` 与 `projected_at`

## 搜索

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /projects/{id}/search | 搜索学习资料（在线增强） |
| POST | /projects/{id}/search-results | 保存 selected search result |
| GET | /projects/{id}/search-results | 列出项目级持久化搜索结果 |
| POST | /projects/{id}/search-results/bridge-overlay-sources | 幂等桥接 persisted search result 为 overlay source |

说明：
- 搜索能力服务于学习资料补充，不参与路径主链正确性判定
- selected search result 可持久化为 project 级 source，刷新页面后仍可恢复 title、snippet、summary、quality、binding state
- saved-search bridge 复用 `search_url` source type；同一 `(project_id, result_id)` 单调映射到稳定 `source_id`，重复点击或 replay 不创建重复 source，跨项目 result/source ID 会被拒绝
- extraction session request 只接受 `source_ids[]`，不接受 `result_ids[]` 或混合字段；Knowledge drawer 会先把已保存搜索结果桥接为 `source_ids[]` 再创建 extraction session
- 搜索结果可在前端路径页中进一步手动绑定到指定阶段

## 路径资源增强

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /projects/{id}/plans/{path_id}/resources | 获取当前路径的阶段资源列表（静态保底 + 已绑定动态资源） |
| POST | /projects/{id}/plans/{path_id}/resources/recommend | 按阶段自动补充 Tavily 候选资源 |
| POST | /projects/{id}/plans/{path_id}/resources/bind | 手动把搜索结果绑定到指定阶段或节点 |
| POST | /projects/{id}/resources/bindings | 绑定项目级资源到 project node 或 path stage |

**手动绑定请求体示例：**
```json
{
  "stage_name": "核心掌握",
  "title": "逻辑回归核心讲义",
  "url": "https://example.com/logreg",
  "snippet": "覆盖逻辑回归、梯度下降和分类原理。"
}
```

说明：
- 当前版本优先支持阶段级资源增强
- 静态资源来自 Domain Pack，作为离线保底
- 动态绑定结果写入 SQLite，不直接回写知识包

## 图谱审核

| 方法 | 路径 | 说明 |
|------|------|------|
| PATCH | /projects/{id}/graph/nodes/{nid} | 审核节点（阶段 6 实现） |
| PATCH | /projects/{id}/graph/edges/{eid} | 审核边（阶段 6 实现） |

## 健康检查与运行时设置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 服务健康状态 |
| GET | /health/config | 获取当前运行时配置状态 |
| PUT | /health/config | 保存 LLM / 搜索运行时配置（运行时生效，并持久化到 SQLite） |
| GET | /health/llm | 检查当前 LLM 配置连通性 |
| GET | /health/search | 检查搜索依赖 readiness |
| GET | /health/readiness | 返回双层演示预检状态与各依赖服务明细 |
| POST | /health/llm-test | 返回已禁用状态，不再发起自定义外部请求 |

**获取配置响应示例：**
```json
{
  "llm_base_url": "https://api.openai.com/v1",
  "llm_model": "gpt-3.5-turbo",
  "llm_api_key_set": false,
  "search_api_key_set": true
}
```

**保存运行时配置请求体：**
```json
{
  "llm_base_url": "https://api.openai.com/v1",
  "llm_model": "gpt-4o-mini",
  "llm_api_key": "sk-xxx",
  "search_api_key": "tvly-xxx"
}
```

**保存运行时配置响应示例：**
```json
{
  "message": "运行时配置已保存",
  "llm_base_url": "https://api.openai.com/v1",
  "llm_model": "gpt-4o-mini",
  "llm_api_key_set": true,
  "search_api_key_set": true
}
```

**空请求响应示例：**
```json
{
  "message": "未提供可更新的运行时配置",
  "llm_api_key_set": false,
  "search_api_key_set": true
}
```

**`GET /health/readiness` 响应要点：**
```json
{
  "status": "degraded",
  "ready": false,
  "core_ready": true,
  "demo_ready": true,
  "enhanced_ready": false,
  "services": {
    "sqlite": {"status": "ok", "ready": true},
    "neo4j": {"status": "ok", "ready": true},
    "graph_sync": {"status": "ok", "ready": true, "reason": "synced", "domain": "machine_learning"},
    "llm": {"status": "skipped", "ready": false, "reason": "LLM_API_KEY not configured"},
    "search": {"status": "skipped", "ready": false, "provider": "tavily", "reason": "搜索服务未配置"}
  }
}
```

说明：
- 后端保存的是运行时配置，并持久化到 SQLite；服务重启后会自动恢复
- 前端会将以下 4 个字段保存到浏览器本地 `localStorage`：`llm_base_url`、`llm_model`、`llm_api_key`、`search_api_key`
- 应用加载时会自动将这 4 个本地保存字段静默回灌到 `PUT /health/config`，用于恢复当前后端进程的运行时配置
- API key 仅通过是否已配置状态对外暴露，不在响应中回显明文
- 支持按需提交 `llm_base_url`、`llm_model`、`llm_api_key`、`search_api_key`
- 未知字段会返回 `422`
- 密钥字段不回显，仅通过 `llm_api_key_set`、`search_api_key_set` 暴露是否已配置
- 清空本地保存只会移除浏览器中的快照，不会主动清空后端当前已生效的运行时配置
- `PUT /health/config` 仅支持覆盖已提供字段，未提交的字段保持原值，不提供清空单个字段的语义
- `POST /health/llm-test` 当前固定返回 `skipped`，不再发起自定义外部连通性请求
- `core_ready` 表示 SQLite + Neo4j + `services.graph_sync` 是否就绪
- `demo_ready` 表示离线答辩主链是否可演示，当前与 `core_ready` 保持一致
- `enhanced_ready` 表示 LLM 与搜索等在线增强能力是否就绪
- 前端为兼容旧联调实例保留 `normalizeReadiness`，若后端仍返回旧结构，会自动补齐 `core_ready/demo_ready/enhanced_ready` 与 `services.graph_sync`
