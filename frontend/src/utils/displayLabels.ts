export type ElementTagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

interface DisplayMeta {
  label: string
  tagType?: ElementTagType
  detail?: string
}

const fallback = (value?: string | null, noun = '状态'): DisplayMeta => {
  const raw = normalizeRaw(value)
  return raw
    ? { label: `未识别${noun}`, tagType: 'warning', detail: raw }
    : { label: `未知${noun}`, tagType: 'warning' }
}

function normalizeRaw(value?: string | null) {
  return typeof value === 'string' && value.trim() ? value.trim() : ''
}

function pick(value: string | null | undefined, map: Record<string, DisplayMeta>, noun: string) {
  const raw = normalizeRaw(value)
  return raw && map[raw] ? map[raw] : fallback(raw, noun)
}

const PROJECT_STATUS: Record<string, DisplayMeta> = {
  draft: { label: '待完善', tagType: 'warning' },
  active: { label: '进行中', tagType: 'primary' },
  completed: { label: '已完成', tagType: 'success' },
  archived: { label: '已归档', tagType: 'info' },
}

const RESOLVE_SOURCE: Record<string, DisplayMeta> = {
  template: { label: '目标模板', tagType: 'success', detail: '命中预设学习目标模板' },
  jieba: { label: '词面匹配', tagType: 'info', detail: '根据节点名称、别名、关键词和描述匹配' },
  lexical: { label: '词面匹配', tagType: 'info', detail: '根据节点名称、别名、关键词和描述匹配' },
  llm: { label: 'AI 辅助识别', tagType: 'warning', detail: '由 LLM 补充召回目标候选' },
  domain_default: { label: '领域默认策略', tagType: 'info' },
  fallback: { label: '规则兜底', tagType: 'warning' },
}

const REVIEW_STATUS: Record<string, DisplayMeta> = {
  pending: { label: '待审核', tagType: 'warning' },
  confirmed: { label: '已确认', tagType: 'success' },
  removed: { label: '已移除', tagType: 'danger' },
  rejected: { label: '已拒绝', tagType: 'danger' },
}

const VALIDATION_STATUS: Record<string, DisplayMeta> = {
  valid: { label: '校验通过', tagType: 'success' },
  invalid: { label: '校验失败', tagType: 'danger' },
  needs_review: { label: '待人工确认', tagType: 'warning' },
  unknown: { label: '未校验', tagType: 'warning' },
}

const PROMOTION_STATUS: Record<string, DisplayMeta> = {
  not_promoted: { label: '未推广', tagType: 'info' },
  promotion_ready: { label: '可推广', tagType: 'warning' },
  promotion_failed: { label: '推广失败', tagType: 'danger' },
  promoted: { label: '已归档到领域包', tagType: 'success' },
  archived: { label: '已归档', tagType: 'info' },
  unknown: { label: '未进入推广流程', tagType: 'info' },
}

const PROMOTION_PREVIEW_STATUS: Record<string, DisplayMeta> = {
  ready: { label: '预览通过', tagType: 'success', detail: '候选内容可写入领域包' },
  invalid: { label: '预览未通过', tagType: 'danger', detail: '候选内容未通过领域包校验' },
  empty: { label: '暂无可推广候选', tagType: 'info', detail: '当前没有满足推广条件的项目扩展' },
  promoted: { label: '推广完成', tagType: 'success' },
  failed: { label: '推广失败', tagType: 'danger' },
}

const SESSION_STATUS: Record<string, DisplayMeta> = {
  pending: { label: '等待处理', tagType: 'warning' },
  running: { label: '抽取中', tagType: 'primary' },
  completed: { label: '抽取完成', tagType: 'success' },
  partial: { label: '部分完成', tagType: 'warning' },
  drafted: { label: '草稿已生成', tagType: 'primary' },
  validated: { label: '已校验', tagType: 'warning' },
  reviewed: { label: '已审核', tagType: 'success' },
  promoted: { label: '已推广', tagType: 'success' },
  archived: { label: '已归档', tagType: 'info' },
  failed: { label: '抽取失败', tagType: 'danger' },
}

const RESOURCE_TYPE: Record<string, DisplayMeta> = {
  article: { label: '文章', tagType: 'info' },
  video: { label: '视频', tagType: 'warning' },
  book: { label: '书籍', tagType: 'success' },
  course: { label: '课程', tagType: 'primary' },
  doc: { label: '文档', tagType: 'info' },
  resource: { label: '资料', tagType: 'info' },
}

const SOURCE_TYPE: Record<string, DisplayMeta> = {
  static: { label: '静态保底', tagType: 'info' },
  manual: { label: '手动绑定', tagType: 'success' },
  online: { label: '在线增强', tagType: 'warning' },
  tavily: { label: '在线增强', tagType: 'warning' },
}

