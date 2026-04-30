import { computed, type Ref } from 'vue'
import type {
  GoalExtensionDraftResponse,
  GraphNodeData,
  OverlayEdgeCandidate,
  OverlayExtractionSessionResponse,
  OverlayNodeCandidate,
  OverlayPreflightResponse,
  OverlayResourceCandidate,
} from '@/api/modules/graph'

export type OverlaySessionView = OverlayExtractionSessionResponse & Partial<GoalExtensionDraftResponse>
export type CandidateIssueFilter = 'all' | 'blocking' | 'review' | 'pending' | 'ready'
export type OverlayWorkflowStepState = 'done' | 'current' | 'pending'

export type OverlayWorkflowStep = {
  key: string
  title: string
  description: string
  state: OverlayWorkflowStepState
  statusLabel: string
  tagType: 'success' | 'warning' | 'info'
}

export type OverlayCandidateDiagnosticSeverity = CandidateIssueFilter | 'empty'

export type OverlayCandidateDiagnosticItem = {
  key: CandidateIssueFilter
  title: string
  description: string
  statusLabel: string
  actionLabel: string
  count: number
  filter: CandidateIssueFilter
  tagType: 'success' | 'warning' | 'info' | 'danger'
  firstTargetTitle: string
  firstError: string
}

export type OverlayCandidateDiagnosticSummary = {
  severity: OverlayCandidateDiagnosticSeverity
  title: string
  description: string
  statusLabel: string
  tagType: 'success' | 'warning' | 'info' | 'danger'
  primaryFilter: CandidateIssueFilter
  primaryActionLabel: string
  canOpenRepairTarget: boolean
}

type OverlaySessionCandidateLike = {
  validation_status?: string | null
  review_status?: string | null
  validation_errors?: string[] | null
}

export type OverlayRepairTarget =
  | { kind: 'node'; candidate: OverlayNodeCandidate }
  | { kind: 'edge'; candidate: OverlayEdgeCandidate }
  | { kind: 'resource'; candidate: OverlayResourceCandidate }

type OverlayEndpointOption = {
  id: string
  label: string
  hint: string
  disabled?: boolean
}

export const OVERLAY_CANDIDATE_FILTER_OPTIONS: Array<{ value: CandidateIssueFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'blocking', label: '需修复' },
  { value: 'review', label: '待复核' },
  { value: 'pending', label: '待审核' },
  { value: 'ready', label: '已确认' },
]

