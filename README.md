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

项目首版聚焦于“机器学习基础”领域，当前版本在接口层与知识包层均限定为 `machine_learning` 单领域；目标不是构建通用教育平台，而是完成一个可以稳定运行、具备研究价值、适合毕业答辩展示的系统原型。

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
- 支持 `LLM 在线问卷 + 静态问卷兜底`

### 4.3 知识图谱驱动的路径生成
- 基于知识点节点与依赖边构建学习图
- 自动提取目标相关前置闭包
- 使用拓扑排序生成满足依赖约束的顺序
- 结合画像参数进行多因子重排
- 输出阶段化学习路径
- 支持 domain / project 两种图谱视图，提供节点/边审核与 `removed` 过滤；`Stage` / `Resource` 当前仅作为只读展示实体

### 4.4 路径解释
系统支持对路径结果进行结构化解释，包括：
- 节点为什么被纳入路径
- 排序为什么这样安排
- 阶段为什么这样划分
- 时间预算是否可行
- 依赖链如何影响学习顺序

当 `LLM_EXPLANATION_POLISH=true` 且已配置 `LLM_API_KEY` 时，可在 Path 页解释面板开启 "AI 润色" 开关，调用 `GET /api/v1/projects/{id}/explanation?polish=true` 获取 LLM 自然语言润色后的解释；规则原文保留在 `raw_reason` / `raw_rationale` 字段中可对照查看。润色失败（超时、异常、长度溢出）会自动回落到原文，不影响主链演示。

### 4.5 学习进度追踪
- 记录 `start` / `complete` / `skip` 事件
- `GET /api/v1/projects/{id}/tracking/summary` 按 `latest plan` 口径汇总完成率、进行中数量、跳过数量
- 已被最新计划移除的节点不再计入当前 `total_nodes`
- Path / Dashboard 页面支持“在图谱中定位”，可直接跳转到 Knowledge 并聚焦目标节点

### 4.6 双模式重规划
- `progress_aware`：基于当前进度，仅重算剩余路径
- `profile_update`：基于最新画像参数重新计算完整路径，并返回差异

### 4.7 学习资料搜索与资源增强
- 接入 Tavily 搜索服务
- 可围绕当前项目在线搜索相关学习资料并展示结果
- 前端在未配置搜索服务时提供明确引导
- 提供独立搜索页，并在路径页内嵌搜索入口
- 新增“知识点优先”的路径资源补充：静态资源按知识点挂载，Tavily 候选按路径节点自动补充，搜索结果可手动绑定到指定知识点
- 当前资源机制采用“静态资源保底 + 在线搜索增强”双层结构
- 在线搜索结果不会直接回写 Domain Pack，也不是路径规划主链的必经输入

### 4.8 前端运行时设置
设置页支持直接录入以下配置：
- `LLM_BASE_URL`
- `LLM_MODEL`
- `LLM_API_KEY`
- `SEARCH_API_KEY`

保存后立即生效，适合答辩演示场景中的快速切换与联调；运行时配置会持久化到 SQLite，后端重启后自动装载。

### 4.9 健康检查与环境指纹
- `GET /api/v1/health` 返回项目状态、版本和非敏感环境指纹
- `GET /api/v1/health/search` 返回搜索依赖独立 readiness 状态
- `GET /api/v1/health/readiness` 返回分层演示预检语义：`core_ready`、`demo_ready`、`enhanced_ready`
- `services` 中包含 `sqlite`、`neo4j`、`graph_sync`、`llm`、`search`
- 当前答辩口径中：`core_ready/demo_ready` 表示规则图算法主链是否可演示，`enhanced_ready` 表示 LLM / 搜索增强能力是否就绪
- 前端为兼容旧联调实例，保留 `normalizeReadiness` 归一化逻辑；若后端仍返回旧结构，前端会补齐分层字段与 `services.graph_sync`
- 环境指纹包含 Python 3.12 基线、实际运行版本、运行时配置作用域，以及 LLM / 搜索配置是否就绪

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
- Neo4j：图谱展示与审核视图
- Domain Pack JSON：单领域知识事实源
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

- Python 3.12（README、`backend/Dockerfile` 与 `GET /api/v1/health` 环境基线保持一致）
- Node.js 18+
- npm 9+
- Neo4j 5+
- Docker / Docker Compose（可选）

