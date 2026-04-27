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

### 项目创建与目标理解真实流程

当前项目创建不是直接提交 `goal_type/domain` 后立即落库，而是先通过 GoalFrame 与 Coverage Router 形成显式业务状态，再由用户执行分支确认：

```text
goal preview -> branch-specific UI -> create / reconfirm / answer clarification / extension draft
```

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /goal-resolution/preview | 新项目目标理解预览 |
| POST | /goal-resolution/clarifications/{clarification_session_id}/answers | 回答新项目澄清问题 |
| POST | /projects | 使用已确认候选创建项目 |
| POST | /projects/{id}/goal-resolution/preview | 已有项目目标重新确认预览 |
| POST | /projects/{id}/goal-resolution/clarifications/{clarification_session_id}/answers | 回答已有项目澄清问题 |
| PUT | /projects/{id}/goal-resolution | 使用已确认候选更新项目目标 |
| POST | /projects/{id}/goal-resolution/extension-drafts | 为 in-domain uncovered 目标显式创建 overlay 草稿 |

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
- 当前版本为机器学习基础单领域原型，不开放多领域选择入口
- preview 对合法业务状态返回 `200` discriminated union；非法转换、未知枚举、过期/漂移会话返回 `4xx` 且不写入正式路径数据

**目标预览公共字段:**

所有 `200` 预览响应都包含 `result_type`、`coverage_status`、`goal_understanding`、`goal_frame` 与 `pack_hash`。`goal_understanding` 来自 LLM 在线目标理解，表达主领域、机器学习相关性、边界判断、目标概念、置信度与证据；它不直接决定正式节点 ID。`project_graph_hash` 只在项目绑定预览中有意义：新建项目尚未产生项目级图谱快照，因此该字段为 `null`；已有项目目标重确认会返回当前项目图谱快照。`audit_trace` 只在创建了可追溯 session 的响应中返回，`boundary_reject` 等不写入后续会话的分支可为空。

```json
{
  "result_type": "select_candidate",
  "coverage_status": "covered",
  "goal_understanding": {
    "schema_version": "v1",
    "raw_text": "我想系统学习机器学习基础",
    "domain_decision": "in_domain",
    "primary_domain": "machine_learning",
    "ml_relevance": "core",
    "goal_type": "domain",
    "target_concepts": ["机器学习基础"],
    "constraints": {},
    "preferences": {},
    "uncertainties": [],
    "clarification_question": null,
    "confidence": 0.94,
    "evidence": [
      {"span": "机器学习基础", "label": "supported_domain", "reason": "明确属于当前支持的机器学习基础领域"}
    ],
    "prompt_version": "goal-understanding-v1",
    "model": "<llm_model>",
    "warnings": []
  },
  "goal_frame": {
    "schema_version": "v1",
    "raw_text": "我想系统学习机器学习基础",
    "domain": "machine_learning",
    "goal_type": "domain",
    "target_concepts": ["机器学习基础"],
    "target_node_ids": ["ml_c09"],
    "constraints": {},
    "preferences": {},
    "planner_parameters": {
      "path_mode": "standard",
      "theory_weight": 0.5,
      "practice_weight": 0.5,
      "weekly_hours": 10,
      "deadline_weeks": 8,
      "explanation_focus": []
    },
    "uncertainties": [],
    "confidence": 0.9,
    "sources": [{"source": "rules", "evidence": "rules_first_goal_frame", "confidence": 0.9}]
  },
  "pack_hash": "<pack_hash>",
  "project_graph_hash": "<project_graph_hash_or_null>",
  "audit_trace": {
    "trace_type": "goal_resolution",
    "trace_id": "<session_or_trace_id>",
    "pack_hash": "<pack_hash>",
    "project_graph_hash": "<project_graph_hash_or_null>"
  }
}
```

