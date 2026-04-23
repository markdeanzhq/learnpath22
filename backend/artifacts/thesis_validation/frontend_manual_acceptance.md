# 前端手工验收清单（5.4）

- 变更：`thesis-alignment-review`
- 验收日期：`2026-04-15`
- 当前源码验收入口：`http://127.0.0.1:5173`
- 当前源码配套后端：`http://127.0.0.1:8010/api/v1`
- 对照说明：
  - `http://127.0.0.1:8080` 为旧静态构建，仅用于识别部署滞后现象
  - `http://127.0.0.1:8000/api/v1` 为旧后端实例，仅用于说明前端 `normalizeReadiness` 兼容层仍有存在意义

## A. Knowledge 页扩展实体只读展示

### A.1 入口可见
- [x] 打开 `http://127.0.0.1:5173/knowledge`
- [x] 当前项目已选中
- [x] 工具栏存在 `扩展实体` 按钮

### A.2 Drawer 可正常打开并展示 Stage / Resource
- [x] 点击 `扩展实体` 后出现标题 `扩展实体`
- [x] Drawer 内存在 `Stage 模板` 区块
- [x] Drawer 内存在 `Curated Resource` 区块
- [x] 页面可见文本显示 `3 个` Stage 模板
- [x] 页面可见文本显示 `5 个` Curated Resource

### A.3 只读语义正确
- [x] Stage 区块包含文案：`领域级默认阶段模板，只读展示，不进入审核流程`
- [x] Resource 区块包含文案：`领域级资料元数据，只读展示，不写回审核状态`
- [x] 页面未出现将 Stage / Resource 纳入审核流的交互入口

## B. Settings 页 readiness 预检提示

### B.1 预检入口存在
- [x] 打开 `http://127.0.0.1:5173/settings`
- [x] 页面存在 `运行演示预检` 按钮

### B.2 当前源码实例的预检语义
- [x] 页面展示 `SQLite` 状态为 `就绪`
- [x] 页面展示 `Neo4j` 状态为 `就绪`
- [x] 页面展示 `图谱同步` 状态为 `就绪`
- [x] 页面展示 `LLM` 状态为 `待配置`
- [x] 页面展示 `Search` 状态为 `待配置`
- [x] 页面可见原因文本 `LLM_API_KEY not configured`
- [x] 页面可见原因文本 `搜索服务未配置`
- [x] 页面整体结论对应后端双层 readiness：`core_ready=true`、`demo_ready=true`、`enhanced_ready=false`
- [x] 页面整体状态为 `status=degraded`、`ready=false`，说明“主链可演示、在线增强未就绪”

### B.3 兼容旧联调实例的归一化语义
- [x] 前端 `normalizeReadiness` 会在后端缺少 `core_ready/demo_ready/enhanced_ready` 时自动补齐
- [x] 前端 `normalizeReadiness` 会在后端缺少 `services.graph_sync` 时按 SQLite + Neo4j 状态推导兼容值
- [x] 因此旧实例仍可展示统一的 readiness 卡片语义，但论文证据与当前答辩口径以原生双层结构为准

## C. Search 页错误提示链路

### C.1 已选择项目时的 readiness 阻断
- [x] 打开 `http://127.0.0.1:5173/search`
- [x] 页面显示当前项目
- [x] 页面展示搜索未就绪提示
- [x] 页面存在 `重新预检` 按钮
- [x] 页面存在 `前往设置` 按钮
- [x] `搜索` 按钮处于禁用状态
- [x] 当前错误语义与后端 `enhanced_ready=false` 一致

### C.2 未选择项目时的空态提示
- [x] 清除 `learnpath:current-project` 后重新打开 `http://127.0.0.1:5173/search`
- [x] 页面显示空态文案：`请先在项目页面选择一个项目`

## D. Path / Dashboard → Knowledge 节点定位

### D.1 Path 页定位入口
- [x] 打开 `http://127.0.0.1:5173/path`
- [x] 路径任务卡片存在 `在图谱中定位` 按钮
- [x] 点击后跳转到 `Knowledge` 页
- [x] `Knowledge` 页根据路由 `nodeId` 聚焦目标节点
- [x] 本轮样本节点展示为 `导数与偏导`

### D.2 Dashboard 页定位入口
- [x] 打开 `http://127.0.0.1:5173/dashboard`
- [x] 进度列表存在 `在图谱中定位` 按钮
- [x] 点击后跳转到 `Knowledge` 页
- [x] 图谱画布成功聚焦同一节点
- [x] 本轮样本节点展示为 `导数与偏导`

### D.3 旧构建差异说明
- [x] `8080` 旧静态构建中未观察到上述定位按钮
- [x] 因此本轮前端联动验收只认可 `5173` 当前源码实例，不使用 `8080` 作为结论依据

## 结论

- [x] Knowledge 页扩展实体只读展示正常
- [x] Settings 页已按双层 readiness 语义展示当前依赖状态
- [x] 前端对旧 readiness 结构保留 `normalizeReadiness` 兼容能力
- [x] Search 页未就绪阻断链路可复现
- [x] Path 与 Dashboard 已支持定位到 Knowledge，并在图谱中聚焦目标节点
