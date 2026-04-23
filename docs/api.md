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

**创建项目请求体:**
```json
{
  "title": "机器学习入门",
  "goal_text": "我想系统学习机器学习基础",
  "goal_type": "domain",
  "domain": "machine_learning"
}
```

说明：
- 当前版本为单领域原型，`domain` 仅支持 `machine_learning`
- 传入其他领域值会在请求校验阶段返回 `422`

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

## 路径规划

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /projects/{id}/plans | 生成学习路径 |
| GET | /projects/{id}/plans/latest | 获取最新路径 |
| POST | /projects/{id}/replans | 触发重规划 |

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

说明：
- `graph/entities` 只返回扩展实体展示数据，不会触发图谱重同步
- 前端 Knowledge 页使用该接口展示 `Stage` / `Resource` 只读信息
- Path / Dashboard 的“在图谱中定位”会跳转到 Knowledge，并由图谱画布聚焦对应 `nodeId`

## 搜索

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /projects/{id}/search | 搜索学习资料（在线增强） |

说明：
- 搜索能力服务于学习资料补充，不参与路径主链正确性判定
- 搜索结果可在前端路径页中进一步手动绑定到指定阶段

## 路径资源增强

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /projects/{id}/plans/{path_id}/resources | 获取当前路径的阶段资源列表（静态保底 + 已绑定动态资源） |
| POST | /projects/{id}/plans/{path_id}/resources/recommend | 按阶段自动补充 Tavily 候选资源 |
| POST | /projects/{id}/plans/{path_id}/resources/bind | 手动把搜索结果绑定到指定阶段或节点 |

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