`GoalFrame.target_node_ids` 只是候选提示；正式规划目标只能来自用户确认的候选或显式接受的 partial covered targets。GoalFrame 只能影响受控 planner 参数：`path_mode`、理论/实践权重、时间预算提示与解释关注点，不能覆盖 `confirmed_target_node_ids`，也不能删除硬 `REQUIRES` 前置依赖。

**Coverage discriminated union:**

| `result_type` | `coverage_status` | 关键字段 | 合法下一步 |
|---|---|---|---|
| `select_candidate` | `covered` / `adjacent_domain` | `session_id`、`expires_at`、`recommended_candidate_id`、`candidates[]` | 选择候选后创建项目或更新项目目标 |
| `confirm_partial` | `partial` | `session_id`、`covered_target_node_ids[]`、`missing_concepts[]`、`candidates[]` | 勾选 partial acceptance 后只规划 covered targets |
| `answer_clarification` | `ambiguous` / `cross_domain` | `clarification_session_id`、`turn_count`、`max_turns`、`questions[]` | 调用 clarification answer 端点，直到 resolved 后获得新的 coverage response |
| `review_extension_draft` | `in_domain_uncovered` | `missing_concepts[]`、`draft_entry`、可选 `session_id` | 用户显式请求创建项目级 overlay 草稿 |
| `boundary_reject` | `out_of_domain` / `adjacent_domain` | `reason_code`、`reason_text`、`rewrite_suggestions[]` | 展示边界说明，不调用 planner，不写正式路径 |

**候选选择响应示例:**
```json
{
  "result_type": "select_candidate",
  "coverage_status": "covered",
  "session_id": "<resolution_session_id>",
  "expires_at": "2026-04-24T12:00:00",
  "auto_detected_goal_type": "domain",
  "effective_goal_type": "domain",
  "recommended_candidate_id": "template:domain_ml_full",
  "pack_hash": "<pack_hash>",
  "project_graph_hash": "<project_graph_hash>",
  "goal_frame": {"schema_version": "v1", "raw_text": "我想系统学习机器学习基础"},
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
      "explanation": "推荐学习完整机器学习主干。",
      "warnings": []
    }
  ],
  "warnings": []
}
```

**Partial 响应示例:**
```json
{
  "result_type": "confirm_partial",
  "coverage_status": "partial",
  "session_id": "<resolution_session_id>",
  "expires_at": "2026-04-24T12:00:00",
  "covered_target_node_ids": ["ml_c09"],
  "missing_concepts": ["深度学习"],
  "goal_frame": {"schema_version": "v1", "raw_text": "我想学习机器学习和深度学习"},
  "candidates": []
}
```

**澄清回答请求体:**
```json
{
  "answers": [
    {
      "question_id": "goal_type",
      "selected_option_id": "domain",
      "free_text": null
    }
  ]
}
```

澄清响应为 `ClarificationSessionResponse`：`status` 为 `active|resolved|rejected|expired|stale`，并携带 `turn_count`、`max_turns`、`questions[]`、可选 `goal_frame` 与可选 `coverage_response`。自由文本答案会先解析为受控 delta，不能直接变成 planner 输入。

**创建项目请求体:**
```json
{
  "title": "机器学习入门",
  "goal_text": "我想系统学习机器学习基础",
  "resolution_session_id": "<resolution_session_id>",
  "selected_candidate_id": "template:domain_ml_full",
  "accept_partial": false
}
```

说明：
- 创建或 reconfirm 时必须复用 preview 返回的 `resolution_session_id` 与候选 ID
- `confirm_partial` 分支必须提交 `accept_partial=true`，正式 audit 会记录 `partial_accepted` 与 `missing_concepts`
- 后端会校验目标文本 hash、domain、`pack_hash`、`project_graph_hash`、候选归属与会话状态
- `goal_type` 与 `domain` 仅保留兼容语义，不是公共创建流程的事实源

**目标重新确认请求体:**
```json
{
  "goal_text": "我想系统学习机器学习基础",
  "resolution_session_id": "<resolution_session_id>",
  "selected_candidate_id": "template:domain_ml_full",
  "accept_partial": false
}
```

