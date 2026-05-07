# 测试与验证记录（毕业论文 v3 口径）

- 记录时间：`2026-05-04T07:17:32Z`
- 验证对象：`thesis-validation-v1`
- 后端基线：`http://127.0.0.1:8010/api/v1`
- 证据文件：
  - `backend/artifacts/thesis_validation/latest.json`
  - `backend/artifacts/thesis_validation/paper_metrics.json`
  - `backend/artifacts/thesis_validation/report.md`

## 1. 命令记录

### 1.1 启动本地验证后端

- 命令：`PYTHONPATH="E:/dailyfile/myfiles/project_all/learnpath322/backend" "E:/dailyfile/myfiles/project_all/learnpath322/backend/.venv/Scripts/python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8010`
- 状态：`GET /api/v1/health` 返回 `200`

### 1.2 刷新论文验证证据

- 命令：`PYTHONPATH="E:/dailyfile/myfiles/project_all/learnpath322/backend" "E:/dailyfile/myfiles/project_all/learnpath322/backend/.venv/Scripts/python.exe" "E:/dailyfile/myfiles/project_all/learnpath322/backend/scripts/generate_thesis_validation_evidence.py" --base-url http://127.0.0.1:8010/api/v1 --runtime-mode auto`
- 结果：`9/9 scenarios passed`
- 引用就绪：`true`

## 2. 当前验证口径

- `resolved_runtime_mode = offline`
- `uses_online_dependencies = false`
- `readiness_status = degraded`
- `readiness_ready = false`
- `core_ready = true`
- `demo_ready = true`
- `enhanced_ready = false`
- `services.graph_sync.status = ok`
- `services.graph_sync.reason = synced`
- `services.llm.status = skipped`
- `services.llm.reason = LLM_API_KEY not configured`
- `services.search.status = skipped`
- `services.search.reason = 搜索服务未配置`
- `tracking_summary_scope = latest_plan`

## 3. 论文引用级指标

- `scenario_count = 9`
- `successful_scenarios = 9`
- `failed_scenarios = 0`
- `all_scenarios_passed = true`
- `satisfied_required_edges = 303`
- `total_required_edges = 303`
- `dependency_satisfaction_ratio = 1.0`
- `average_stage_count = 3.0`
- `average_total_stage_hours = 75.11`

## 4. 场景明细

| 场景 ID | 节点数 | 阶段数 | 总时长 | 依赖满足率 |
|---|---:|---:|---:|---:|
| `scenario_domain_beginner` | 47 | 3 | 125 | 100.0% |
| `scenario_domain_intermediate` | 47 | 3 | 125 | 100.0% |
| `scenario_domain_focused` | 47 | 3 | 125 | 100.0% |
| `scenario_problem_beginner` | 24 | 3 | 64 | 100.0% |
| `scenario_problem_intermediate` | 20 | 3 | 54 | 100.0% |
| `scenario_problem_focused` | 20 | 3 | 54 | 100.0% |
| `scenario_concept_beginner` | 20 | 3 | 53 | 100.0% |
| `scenario_concept_intermediate` | 14 | 3 | 38 | 100.0% |
| `scenario_concept_focused` | 14 | 3 | 38 | 100.0% |

## 5. 证据边界

- 本次验证未使用在线 LLM 与搜索服务，论文结论只支撑本地领域知识包、图谱同步、规则规划、解释、进度追踪和重规划主链路。
- LLM 目标理解、解释润色、扩展候选抽取和在线搜索应在论文中表述为可选增强能力，不作为本次 M1-M5 和 9 场景通过结论的依据。
- 验证脚本已兼容当前 API 在 LLM 未配置时的受控澄清流程，会使用固定目标文本完成澄清后再创建项目与路径。
