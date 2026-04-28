export interface SummaryEntry {
  key: string
  value: string
}

const BUDGET_LABELS: Record<string, string> = {
  status: '时间状态',
  total_hours: '总学时',
  weekly_hours: '每周投入',
  estimated_weeks: '预计周数',
  suggestion: '建议',
  path_mode: '路径模式',
}

const AUDIT_LABELS: Record<string, string> = {
  node_count: '知识点数',
  total_hours: '总学时',
  path_mode: '路径模式',
  graph_option: '图谱方案',
  option_label: '方案名称',
  overlay_node_ids: '纳入扩展节点',
  added_node_ids: '新增节点',
  removed_node_ids: '移除节点',
  nodes_added_vs_baseline: '较基础方案新增',
  nodes_missing_vs_enhanced: '较增强方案缺少',
}

const FEEDBACK_LABELS: Record<string, string> = {
  path_mode: '路径模式',
  weekly_hours: '每周投入',
  deadline_weeks: '期限周数',
  theory_weight: '理论权重',
  practice_weight: '实践权重',
  known_node_ids: '已掌握知识点',
  total_hours_delta: '总学时变化',
  estimated_weeks_delta: '周期变化',
  status_before: '调整前状态',
  status_after: '调整后状态',
}

export function stringifyPreviewValue(value: unknown) {
  if (value == null) return '无'
  if (Array.isArray(value)) return value.length ? value.join('、') : '无'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export function toSummaryEntries(
  record: Record<string, unknown> | undefined,
  labels: Record<string, string>,
  allowedKeys: string[],
): SummaryEntry[] {
  const source = record ?? {}
  return allowedKeys
    .filter((key) => source[key] !== undefined && source[key] !== null && source[key] !== '')
    .map((key) => ({ key: labels[key] || key, value: stringifyPreviewValue(source[key]) }))
}

export function budgetSummaryEntries(record: Record<string, unknown> | undefined) {
  return toSummaryEntries(record, BUDGET_LABELS, ['status', 'total_hours', 'weekly_hours', 'estimated_weeks', 'suggestion', 'path_mode'])
}

export function auditSummaryEntries(record: Record<string, unknown> | undefined) {
  return toSummaryEntries(record, AUDIT_LABELS, ['node_count', 'total_hours', 'path_mode', 'graph_option', 'option_label', 'overlay_node_ids', 'added_node_ids', 'removed_node_ids', 'nodes_added_vs_baseline', 'nodes_missing_vs_enhanced'])
}

export function feedbackParameterEntries(record: Record<string, unknown> | undefined) {
  return toSummaryEntries(record, FEEDBACK_LABELS, ['path_mode', 'weekly_hours', 'deadline_weeks', 'theory_weight', 'practice_weight', 'known_node_ids'])
}

export function feedbackBudgetDeltaEntries(record: Record<string, unknown> | undefined) {
  return toSummaryEntries(record, FEEDBACK_LABELS, ['total_hours_delta', 'estimated_weeks_delta', 'status_before', 'status_after'])
}