export function useOverlayCandidateWorkflow({
  lastOverlaySession,
  overlayPreflight,
  nodes,
  overlayCandidateFilter,
}: {
  lastOverlaySession: Ref<OverlaySessionView | null>
  overlayPreflight: Ref<OverlayPreflightResponse | null>
  nodes: Ref<GraphNodeData[]>
  overlayCandidateFilter: Ref<CandidateIssueFilter>
}) {
  const overlaySessionCandidates = computed<OverlayRepairTarget[]>(() => {
    const session = lastOverlaySession.value
    if (!session) return []
    return [
      ...(session.nodes || []).map((candidate) => ({ kind: 'node' as const, candidate })),
      ...(session.edges || []).map((candidate) => ({ kind: 'edge' as const, candidate })),
      ...(session.resources || []).map((candidate) => ({ kind: 'resource' as const, candidate })),
    ]
  })

  const overlaySessionStats = computed(() => {
    const candidates = overlaySessionCandidates.value.map((item) => item.candidate)
    return {
      invalid: candidates.filter((item) => item.validation_status === 'invalid').length,
      needsReview: candidates.filter((item) => item.validation_status === 'needs_review').length,
      valid: candidates.filter((item) => item.validation_status === 'valid').length,
      pendingReview: candidates.filter((item) => item.review_status === 'pending').length,
    }
  })

  const overlayCandidateDiagnostics = computed<OverlayCandidateDiagnosticItem[]>(() => {
    const targets = overlaySessionCandidates.value
    const diagnostics = [
      buildOverlayCandidateDiagnostic({
        key: 'blocking',
        targets: targets.filter((item) => item.candidate.validation_status === 'invalid'),
        title: '先修复校验失败候选',
        description: '这些候选会阻塞增强图谱进入路径，优先补齐必填字段、证据来源或修正关系端点。',
        statusLabel: '需修复',
        actionLabel: '查看需修复',
        tagType: 'danger',
      }),
      buildOverlayCandidateDiagnostic({
        key: 'review',
        targets: targets.filter((item) => item.candidate.validation_status === 'needs_review'),
        title: '复核重复或证据不足候选',
        description: '这些候选可能重复、证据不足或需要确认是否保留，复核后再进入人工审核。',
        statusLabel: '待复核',
        actionLabel: '查看待复核',
        tagType: 'warning',
      }),
      buildOverlayCandidateDiagnostic({
        key: 'pending',
        targets: targets.filter((item) => item.candidate.validation_status === 'valid' && item.candidate.review_status === 'pending'),
        title: '确认机器校验已通过候选',
        description: '这些候选已通过机器校验但仍是草稿，人工确认后才会按规划开关进入增强图谱。',
        statusLabel: '待审核',
        actionLabel: '查看待审核',
        tagType: 'info',
      }),
      buildOverlayCandidateDiagnostic({
        key: 'ready',
        targets: targets.filter((item) => item.candidate.validation_status === 'valid' && item.candidate.review_status === 'confirmed'),
        title: '已确认候选可参与路径',
        description: '这些候选已经确认，可继续预检路径；如暂不需要进入路径，可关闭规划开关。',
        statusLabel: '已确认',
        actionLabel: '查看已确认',
        tagType: 'success',
      }),
    ]
    return diagnostics.filter((item): item is OverlayCandidateDiagnosticItem => Boolean(item))
  })

  const overlayCandidateDiagnosticSummary = computed<OverlayCandidateDiagnosticSummary>(() => {
    const total = overlaySessionCandidates.value.length
    const primary = (
      overlayCandidateDiagnostics.value.find((item) => item.key === 'blocking')
      || overlayCandidateDiagnostics.value.find((item) => item.key === 'review')
      || overlayCandidateDiagnostics.value.find((item) => item.key === 'pending')
      || overlayCandidateDiagnostics.value.find((item) => item.key === 'ready')
    )

    if (!total || !primary) {
      return {
        severity: 'empty',
        title: '暂无候选诊断',
        description: '生成自动草稿或创建扩展草稿后，系统会在这里提示阻塞项、复核项和审核入口。',
        statusLabel: '无候选',
        tagType: 'info',
        primaryFilter: 'all',
        primaryActionLabel: '查看全部候选',
        canOpenRepairTarget: false,
      }
    }

    const targetHint = primary.firstTargetTitle ? ` 首个处理目标：${primary.firstTargetTitle}。` : ''
    return {
      severity: primary.key,
      title: primary.title,
      description: `${primary.description}${targetHint}`,
      statusLabel: primary.statusLabel,
      tagType: primary.tagType,
      primaryFilter: primary.filter,
      primaryActionLabel: primary.key === 'blocking' || primary.key === 'review' ? '打开首个需处理候选' : primary.actionLabel,
      canOpenRepairTarget: primary.key === 'blocking' || primary.key === 'review',
    }
  })

  const overlaySessionGuide = computed(() => {
    if (!lastOverlaySession.value) return ''
    return `下一步：${overlayCandidateDiagnosticSummary.value.description}`
  })

  const overlayWorkflowSteps = computed<OverlayWorkflowStep[]>(() => {
    const stats = overlaySessionStats.value
    const preflight = overlayPreflight.value
    const visibleNodes = preflight?.counts.visible_overlay_nodes ?? 0
    const visibleEdges = preflight?.counts.visible_overlay_edges ?? 0
    const hasBlocking = stats.invalid > 0 || stats.needsReview > 0
    const hasPendingReview = stats.pendingReview > 0
    const hasVisibleOverlay = visibleNodes > 0 || visibleEdges > 0
    const repairState: OverlayWorkflowStepState = hasBlocking ? 'current' : 'done'
    const reviewState: OverlayWorkflowStepState = hasBlocking ? 'pending' : hasPendingReview ? 'current' : 'done'
    const graphState: OverlayWorkflowStepState = hasBlocking || hasPendingReview ? 'pending' : 'current'

    return [
      {
        key: 'source',
        title: '来源与预览',
        description: '先收集粘贴文本、搜索 URL、已保存搜索或目标理解推荐草稿；预览阶段不会写入正式图谱。',
        state: 'done',
        statusLabel: '已完成',
        tagType: 'success',
      },
      {
        key: 'repair',
        title: '校验修复',
        description: hasBlocking
          ? `还有 ${stats.invalid} 个校验失败、${stats.needsReview} 个待复核候选；先修复字段或端点，关系会跟随节点重新校验。`
          : '候选已经通过机器校验，可以进入人工审核。',
        state: repairState,
        statusLabel: repairState === 'current' ? '当前处理' : '已通过',
        tagType: repairState === 'current' ? 'warning' : 'success',
      },
      {
        key: 'review',
        title: '人工审核与规划开关',
        description: hasPendingReview
          ? `还有 ${stats.pendingReview} 个候选待确认；只有已确认且开启规划的节点/关系才会进入增强图谱。`
          : '候选已完成审核判断，规划开关决定它是否参与路径。',
        state: reviewState,
        statusLabel: reviewState === 'pending' ? '等待前置' : reviewState === 'current' ? '当前处理' : '已完成',
        tagType: reviewState === 'done' ? 'success' : reviewState === 'current' ? 'warning' : 'info',
      },
      {
        key: 'graph',
        title: '进入增强图谱 / 可选同步',
        description: hasVisibleOverlay
          ? `当前已有 ${visibleNodes} 个节点 / ${visibleEdges} 条关系可用于项目增强图谱；如需 Neo4j 投影，再显式同步图谱。`
          : '审核完成后会先进入本地增强读模型；Neo4j 投影同步是可选的显式操作。',
        state: graphState,
        statusLabel: graphState === 'pending' ? '等待前置' : '当前确认',
        tagType: graphState === 'current' ? 'warning' : 'info',
      },
    ]
  })

  const overlayWorkflowCurrentStep = computed(() => overlayWorkflowSteps.value.find((step) => step.state === 'current') || null)
  const overlayPreflightTagType = computed(() => {
    if (overlayPreflight.value?.status === 'ok') return 'success'
    if (overlayPreflight.value?.status === 'blocked') return 'danger'
    return 'warning'
  })
  const overlayPreflightStatusLabel = computed(() => {
    if (overlayPreflight.value?.status === 'ok') return '可用'
    if (overlayPreflight.value?.status === 'blocked') return '阻塞'
    return '需关注'
  })
  const overlayPreflightIssues = computed(() => [
    ...(overlayPreflight.value?.blocking_items || []),
    ...(overlayPreflight.value?.warning_items || []),
  ])
  const overlayPreflightGuidance = computed(() => {
    const preflight = overlayPreflight.value
    if (!preflight) return ''
    const counts = preflight.counts
    const invalid = counts.nodes.invalid + counts.edges.invalid
    const pendingReview = counts.nodes.pending_review + counts.edges.pending_review
    const planningDisabled = counts.nodes.planning_disabled + counts.edges.planning_disabled
    if (invalid) return '先修复校验失败候选；节点无效时，引用它的关系会暂时显示端点不存在。'
    if (pendingReview) return '已有候选通过机器校验，请逐项确认审核；只有已确认且开启规划的候选才会进入增强图谱。'
    if (planningDisabled) return '存在已确认但关闭规划的候选，如需参与路径，请重新开启规划开关。'
    if (counts.visible_overlay_nodes || counts.visible_overlay_edges) return '增强图谱已可用于项目图谱和路径预检；如需写入 Neo4j 投影，再点击同步图谱。'
    return '当前草稿尚未产生可进入增强图谱的节点或关系。'
  })
  const filteredOverlayNodes = computed(() => (lastOverlaySession.value?.nodes || []).filter((candidate) => matchesOverlayCandidateFilter(candidate, overlayCandidateFilter.value)))
  const filteredOverlayEdges = computed(() => (lastOverlaySession.value?.edges || []).filter((candidate) => matchesOverlayCandidateFilter(candidate, overlayCandidateFilter.value)))
  const filteredOverlayResources = computed(() => (lastOverlaySession.value?.resources || []).filter((candidate) => matchesOverlayCandidateFilter(candidate, overlayCandidateFilter.value)))
  const overlayCandidateFilterCounts = computed<Record<CandidateIssueFilter, number>>(() => {
    const candidates = overlaySessionCandidates.value.map((item) => item.candidate)
    return {
      all: candidates.length,
      blocking: candidates.filter((item) => matchesOverlayCandidateFilter(item, 'blocking')).length,
      review: candidates.filter((item) => matchesOverlayCandidateFilter(item, 'review')).length,
      pending: candidates.filter((item) => matchesOverlayCandidateFilter(item, 'pending')).length,
      ready: candidates.filter((item) => matchesOverlayCandidateFilter(item, 'ready')).length,
    }
  })
  const filteredOverlayCandidateCount = computed(() => (
    filteredOverlayNodes.value.length + filteredOverlayEdges.value.length + filteredOverlayResources.value.length
  ))
  const overlayCandidateRepairTarget = computed(() => (
    overlaySessionCandidates.value.find((item) => item.candidate.validation_status === 'invalid')
    || overlaySessionCandidates.value.find((item) => item.candidate.validation_status === 'needs_review')
    || null
  ))
  const overlayCandidateRepairTargetLabel = computed(() => {
    if (!overlayCandidateRepairTarget.value) return '暂无需修复候选'
    return `打开首个需处理候选：${overlayRepairTargetTitle(overlayCandidateRepairTarget.value)}`
  })
  const overlayEndpointOptions = computed(() => {
    const options = new Map<string, OverlayEndpointOption>()
    nodes.value.forEach((node) => addEndpointOption(options, node.id, node.label || node.id, '当前图谱节点'))
    ;(lastOverlaySession.value?.nodes || []).forEach((node) => {
      const isUsable = node.validation_status === 'valid'
      addEndpointOption(
        options,
        node.node_id,
        node.name || node.node_id,
        isUsable ? '本次草稿节点' : '本次草稿节点（需先修复节点）',
        !isUsable,
      )
    })
    return Array.from(options.values())
  })

  return {
    overlaySessionGuide,
    overlaySessionStats,
    overlayCandidateDiagnostics,
    overlayCandidateDiagnosticSummary,
    overlayWorkflowSteps,
    overlayWorkflowCurrentStep,
    overlayPreflightTagType,
    overlayPreflightStatusLabel,
    overlayPreflightIssues,
    overlayPreflightGuidance,
    overlaySessionCandidates,
    filteredOverlayNodes,
    filteredOverlayEdges,
    filteredOverlayResources,
    overlayCandidateFilterCounts,
    filteredOverlayCandidateCount,
    overlayCandidateRepairTarget,
    overlayCandidateRepairTargetLabel,
    overlayEndpointOptions,
    overlayRepairTargetTitle,
  }
}