环境基线说明：
- 本项目当前交付物是“机器学习基础”单领域本科毕业设计原型，不承诺多领域平台能力
- `GET /api/v1/health` 会输出非敏感环境指纹，便于答辩截图、验证记录和后续论文证据脚本复用
- `GET /api/v1/health/readiness` 用于答辩前预检分层依赖状态：`core_ready/demo_ready/enhanced_ready`
- `services.graph_sync` 直接反映 Domain Pack 与 Neo4j 图谱同步状态，是当前规则图算法主链的一部分

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
LLM_EXPLANATION_POLISH=false
SEARCH_API_KEY=
CORS_ORIGINS=["http://localhost:5173"]
```

说明：
- `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`、`SEARCH_API_KEY` 可在 `.env` 中预置
- 也可在前端“设置”页运行时录入或覆盖
- 运行时配置会持久化到 SQLite，应用重启后仍会自动装载
- `GET /api/v1/health` 会同步返回 `runtime_settings_scope=sqlite-persisted` 等环境指纹字段，作为当前答辩环境基线

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
- `GET /api/v1/health` 返回 `ok`，并包含 Python 基线与配置状态等环境指纹字段
- 前端页面可正常访问
- 设置页可保存运行时配置
- 搜索页在配置 `SEARCH_API_KEY` 后可正常搜索

## 12. 演示流程建议

答辩建议按“先证明主链正确，再展示增强能力边界”的顺序执行。

### 12.1 预检：确认演示环境

1. 打开前端 `http://localhost:5173`，进入“设置”页。
2. 检查 `/health/readiness`：
   - `demo_ready=true`：SQLite、Neo4j、graph_sync 与规则图算法主链可演示。
   - `enhanced_ready=true`：LLM 与搜索增强能力可演示。
3. 如需完整增强演示，填入并测试 `LLM_API_KEY` 与 `SEARCH_API_KEY`。

### 12.2 基础主线：机器学习基础路径

1. 在“项目创建”页输入目标：`我想系统学习机器学习基础`。
2. 选择或提交一组基础薄弱、理论优先、12 周周期的学习者画像。
3. 生成学习路径，重点展示：
   - 三阶段学习路径；
   - 总学时与预算状态；
   - 节点解释、排序解释、阶段解释和预算解释；
   - Path 页面跳转 Knowledge 并定位路径节点。
4. 建议讲解口径：正式路径来自 Domain Pack / Project Graph Snapshot、前置闭包、拓扑排序与规则评分，LLM 不直接决定路径正确性。

### 12.3 对照主线：问题型目标收敛

1. 新建或切换项目，输入目标：`我想搞懂逻辑回归为什么能做分类`。
2. 使用偏实践画像或紧周期画像生成路径。
3. 对比领域型目标，说明问题型目标只保留与分类原理直接相关的前置链，不会为了覆盖率拉入整张图。

### 12.4 扩展草稿：随机森林目标边界

1. 输入目标：`我想学习随机森林`。
2. 展示目标解析结果中的 `review_extension_draft` / `in_domain_uncovered` 语义。
3. 创建随机森林扩展审核项目或扩展草稿，进入 Knowledge 查看候选 source、node、edge、resource。
4. 在候选处理队列中展示“需修复 / 待复核 / 待审核 / 已确认”诊断，优先打开首个可修复候选。
5. 强调：随机森林尚不属于当前 Domain Pack 正式事实源，草稿不会直接写正式图谱或正式路径，必须经过校验、人工审核与 `planning_enabled` 开关。

### 12.5 增强主线：资料到 overlay 的受控链路

1. 在 Search 页保存一条机器学习资料，或在 Knowledge 页粘贴一段资料文本。
2. 在 Knowledge 中生成 “AI 抽取预览”，检查节点、关系、资源候选数量。
3. 使用预览 payload 创建 extraction session，展示字段校验、重复检测、DAG 校验与 warning。
4. 对已通过机器校验的候选可批量确认；对已确认但未开启规划的候选可批量纳入 `planning_enabled`。
5. Knowledge 预检面板出现“查看路径对比”入口后跳转到 Path 的“基础 / 增强图谱路径对比”，由用户显式点击生成对比预览。
6. 与基础路径对比：新增内容只来自已确认且开启规划的 Project Overlay，未确认候选不会进入 planner-visible graph。

### 12.6 闭环演示：资源、进度与重规划

1. 在 Path 页执行“自动补充知识点资源”，或把搜索结果手动绑定到阶段/资源位。
2. 在 Dashboard 模拟 `start` / `complete` / `skip` 学习事件。
3. 分别触发：
   - `progress_aware`：保留已完成节点，仅重算剩余路径；
   - `profile_update`：画像变化后重新生成完整路径。
