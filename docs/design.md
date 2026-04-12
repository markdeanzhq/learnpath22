# 系统设计文档

## 1. 系统概述

**LearnPath-KG** 是一个基于知识图谱的智能学习路径规划系统，面向机器学习基础学习场景。系统通过知识图谱结构化表示知识点与前置依赖关系，结合学习者画像参数，基于拓扑排序与多因子评分实现可解释的个性化学习路径规划。

## 2. 技术架构

```
┌─────────────────────────────────────────────────────────┐
│                     Nginx (端口 80)                      │
│              SPA 静态文件 + API 反向代理                   │
├─────────────────────────────────────────────────────────┤
│                 Vue3 前端 (Vite 构建)                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ 项目创建  │ │ 知识图谱  │ │ 学习路径  │ │ 进度追踪  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
├─────────────────────────────────────────────────────────┤
│              FastAPI 后端 (端口 8000)                     │
│  ┌──────────────────────────────────────────────────┐   │
│  │ API 层: projects / profiles / plans / tracking    │   │
│  │         graph / replans / health                  │   │
│  ├──────────────────────────────────────────────────┤   │
│  │ 服务层: goal_service / planner_service            │   │
│  │         profile_collector / tracking / replan      │   │
│  ├──────────────────────────────────────────────────┤   │
│  │ 规划引擎: closure → scoring → topology            │   │
│  │           → staging → budget → audit → renderer   │   │
│  ├──────────────────────────────────────────────────┤   │
│  │ 数据层: SQLite (业务状态) + Neo4j (图谱展示)       │   │
│  │         Domain Pack (JSON 知识包)                  │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## 3. 核心模块

### 3.1 Domain Pack (领域知识包)

位置: `backend/app/domain_packs/machine_learning/`

机器学习领域知识包包含 **48 个知识点节点**，每个节点定义：
- 基础属性: id, name, category, group
- 难度/重要性: difficulty_final (1-5), importance_final (1-5)
- 需求画像: req_math, req_coding, req_ml (1-5)
- 偏好权重: theory_weight, practice_weight
- 预估学时: estimated_hours

依赖关系:
- **REQUIRES 边**: 硬前置依赖（必须先学 A 才能学 B）
- **RELATED_TO 边**: 软关联（推荐了解）

### 3.2 目标解析 (Goal Interpreter)

位置: `backend/app/services/goal_service.py`

支持三类学习目标：
| 目标类型 | 关键词示例 | 规划模式 |
|---------|-----------|---------|
| domain (领域型) | "系统学习"、"入门"、"全面" | steady |
| problem (问题型) | "为什么"、"搞懂"、"如何" | efficient |
| concept (概念型) | "理解"、"什么是" | efficient |

### 3.3 规划引擎 (Path Planner)

位置: `backend/app/planner/`

规划流程（7 步纯函数管线）：

```
目标节点 → 前置闭包提取 → 画像补强选择 → 子图提取
→ 拓扑排序(多因子优先级) → 阶段划分 → 时间预算 → 审计日志
```

**关键算法:**

1. **前置闭包** (`closure.py`): BFS 反向遍历 REQUIRES 边，收集所有传递性前置依赖
2. **多因子评分** (`scoring.py`):
   - 差距分 = 0.40×ML差距 + 0.35×数学差距 + 0.25×编程差距
   - 补强分 = 0.45×差距 + 0.20×基础 + 0.15×桥接 + 0.10×主路径 + 0.10×新手
3. **拓扑排序** (`topology.py`): Kahn 算法 + 优先队列，按评分重排同层节点
4. **阶段划分** (`staging.py`): 按 category 分配 → 新手修正 → 三阶段输出
5. **时间预算** (`budget.py`): feasibility_ratio = 可用学时 / 规划学时

### 3.4 学习者画像

画像参数（6 维）：
| 参数 | 范围 | 含义 |
|------|------|------|
| math_level | 1-5 | 数学基础 |
| coding_level | 1-5 | 编程基础 |
| ml_level | 1-5 | 机器学习基础 |
| theory_weight | 0-1 | 理论偏好 |
| weekly_hours | 1-40 | 每周学习时间 |
| deadline_weeks | 1-52 | 截止周数 |

画像采集方式：
- LLM 智能问卷（根据目标动态生成 3-5 题）
- 静态 5 题问卷（LLM 不可用时兜底）

## 4. 数据存储

### SQLite (7 张表)
- LearningProject / LearnerProfile / KnowledgeSource
- LearningPath / PathStage / PathTask / TrackingEvent

### Neo4j
- 纯展示层，启动时由 seed_graph.py 从 Domain Pack 同步
- 48 个 KnowledgeNode + REQUIRES/RELATED_TO 边

## 5. 前端页面

| 页面 | 路由 | 功能 |
|------|------|------|
| 项目创建 | /project | 新建项目 + 画像采集引导流程 |
| 知识图谱 | /knowledge | Cytoscape.js 可视化，力导向/层次布局 |
| 学习路径 | /path | 三阶段时间线 + 规划解释审计日志 |
| 学习进度 | /dashboard | 完成率环形图 + 节点状态标记 |
| 设置 | /settings | 系统设置 |