function matchesOverlayCandidateFilter(candidate: OverlaySessionCandidateLike, filter: CandidateIssueFilter) {
  if (filter === 'all') return true
  if (filter === 'blocking') return candidate.validation_status === 'invalid'
  if (filter === 'review') return candidate.validation_status === 'needs_review'
  if (filter === 'pending') return candidate.validation_status === 'valid' && candidate.review_status === 'pending'
  return candidate.validation_status === 'valid' && candidate.review_status === 'confirmed'
}

function overlayRepairTargetTitle(target: OverlayRepairTarget) {
  if (target.kind === 'node') return target.candidate.name || target.candidate.node_id
  if (target.kind === 'edge') return `${target.candidate.source_node_id || target.candidate.source_name_or_id || '未知来源'} → ${target.candidate.target_node_id || target.candidate.target_name_or_id || '未知目标'}`
  return target.candidate.title || target.candidate.resource_id
}

function buildOverlayCandidateDiagnostic({
  key,
  targets,
  title,
  description,
  statusLabel,
  actionLabel,
  tagType,
}: {
  key: CandidateIssueFilter
  targets: OverlayRepairTarget[]
  title: string
  description: string
  statusLabel: string
  actionLabel: string
  tagType: 'success' | 'warning' | 'info' | 'danger'
}): OverlayCandidateDiagnosticItem | null {
  if (!targets.length) return null
  const firstTarget = targets[0]
  return {
    key,
    title,
    description,
    statusLabel,
    actionLabel,
    count: targets.length,
    filter: key,
    tagType,
    firstTargetTitle: overlayRepairTargetTitle(firstTarget),
    firstError: firstTarget.candidate.validation_errors?.[0] || '',
  }
}

function addEndpointOption(
  options: Map<string, OverlayEndpointOption>,
  id?: string | null,
  label?: string | null,
  hint = '可选节点',
  disabled = false,
) {
  const normalizedId = typeof id === 'string' ? id.trim() : ''
  if (!normalizedId || options.has(normalizedId)) return
  const normalizedLabel = typeof label === 'string' && label.trim() ? label.trim() : normalizedId
  options.set(normalizedId, {
    id: normalizedId,
    label: normalizedLabel === normalizedId ? normalizedId : `${normalizedLabel}（${normalizedId}）`,
    hint,
    disabled,
  })
}