项目级 reconfirm 会额外校验 `project_id` 与当前项目图谱 hash，避免图谱审核状态变化后复用旧候选。

**Extension draft 创建请求体:**
```json
{
  "resolution_session_id": "<resolution_session_id>"
}
```

该端点只为 `coverage_status=in_domain_uncovered` 的已保存目标解析会话创建项目级 overlay source/session/candidate 草稿；打开 Knowledge 深链本身不会创建草稿、不会改变 review/planning 状态，也不会写入 Domain Pack。

**目标理解相关错误码:**

| HTTP | `error` / `reason_code` | 说明 |
|---|---|---|
| 409 | `STALE_RESOLUTION_SESSION` | 目标解析会话过期、已确认、跨项目或已失效 |
| 409 | `STALE_CLARIFICATION_SESSION` | 澄清会话过期、超过最大轮次、跨项目或已失效 |
| 409 | `PROJECT_GRAPH_DRIFT` | 当前 project graph hash 与会话快照不一致 |
| 409 | `PACK_HASH_DRIFT` | 当前 Domain Pack hash 与会话快照不一致 |
| 422 | `EMPTY_CANDIDATES` | 无法形成任何安全候选，且不属于 partial / uncovered / boundary / clarification 分支 |
| 422 | `INVALID_GOAL_TYPE` / `INVALID_TRANSITION` | 请求字段或状态转换不合法 |

说明：`partial`、`in_domain_uncovered`、`out_of_domain`、`ambiguous` 都是合法业务状态，使用 `200` 的显式分支响应，不再依赖“零候选”错误来表达下一步。

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
| POST | /projects/{id}/replans | 触发传统进度/画像重规划 |
| POST | /projects/{id}/plans/variants/preview | 生成路径变体 TTL 预览，不写正式路径 |
| POST | /projects/{id}/plans/variants/{preview_id}/confirm | 确认一个变体并保存为正式最新路径版本 |
| POST | /projects/{id}/replans/feedback/preview | 解析自然语言反馈并返回 replan 预览，不写正式路径 |
| POST | /projects/{id}/replans/feedback/known-node-drafts/{draft_id}/confirm | 确认 `mark_known_nodes` 候选草稿 |
| POST | /projects/{id}/replans/feedback/{feedback_preview_id}/confirm | 确认反馈预览并保存正式路径版本 |

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

### 路径变体 preview/confirm

**变体预览请求体:**
```json
{
  "path_modes": ["standard", "compressed", "theory_first", "practice_first"]
}
```

`path_modes` 可省略；省略时后端返回当前支持的标准变体集合。预览会保存 TTL session，但不会创建 draft `LearningPath`，也不会改写 latest plan、tracking、resources、explanation cache 或项目目标确认。

**变体预览响应:**
```json
{
  "variant_preview_id": "<variant_preview_id>",
  "project_id": "<project_id>",
  "status": "active",
  "expires_at": "2026-04-24T12:00:00",
  "pack_hash": "<pack_hash>",
  "project_graph_hash": "<project_graph_hash>",
  "profile_hash": "<profile_hash>",
  "parameter_hash": "<parameter_hash>",
  "variants": [
    {
      "variant_id": "standard:<parameter_hash>",
      "path_mode": "standard",
      "budget_summary": {"status": "feasible", "total_hours": 80},
      "included_node_ids": ["ml_a01", "ml_c09"],
      "excluded_node_ids": [],
      "audit_summary": {"path_mode": "standard"}
    }
  ]
}
```

**确认变体请求体:**
```json
{
  "variant_id": "standard:<parameter_hash>"
}
```

确认时后端校验 preview 状态、TTL、项目归属、`pack_hash`、`project_graph_hash`、`profile_hash` 与 `parameter_hash`。同一个有效确认只写入一个正式 `LearningPath` 版本；过期、漂移、已确认或跨项目 preview 会返回 `4xx`，不保存路径。

### 自然语言 feedback replan preview/confirm