4. 最后回到 Knowledge，用 Path / Dashboard 的“在图谱中定位”证明路径、进度与图谱视图联动。

## 13. 关键接口

详见 `docs/api.md`，常用接口包括：

- `POST /api/v1/projects`
- `GET /api/v1/projects`
- `POST /api/v1/projects/{id}/profiles`
- `POST /api/v1/projects/{id}/collector/questions`
- `POST /api/v1/projects/{id}/collector/submit`
- `POST /api/v1/projects/{id}/plans`
- `GET /api/v1/projects/{id}/plans/latest`
- `GET /api/v1/projects/{id}/explanation`
- `GET /api/v1/projects/{id}/graph`
- `PATCH /api/v1/projects/{id}/graph/nodes/{node_id}`
- `PATCH /api/v1/projects/{id}/graph/edges/{edge_id}`
- `POST /api/v1/projects/{id}/tracking/events`
- `GET /api/v1/projects/{id}/tracking/summary`
- `POST /api/v1/projects/{id}/replans`
- `POST /api/v1/projects/{id}/search`
- `GET /api/v1/projects/{id}/plans/{path_id}/resources`
- `POST /api/v1/projects/{id}/plans/{path_id}/resources/recommend`
- `POST /api/v1/projects/{id}/plans/{path_id}/resources/bind`
- `GET /api/v1/health`
- `GET /api/v1/health/config`
- `PUT /api/v1/health/config`
- `GET /api/v1/health/llm`

## 14. 测试与验证

### 后端测试

```bash
cd backend
.venv/Scripts/python.exe -m pytest tests/test_health_api.py tests/test_search_service.py tests/test_api_plans.py tests/test_api_tracking.py tests/test_replan.py tests/test_e2e.py
```

### 论文验证指标评估

```bash
cd backend
.venv/Scripts/python.exe -m scripts.evaluate --goal "我想系统学习机器学习基础" --profile beginner --out artifacts/eval_reports
.venv/Scripts/python.exe -m scripts.ablation --profile beginner --out artifacts/ablation_reports
```

前者输出 5 项量化指标（依赖满足率 / DAG 检查 / Kendall τ 教材对比 / 类型覆盖矩阵 / 阶段闭包完整率），后者输出 3 组权重 × 3 个典型目标的消融矩阵。报表写入 `reports/{timestamp}/`，可直接贴入论文第 7 章。教材基线见 `backend/scripts/baselines/zhouzhihua_index.json`。

### 前端构建验证

```bash
cd frontend
npm run build
```

当前已验证结果：
- 后端回归测试：`226 passed`（含论文验证指标评估 11 项 + 权重消融 6 项 + 解释润色 5 项）
- 前端生产构建：通过（main chunk 472.83 kB / gzip 152.12 kB，与基线一致）

### 论文交付物

- `document/毕业论文_v2.md`：论文 v2 Markdown 稿（8 章 + 参考文献 + 致谢 + 附录 A/B，约 1400 行）
- `document/毕业论文_v2.docx`：pandoc 转换产出，已套用 `本科毕业论文模板样例.docx` 样式
- `document/thesis_assets/final_reports/{G1,G2,G3}/`：论文第 7 章量化指标原始报表
- `document/thesis_assets/final_ablation/`：论文第 7 章权重消融矩阵与 Kendall τ 表
- `document/template_notes.md`：论文模板样式提取说明与 pandoc 转换约定

## 15. 当前版本说明

- 当前版本以**毕业设计演示原型**为定位
- 当前交付范围限定为**机器学习基础单领域原型**，创建项目时 `domain` 仅支持 `machine_learning`
- 设置页中的 LLM 与搜索配置采用**运行时覆盖**，并持久化到 SQLite，便于答辩现场快速恢复演示环境
- `GET /api/v1/health` 返回非敏感环境指纹，可复用于答辩截图与后续验证脚本
- `GET /api/v1/health/search` 与 `GET /api/v1/health/readiness` 可用于答辩前依赖预检
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

- 将 Domain Pack 机制扩展到数据结构、高等数学、操作系统等其他结构化课程
- 引入基于 LLM 的关系候选抽取，配合人工审核降低多领域扩展维护成本
- 增加资源质量评估与资源排序（基于点击率、停留时间、学习事件反馈）
- 增强节点/边审核交互与审核依据展示
- 在校内小班开展受控试点，收集真实学习者画像与路径使用数据以进一步校准评分权重

## 18. 许可证

如需对外发布，请补充项目许可证说明。
