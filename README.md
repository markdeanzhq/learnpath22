# LearnPath-KG

> 基于知识图谱的智能学习路径规划系统
> 
> 面向“机器学习基础”学习场景的本科毕业设计原型，强调**可解释、可验证、可演示**。

## 1. 项目简介

LearnPath-KG 是一个围绕“如何为学习者生成个性化学习路径”而设计的原型系统。

系统以知识图谱为核心载体，将知识点、前置依赖关系、学习者画像、时间预算和学习进度统一纳入规划流程中，最终输出一个**结构化、可解释、可追踪、可重规划**的学习路径。

与纯大模型推荐不同，本项目的核心思路是：

- 用**知识图谱**表达知识结构与前置关系
- 用**规则 + 图算法**保证路径顺序合理
- 用**学习者画像**实现个性化排序
- 用**解释模块**提升结果透明度
- 用**进度追踪与重规划**形成闭环

## 2. 课题定位

本项目对应论文方向：

**《基于知识图谱的智能学习路径规划系统设计与实现》**

项目首版聚焦于“机器学习基础”领域，目标不是构建通用教育平台，而是完成一个可以稳定运行、具备研究价值、适合毕业答辩展示的系统原型。

## 3. 核心目标

本系统主要解决以下问题：

1. 学习目标如何映射为结构化知识点集合
2. 知识点之间的前置依赖如何约束学习顺序
3. 不同基础、偏好、时间预算的学习者如何得到差异化路径
4. 系统如何解释“为什么这样排”
5. 学习进度变化后，系统如何进行重规划

## 4. 功能亮点

### 4.1 学习项目管理
- 创建学习项目
- 输入学习目标文本
- 支持领域型 / 概念型 / 问题型目标

### 4.2 学习者画像建模
- 数学基础
- 编程基础
- 机器学习基础
- 理论偏好 / 实践偏好
- 每周可投入时间
- 学习周期预算

### 4.3 知识图谱驱动的路径生成
- 基于知识点节点与依赖边构建学习图
- 自动提取目标相关前置闭包
- 使用拓扑排序生成满足依赖约束的顺序
- 结合画像参数进行多因子重排
- 输出阶段化学习路径

### 4.4 路径解释
系统支持对路径结果进行结构化解释，包括：
- 节点为什么被纳入路径
- 排序为什么这样安排
- 阶段为什么这样划分
- 时间预算是否可行
- 依赖链如何影响学习顺序

### 4.5 学习进度追踪
- 记录 `start` / `complete` / `skip` 事件
- 汇总完成率、进行中数量、跳过数量
- 为后续重规划提供依据

### 4.6 双模式重规划
- `progress_aware`：基于当前进度，仅重算剩余路径
- `profile_update`：基于最新画像参数重新计算完整路径，并返回差异

### 4.7 学习资料搜索
- 接入 Tavily 搜索服务
- 可围绕当前项目搜索相关学习资料
- 前端在未配置搜索服务时提供明确引导

### 4.8 前端运行时设置
设置页支持直接录入以下配置：
- `LLM_BASE_URL`
- `LLM_MODEL`
- `LLM_API_KEY`
- `SEARCH_API_KEY`

保存后立即生效，适合答辩演示场景中的快速切换与联调。

## 5. 技术路线

### 前端
- Vue 3
- Vite
- TypeScript
- Element Plus
- Pinia
- Cytoscape.js

### 后端
- FastAPI
- SQLAlchemy Async
- Pydantic v2
- httpx

### 数据与算法
- SQLite：业务数据存储
- Neo4j：知识图谱存储
- NetworkX：图算法与路径规划逻辑

## 6. 系统架构概览

```text
前端 Vue 页面
   ↓
FastAPI 接口层
   ↓
业务服务层
   ├─ 项目管理
   ├─ 学习者画像
   ├─ 路径规划
   ├─ 解释服务
   ├─ 重规划
   ├─ 搜索服务
   └─ 进度追踪
   ↓
数据层
   ├─ SQLite
   └─ Neo4j
```

## 7. 项目结构

```text
learnpath322/
├─ backend/                 # FastAPI 后端
│  ├─ app/
│  │  ├─ api/               # API 路由
│  │  ├─ core/              # 配置、异常、基础设施
│  │  ├─ domain_packs/      # 领域知识包
│  │  ├─ planner/           # 路径规划核心逻辑
│  │  ├─ repositories/      # 数据访问层
│  │  ├─ schemas/           # Pydantic 模型
│  │  └─ services/          # 业务服务
│  └─ tests/                # 后端测试
├─ frontend/                # Vue 前端
│  └─ src/
├─ docs/                    # 文档
├─ docker-compose.yml       # 容器编排
└─ README.md
```