**反馈预览请求体:**
```json
{
  "feedback_text": "太长了，希望压缩一点"
}
```

V1 仅支持以下受控意图：`compress_time`、`increase_practice`、`increase_theory`、`adjust_deadline`、`mark_known_nodes`。要求改变目标、跳过硬前置、调整 overlay 可见性、跨领域扩展或低置信度反馈，会返回 clarification/refusal 型预览，不写正式路径。

**反馈预览响应:**
```json
{
  "feedback_preview_id": "<feedback_preview_id>",
  "project_id": "<project_id>",
  "intent_type": "compress_time",
  "confidence": 0.86,
  "controlled_parameters": {"path_mode": "compressed"},
  "diff": {"removed_optional_node_ids": ["ml_r01"]},
  "budget_delta": {"total_hours_delta": -12},
  "blocked_actions": [],
  "requires_confirmation": true,
  "requires_second_confirm": false,
  "variant_preview_id": "<variant_preview_id>",
  "known_node_draft": null,
  "status": "active",
  "expires_at": "2026-04-24T12:00:00",
  "pack_hash": "<pack_hash>",
  "project_graph_hash": "<project_graph_hash>"
}
```

`mark_known_nodes` 会返回 `requires_second_confirm=true` 与 `known_node_draft`：

```json
{
  "draft_id": "<draft_id>",
  "feedback_preview_id": "<feedback_preview_id>",
  "project_id": "<project_id>",
  "node_ids": ["ml_a01"],
  "evidence": [{"source": "feedback_text", "text": "我已经会线性代数"}],
  "status": "draft",
  "expires_at": "2026-04-24T12:00:00"
}
```

调用 known-node draft confirm 后，draft 状态变为 `confirmed`，前端才允许确认 feedback preview。确认 feedback preview 会保存一个正式路径版本并在 audit 中记录 intent、diff、blocked actions、相关 variant 或受控参数；预览本身始终 no-write。

**路径预览相关错误码:**

| HTTP | `error` / `reason_code` | 说明 |
|---|---|---|
| 409 | `STALE_VARIANT_PREVIEW` | 变体预览过期、已确认、跨项目或状态失效 |
| 409 | `STALE_FEEDBACK_PREVIEW` | 反馈预览过期、已确认、跨项目或状态失效 |
| 409 | `PROJECT_GRAPH_DRIFT` | 当前 project graph hash 与 preview 快照不一致 |
| 409 | `PACK_HASH_DRIFT` | 当前 Domain Pack hash 与 preview 快照不一致 |
| 409 | `PROFILE_DRIFT` | 当前画像 hash 与变体 preview 快照不一致 |
| 409 | `PARAMETER_DRIFT` | 当前 planner 参数 hash 与变体 preview 快照不一致 |
| 422 | `UNSUPPORTED_FEEDBACK_INTENT` | 反馈意图不在 V1 白名单或置信度不足 |

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
- 搜索结果可在前端路径页中进一步手动绑定到当前路径中的指定知识点

## 路径资源增强

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /projects/{id}/plans/{path_id}/resources | 获取当前路径的阶段总览资源与知识点资源列表（静态保底 + 已绑定动态资源） |
| POST | /projects/{id}/plans/{path_id}/resources/recommend | 按当前路径知识点自动补充 Tavily 候选资源 |
| POST | /projects/{id}/plans/{path_id}/resources/bind | 手动把搜索结果绑定到指定阶段或知识点 |
| POST | /projects/{id}/resources/bindings | 绑定项目级资源到 project node 或 path stage |

**手动绑定请求体示例：**
```json
{
  "stage_name": "核心掌握",
  "node_id": "ml_c05",
  "title": "逻辑回归核心讲义",
  "url": "https://example.com/logreg",
  "snippet": "覆盖逻辑回归、梯度下降和分类原理。"
}
```

说明：
- 当前版本优先支持知识点级资源增强，阶段资源作为总览保底
- 静态资源来自 Domain Pack，并优先通过 `node_ids` 挂载到知识点
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
