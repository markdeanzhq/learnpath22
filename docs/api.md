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

## 结构化解释

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /projects/{id}/explanation | 获取路径解释（阶段 3 实现） |

## 进度追踪

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /projects/{id}/tracking/events | 记录学习事件 |
| GET | /projects/{id}/tracking/events | 列出所有事件 |
| GET | /projects/{id}/tracking/summary | 获取进度汇总 |

**学习事件类型:** `start` / `complete` / `skip`

## 知识图谱

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /projects/{id}/graph | 获取项目关联的图谱数据 |
| GET | /projects/{id}/graph/subgraph?node_ids=a,b | 获取指定节点的子图 |
| POST | /graph/seed | 同步 Domain Pack 到 Neo4j（全局操作） |

## 搜索

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /projects/{id}/search | 搜索学习资料（阶段 5 实现） |

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
| PUT | /health/config | 保存 LLM / 搜索运行时配置（运行时生效，重启后失效） |
| GET | /health/llm | 检查当前 LLM 配置连通性 |
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

说明：
- 后端保存的是运行时配置，保存后仅对当前后端进程生效，服务重启后失效
- 前端会将以下 4 个字段保存到浏览器本地 `localStorage`：`llm_base_url`、`llm_model`、`llm_api_key`、`search_api_key`
- 应用加载时会自动将这 4 个本地保存字段静默回灌到 `PUT /health/config`，用于恢复当前后端进程的运行时配置
- API key 仅保存在浏览器本地，不由后端持久化
- 支持按需提交 `llm_base_url`、`llm_model`、`llm_api_key`、`search_api_key`
- 未知字段会返回 `422`
- 密钥字段不回显，仅通过 `llm_api_key_set`、`search_api_key_set` 暴露是否已配置
- 清空本地保存只会移除浏览器中的快照，不会主动清空后端当前进程内已生效的运行时配置
- `PUT /health/config` 仅支持覆盖已提供字段，未提交的字段保持原值，不提供清空单个字段的语义
- `POST /health/llm-test` 当前固定返回 `skipped`，不再发起自定义外部连通性请求