## 8. 运行环境

- Python 3.12
- Node.js 18+
- npm 9+
- Neo4j 5+
- Docker / Docker Compose（可选）

## 9. 环境变量

后端支持从 `backend/.env` 读取配置：

```env
SQLITE_URL=sqlite+aiosqlite:///./learnpath.db
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=learnpath
LLM_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-3.5-turbo
SEARCH_API_KEY=
CORS_ORIGINS=["http://localhost:5173"]
```

说明：
- `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`、`SEARCH_API_KEY` 可在 `.env` 中预置
- 也可在前端“设置”页运行时录入或覆盖
- 运行时配置仅在当前后端进程生命周期内有效，重启后失效

## 10. 本地部署方式

### 10.1 启动后端

```bash
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 10.2 启动前端

```bash
cd frontend
npm install
npm run dev
```

默认访问地址：
- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`
- Swagger：`http://localhost:8000/docs`

## 11. Docker 部署方式

如本地已准备好镜像与容器环境，可直接执行：

```bash
docker compose up --build
```

启动后建议检查：
- `GET /api/v1/health` 返回 `ok`
- 前端页面可正常访问
- 设置页可保存运行时配置
- 搜索页在配置 `SEARCH_API_KEY` 后可正常搜索

## 12. 演示流程建议

答辩时可按以下顺序演示：

### 第一步：创建学习项目
输入一个学习目标，例如：
- “我想系统学习机器学习基础”
- “我想搞懂逻辑回归为什么能做分类”

### 第二步：提交学习者画像
填写基础水平、理论/实践偏好、时间预算。

### 第三步：生成学习路径
展示系统输出的阶段化路径、总学时和预算状态。

### 第四步：查看解释
展示节点解释、排序解释、阶段解释和预算解释，突出系统可解释性。

### 第五步：记录学习进度
模拟 `start` / `complete` / `skip` 事件，展示系统如何汇总学习状态。

### 第六步：执行重规划
分别演示：
- 进度驱动重规划
- 画像更新驱动重规划

### 第七步：资料搜索
在设置页填入 `SEARCH_API_KEY` 后，前往搜索页检索学习资料。

## 13. 关键接口

详见 `docs/api.md`，常用接口包括：

- `POST /api/v1/projects`
- `GET /api/v1/projects`
- `POST /api/v1/projects/{id}/profiles`
- `POST /api/v1/projects/{id}/plans`
- `GET /api/v1/projects/{id}/plans/latest`
- `GET /api/v1/projects/{id}/explanation`
- `POST /api/v1/projects/{id}/tracking/events`
- `GET /api/v1/projects/{id}/tracking/summary`
- `POST /api/v1/projects/{id}/replans`
- `POST /api/v1/projects/{id}/search`
- `GET /api/v1/health/config`
- `PUT /api/v1/health/config`
- `GET /api/v1/health/llm`

## 14. 测试与验证

### 后端测试

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/test_health_api.py tests/test_search_service.py tests/test_api_plans.py tests/test_api_tracking.py tests/test_replan.py tests/test_e2e.py
```

### 前端构建验证

```bash
cd frontend
npm run build
```

当前已验证结果：
- 后端回归测试：`42 passed`
- 前端生产构建：通过

## 15. 当前版本说明

- 当前版本以**毕业设计演示原型**为定位
- 首版重点是“机器学习基础”领域
- 设置页中的 LLM 与搜索配置采用**运行时覆盖**，不写回 `.env`
- `GET /api/v1/health/llm` 可用于检查当前 LLM 配置连通性
- 自定义 `POST /api/v1/health/llm-test` 已禁用
- 前端构建存在大 chunk warning，但不影响当前运行与答辩演示

## 16. 项目价值

本项目的价值主要体现在：

1. 将知识图谱方法引入学习路径规划问题
2. 将“个性化推荐”与“可解释规则系统”结合
3. 构建了从目标输入到进度反馈的闭环流程
4. 为毕业论文提供了可运行、可验证、可展示的系统实现基础

## 17. 后续可扩展方向

- 扩展更多学科领域的 Domain Pack
- 增强知识点抽取与自动建图能力
- 增加资源质量评估与资源排序
- 增加图谱审核可视化交互能力
- 增强重规划策略与差异展示能力

## 18. 许可证

如需对外发布，请补充项目许可证说明。
