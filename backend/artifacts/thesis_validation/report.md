# LearnPath-KG 论文验证自动评估报告

- 生成时间：2026-05-04T07:17:32.210569Z
- Matrix：`thesis-validation-v1`
- Change：`complete-domain-pack-edges`
- 引用就绪：是

## 1. 总体验证结论

- 场景通过：9/9
- 全部场景通过：是
- 依赖满足率：100.0%
- 平均阶段数：3.0
- 平均阶段总时长：75.11 小时

## 2. 运行环境与依赖状态

- 运行模式：`offline`
- 使用在线依赖：否
- Readiness：`degraded`
- Core ready：是
- Demo ready：是
- Enhanced ready：否
- Tracking 统计口径：`latest_plan`

## 3. 场景明细

| 场景 ID | 标题 | 状态 | 节点数 | 阶段数 | 总时长 | 依赖满足率 | 失败检查 |
|---|---|---:|---:|---:|---:|---:|---|
| scenario_domain_beginner | 领域型目标 × 基础薄弱画像 | ok | 47 | 3 | 125 | 100.0% | - |
| scenario_domain_intermediate | 领域型目标 × 偏实践画像 | ok | 47 | 3 | 125 | 100.0% | - |
| scenario_domain_focused | 领域型目标 × 紧周期画像 | ok | 47 | 3 | 125 | 100.0% | - |
| scenario_problem_beginner | 问题型目标 × 基础薄弱画像 | ok | 24 | 3 | 64 | 100.0% | - |
| scenario_problem_intermediate | 问题型目标 × 偏实践画像 | ok | 20 | 3 | 54 | 100.0% | - |
| scenario_problem_focused | 问题型目标 × 紧周期画像 | ok | 20 | 3 | 54 | 100.0% | - |
| scenario_concept_beginner | 概念型目标 × 基础薄弱画像 | ok | 20 | 3 | 53 | 100.0% | - |
| scenario_concept_intermediate | 概念型目标 × 偏实践画像 | ok | 14 | 3 | 38 | 100.0% | - |
| scenario_concept_focused | 概念型目标 × 紧周期画像 | ok | 14 | 3 | 38 | 100.0% | - |

## 4. 可引用证据边界

- 本报告由固定场景矩阵通过 API 自动生成，原始证据保存在 `latest.json`。
- `paper_metrics.json` 保留论文可引用的结构化指标，Markdown 报告只做可读化汇总。
- 依赖正确性以 Domain Pack 的 `REQUIRES` 边为基准，检查路径内前置节点是否早于目标节点出现。
- 路径正确性仍由知识图谱、项目快照、拓扑排序和规则评分保证，LLM/搜索只作为增强证据记录。