const AUDIT_SOURCE: Record<string, DisplayMeta> = {
  'audit.goal_result': { label: '目标解析审计快照' },
  'audit.closure_ids': { label: '硬前置闭包记录' },
  dependency_chain_explanations: { label: '依赖链解释记录' },
  'audit.reinforcement_logs': { label: '画像补强审计记录' },
  'audit.ordering_logs': { label: '排序审计记录' },
  'audit.stage_logs': { label: '阶段划分审计记录' },
  'audit.budget_summary': { label: '时间预算审计记录' },
  'audit.overlay_lineage': { label: '项目扩展快照记录' },
  'meta.provenance': { label: '解释来源与回退记录' },
  node_explanations: { label: '节点纳入依据' },
  ordering_explanations: { label: '排序依据' },
  stage_explanations: { label: '阶段划分依据' },
  budget_explanation: { label: '时间预算依据' },
}

const ERROR_CODE: Record<string, string> = {
  SEARCH_NOT_READY: '搜索服务尚未就绪',
  EMPTY_CANDIDATES: '未找到可确认的目标候选',
  negative_patterns_excluded_all: '目标文本被排除规则过滤',
  INVALID_GOAL_TYPE: '目标类型不受支持',
  INVALID_DOMAIN: '当前仅支持默认机器学习领域',
  INVALID_PATH_MODE: '路径模式不受支持',
  INVALID_GRAPH_SCOPE: '图谱范围不受支持',
  INVALID_GRAPH_PATH_ID: '路径图谱编号无效',
  INVALID_OVERLAY_ELEMENT_TYPE: '项目扩展元素类型无效',
  INVALID_OVERLAY_EXTRACTION_MODE: '扩展抽取模式无效',
  INVALID_OVERLAY_SESSION_TRANSITION: '扩展会话状态流转无效',
  INVALID_RESOURCE_BINDING_TARGET_TYPE: '资源绑定目标类型无效',
  INVALID_RESOLUTION_CANDIDATE: '目标候选无效',
  INVALID_LLM_EXTRACTION_JSON: 'AI 抽取结果格式无效',
  STALE_RESOLUTION_SESSION: '目标解析会话已过期，请重新解析目标',
  GOAL_TARGETS_REMOVED: '已确认的目标节点被移除，请重新确认学习目标',
  GOAL_DEFAULT_TARGETS_UNAVAILABLE: '默认目标节点不可用',
  OVERLAY_SESSION_NOT_FOUND: '扩展抽取会话不存在',
  OVERLAY_SESSION_NOT_EDITABLE: '扩展抽取会话当前不可编辑',
  OVERLAY_SESSION_REVIEW_REQUIRED: '请先审核扩展候选',
  OVERLAY_ID_REPLAY_SESSION_MISMATCH: '扩展来源与当前会话不匹配',
  OVERLAY_PROMOTION_BATCH_NOT_FOUND: '推广批次不存在',
  PERSISTED_SEARCH_RESULT_NOT_FOUND: '已保存搜索结果不存在',
  PERSISTED_SEARCH_RESULTS_REQUIRED: '请选择要桥接的搜索结果',
  DUPLICATE_PERSISTED_SEARCH_RESULT_ID: '搜索结果选择重复',
  PROMOTION_DISABLED: '领域包推广未启用',
  PROMOTION_FORBIDDEN: '推广密钥无效',
  PROMOTION_PREVIEW_INVALID: '推广预览未通过',
  PROMOTION_COMMIT_FAILED: '推广写入失败',
  PROMOTION_CACHE_RELOAD_FAILED: '推广后缓存刷新失败',
  no_candidates: '暂无可推广候选',
  projection_status_unavailable: '项目扩展状态暂时无法读取',
  seed_metadata_stale: '图谱同步信息已过期',
  missing_api_key: '尚未配置 API Key',
  connection_failed: '服务连接失败',
}

export function projectStatusMeta(status?: string | null) {
  return pick(status, PROJECT_STATUS, '项目状态')
}

export function resolveSourceMeta(source?: string | null) {
  return pick(source, RESOLVE_SOURCE, '解析来源')
}

export function reviewStatusMeta(status?: string | null) {
  return pick(status, REVIEW_STATUS, '审核状态')
}

export function validationStatusMeta(status?: string | null) {
  return pick(status, VALIDATION_STATUS, '校验状态')
}

export function promotionStatusMeta(status?: string | null) {
  return pick(status, PROMOTION_STATUS, '推广状态')
}

export function promotionPreviewStatusMeta(status?: string | null) {
  return pick(status, PROMOTION_PREVIEW_STATUS, '推广预览状态')
}

export function sessionStatusMeta(status?: string | null) {
  return pick(status, SESSION_STATUS, '抽取状态')
}

export function resourceTypeMeta(type?: string | null) {
  return pick(type, RESOURCE_TYPE, '资料类型')
}

export function sourceTypeMeta(type?: string | null) {
  return pick(type, SOURCE_TYPE, '来源类型')
}

export function auditSourceLabel(source?: string | null) {
  return pick(source, AUDIT_SOURCE, '审计来源')
}

export function formatErrorCode(code?: string | null) {
  const raw = normalizeRaw(code)
  return raw ? ERROR_CODE[raw] || raw : ''
}

export function formatServiceReason(reason?: string | null) {
  const raw = normalizeRaw(reason)
  return raw ? ERROR_CODE[raw] || raw : ''
}

export function traceTitle(label: string, raw?: string | null) {
  const normalized = normalizeRaw(raw)
  return normalized && normalized !== label ? `${label}（原始值：${normalized}）` : label
}
