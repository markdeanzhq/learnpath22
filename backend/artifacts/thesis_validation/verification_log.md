# 测试与验证记录（5.5）

- 变更：`thesis-alignment-review`
- 记录时间：`2026-04-15T18:29:11Z`
- 当前代码验证基线：
  - 后端：`http://127.0.0.1:8010/api/v1`
  - 前端：`http://127.0.0.1:5173`
- 对照实例（仅用于解释兼容层）：
  - 旧后端：`http://127.0.0.1:8000/api/v1`
  - 旧静态前端：`http://127.0.0.1:8080`

## 1. 命令记录

### 1.1 定向测试
- 命令：`cd backend && .venv/Scripts/python.exe -m pytest tests/test_generate_thesis_validation_evidence.py`
- 结果：`20 passed`

### 1.2 论文证据刷新
- 命令：`cd backend && .venv/Scripts/python.exe scripts/generate_thesis_validation_evidence.py --base-url http://127.0.0.1:8010/api/v1 --runtime-mode auto`
- 输出文件：
  - `backend/artifacts/thesis_validation/latest.json`
  - `backend/artifacts/thesis_validation/paper_metrics.json`
- 结果：`9/9 scenarios passed`

## 2. 当前代码实例与旧实例差异

### 2.1 当前代码后端（8010）
- `GET /health/readiness` 直接返回双层预检结构：
  - `status=degraded`
  - `ready=false`
  - `core_ready=true`
  - `demo_ready=true`
  - `enhanced_ready=false`
- `services.graph_sync.status=ok`
- `services.graph_sync.reason=synced`
- `validation_contract.readiness_contract.mode=native_dual_layer`
- `validation_contract.tracking_contract.summary_scope=latest_plan`

### 2.2 旧联调后端（8000）
- `GET /health/readiness` 仍返回旧聚合结构，只包含 `status`、`ready` 与 `services`
- 不含 `core_ready/demo_ready/enhanced_ready`
- 不含 `services.graph_sync`
- tracking summary 也不是本轮要求的 `latest plan` 口径
- 因此本轮结构化证据最终以 `8010` 工作区实例为准

### 2.3 前端实例差异
- `5173` 为 Vite dev server，加载当前前端源码
- `8080` 为旧静态构建，本轮对照时发现其 Path / Dashboard 缺少“在图谱中定位”按钮
- 因此前端真实验收以 `5173` 为准

## 3. 结构化证据复核

### 3.1 原始证据 `latest.json`
- `base_url = http://127.0.0.1:8010/api/v1`
- `requested_runtime_mode = auto`
- `resolved_runtime_mode = offline`
- `uses_online_dependencies = false`
- `readiness_status = degraded`
- `readiness_ready = false`
- `core_ready = true`
- `demo_ready = true`
- `enhanced_ready = false`
- `readiness_contract.mode = native_dual_layer`
- `readiness_contract.normalized = false`
- `tracking_contract.summary_scope = latest_plan`
- `scenario_count = 9`
- `successful_scenarios = 9`
- `failed_scenarios = 0`
- `all_scenarios_passed = true`

### 3.2 论文引用级指标 `paper_metrics.json`
- `citation_ready = true`
- `dependency_satisfaction_ratio = 1.0`
- `satisfied_required_edges = 306`
- `total_required_edges = 306`
- `average_stage_count = 3.0`
- `average_total_stage_hours = 61.78`
- `environment_state.readiness_contract_mode = native_dual_layer`
- `environment_state.readiness_contract_normalized = false`
- `environment_state.tracking_summary_scope = latest_plan`
- `environment_state.service_statuses.graph_sync.status = ok`
- `environment_state.service_statuses.graph_sync.reason = synced`

## 4. 真实浏览器复核

- Path 页存在“在图谱中定位”按钮
- Dashboard 页存在“在图谱中定位”按钮
- 点击后均会跳转到 `Knowledge` 页，并通过 `nodeId` 路由参数聚焦对应节点
- 本轮样本节点为 `导数与偏导`
- 该链路证明 Path / Dashboard → Knowledge 的节点定位已可直接演示

## 5. 结论

- [x] `backend/tests/test_generate_thesis_validation_evidence.py` 已通过
- [x] thesis validation 结构化证据已按当前代码实例重新生成
- [x] readiness 证据已改为双层语义，并显式记录 `services.graph_sync`
- [x] tracking summary 证据已改为 `latest plan` 口径
- [x] 前端节点定位链路已通过真实浏览器复核
