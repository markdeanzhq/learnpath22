# 部署文档

## 前置要求

- Docker & Docker Compose (v2+)
- 磁盘空间: ~2GB (镜像 + Neo4j 数据)

> 当前部署目标是“机器学习基础”单领域毕业设计原型。核心演示链路依赖本地知识包、SQLite、Neo4j 与 `graph_sync` 同步状态；LLM 与在线搜索属于增强能力，可按答辩现场条件选择是否启用。

## 一键部署

```bash
# 1. 克隆项目
git clone <repo-url> learnpath-kg
cd learnpath-kg

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，修改 NEO4J_PASSWORD

# 3. 启动
docker compose up -d --build

# 4. 等待服务就绪（约 30-60 秒）
docker compose ps

# 5. 同步知识图谱到 Neo4j
curl -X POST http://localhost:8000/api/v1/graph/seed

# 6. 检查演示预检状态
curl http://localhost:8000/api/v1/health/readiness
```

或使用初始化脚本：
```bash
bash scripts/init.sh
```

## 访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端 | http://localhost | 系统主页 |
| API Swagger | http://localhost:8000/docs | 接口文档 |
| Neo4j Browser | http://localhost:7474 | 图数据库管理 |

## 服务架构

```
┌────────────┐    ┌────────────┐    ┌────────────┐
│  frontend  │───▶│    api     │───▶│   neo4j    │
│  (Nginx)   │    │ (FastAPI)  │    │ (Neo4j 5)  │
│   :80      │    │   :8000    │    │  :7474/7687│
└────────────┘    └────────────┘    └────────────┘
                       │
                  ┌────────────┐
                  │   SQLite   │
                  │ (api_data) │
                  └────────────┘
```

## 数据持久化

| 卷名 | 挂载路径 | 内容 |
|------|---------|------|
| api_data | /app/data | SQLite 数据库 |
| neo4j_data | /data | Neo4j 图数据 |

## 常用命令

```bash
# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f api
docker compose logs -f frontend

# 重启单个服务
docker compose restart api

# 停止所有服务
docker compose down

# 停止并清除数据
docker compose down -v

# 重新构建
docker compose up -d --build
```

## 离线部署（答辩场景）

如果答辩现场无网络：

- 可不配置 `LLM_API_KEY` 与 `SEARCH_API_KEY`
- 核心路径规划、图谱查看、进度追踪、重规划演示仍可进行
- 需确保 `graph/seed` 已执行，且 `GET /health/readiness` 中 `core_ready=true`、`demo_ready=true`
- 此时允许 `enhanced_ready=false`，表示在线增强未启用，但不影响离线主链答辩
- 建议提前完成图谱 seed，并准备好固定演示项目数据

```bash
# 预先在有网环境导出镜像
docker compose build
docker save learnpath-api learnpath-frontend neo4j:5-community | gzip > learnpath-images.tar.gz

# 答辩机器加载镜像
docker load < learnpath-images.tar.gz
docker compose up -d
```

## 环境变量

| 变量 | 必须 | 默认值 | 说明 |
|------|------|--------|------|
| NEO4J_USER | 否 | neo4j | Neo4j 用户名 |
| NEO4J_PASSWORD | 是 | - | Neo4j 密码 |
| LLM_API_KEY | 否 | 空 | LLM API 密钥（画像采集增强，未配置时可走静态问卷） |
| SEARCH_API_KEY | 否 | 空 | Tavily 搜索 API 密钥（在线搜索增强，未配置时不影响主规划链路） |
| CORS_ORIGINS | 否 | localhost | 允许的跨域来源 |

部署验收建议：
- `GET /api/v1/health` 用于确认环境基线
- `GET /api/v1/health/readiness` 用于确认双层演示预检状态
- 重点检查 `services.graph_sync` 是否为 `ok/synced`

## 典型演示场景

### 场景 A: 领域型
> "我想系统学习机器学习基础"

预期输出：完整三阶段路径（约 47 个知识点、125 小时），基础准备 → 核心掌握 → 应用突破。

说明：当前系统仅支持 `machine_learning` 单领域项目创建，答辩时建议优先演示该场景作为主案例。领域型目标默认覆盖机器学习基础主干，不建议把节点数量差异作为主要个性化证据。

### 场景 B: 问题型
> "我想搞懂逻辑回归为什么能做分类"

预期输出：收缩路径，聚焦逻辑回归解释链及其前置依赖（约 20-24 个知识点、54-64 小时，随画像与路径模式变化）。

适合配合节点/边审核与重规划功能演示“removed 过滤”对后续路径的影响。 

### 场景 C: 概念型
> "理解梯度下降"

预期输出：概念收缩路径，围绕梯度下降及必要前置知识展开（约 14-20 个知识点、38-53 小时，随画像与路径模式变化）。
