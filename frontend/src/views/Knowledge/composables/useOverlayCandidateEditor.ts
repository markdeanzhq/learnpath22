import { computed, ref, type Ref } from 'vue'
import {
  graphApi,
  type OverlayEdgeCandidate,
  type OverlayNodeCandidate,
  type OverlayResourceCandidate,
} from '@/api/modules/graph'
import type { OverlaySessionView } from './useOverlayCandidateWorkflow'

type EditableCandidateKind = 'node' | 'edge' | 'resource'

export type CandidateEditorState = {
  visible: boolean
  saving: boolean
  kind: EditableCandidateKind
  id: string
  title: string
  errors: string[]
  validationStatus: string
  reviewStatus: string
  form: Record<string, any>
}

type UseOverlayCandidateEditorOptions = {
  projectId: Readonly<Ref<string | undefined>>
  lastOverlaySession: Ref<OverlaySessionView | null>
  overlayError: Ref<string>
  refreshAfterSave: () => Promise<void>
  getErrorMessage: (error: unknown) => string
  notifySuccess?: (message: string) => void
}

const VALIDATION_ERROR_FIELDS: Record<string, string[]> = {
  missing_summary: ['summary'],
  missing_legality_rationale: ['legality_rationale'],
  invalid_difficulty_final: ['difficulty_final'],
  invalid_importance_final: ['importance_final'],
  invalid_req_math: ['req_math'],
  invalid_req_coding: ['req_coding'],
  invalid_req_ml: ['req_ml'],
  invalid_estimated_hours: ['estimated_hours'],
  invalid_theory_weight: ['theory_weight'],
  invalid_practice_weight: ['practice_weight'],
  invalid_weight_sum: ['theory_weight', 'practice_weight'],
  invalid_confidence: ['confidence'],
  invalid_quality_score: ['quality_score'],
  invalid_relation_type: ['relation_type'],
  self_loop: ['source_node_id', 'target_node_id'],
  dangling_source: ['source_node_id'],
  dangling_target: ['target_node_id'],
  requires_cycle: ['relation_type'],
  invalid_evidence_source_id: ['evidence_source_id'],
  missing_endpoint: ['source_node_id', 'target_node_id'],
  missing_title: ['title'],
  missing_url: ['url'],
  missing_resource_type: ['resource_type'],
  missing_evidence_source_id: ['evidence_source_id'],
}

const QUICK_FIX_LABELS: Record<string, string> = {
  missing_summary: '补默认摘要',
  missing_legality_rationale: '补合法性说明',
  invalid_difficulty_final: '难度归位',
  invalid_importance_final: '重要性归位',
  invalid_req_math: '数学要求归位',
  invalid_req_coding: '编程要求归位',
  invalid_req_ml: '机器学习要求归位',
  invalid_estimated_hours: '学习时长归位',
  invalid_theory_weight: '理论权重归位',
  invalid_practice_weight: '实践权重归位',
  invalid_weight_sum: '平衡理论/实践',
  invalid_confidence: '清空置信度',
  invalid_quality_score: '质量分归位',
  invalid_relation_type: '改为 RELATED_TO',
  missing_resource_type: '补资源类型',
}

const VALIDATION_ERROR_HINTS: Record<string, { label: string; suggestion: string }> = {
  missing_summary: { label: '缺少摘要', suggestion: '补充一句说明该候选的学习含义。' },
  missing_legality_rationale: { label: '缺少合法性理由', suggestion: '说明为什么该候选属于机器学习基础扩展范围。' },
  invalid_difficulty_final: { label: '难度必须是 1~5 的整数', suggestion: '将 difficulty_final 调整到 1、2、3、4 或 5。' },
  invalid_importance_final: { label: '重要性必须是 1~5 的整数', suggestion: '将 importance_final 调整到 1、2、3、4 或 5。' },
  invalid_req_math: { label: '数学基础要求必须是 1~5 的整数', suggestion: '将 req_math 调整到 1、2、3、4 或 5。' },
  invalid_req_coding: { label: '编程基础要求必须是 1~5 的整数', suggestion: '将 req_coding 调整到 1、2、3、4 或 5。' },
  invalid_req_ml: { label: '机器学习基础要求必须是 1~5 的整数', suggestion: '将 req_ml 调整到 1、2、3、4 或 5。' },
  invalid_estimated_hours: { label: '预计学习时长无效', suggestion: '填写大于 0 的小时数。' },
  invalid_theory_weight: { label: '理论权重无效', suggestion: '填写 0~1 之间的小数。' },
  invalid_practice_weight: { label: '实践权重无效', suggestion: '填写 0~1 之间的小数。' },
  invalid_weight_sum: { label: '理论/实践权重不等于 1', suggestion: '调整 theory_weight 与 practice_weight，使总和为 1。' },
  invalid_confidence: { label: '置信度无效', suggestion: '填写 0~1 之间的小数，或留空。' },
  invalid_quality_score: { label: '资源质量分无效', suggestion: '填写 0~1 之间的小数。' },
  invalid_relation_type: { label: '关系类型不受支持', suggestion: '只保留 REQUIRES 或 RELATED_TO。' },
  self_loop: { label: '关系不能指向自身', suggestion: '改选不同的来源节点或目标节点。' },
  dangling_source: { label: '关系来源节点暂不可用', suggestion: '如果来源是本次新增节点，请先修复该节点的校验错误；否则改为已有节点 ID。' },
  dangling_target: { label: '关系目标节点暂不可用', suggestion: '如果目标是本次新增节点，请先修复该节点的校验错误；否则改为已有节点 ID。' },
  requires_cycle: { label: 'REQUIRES 会形成环', suggestion: '改为 RELATED_TO，或调整依赖方向。' },
  invalid_evidence_source_id: { label: '资源证据来源无效', suggestion: '选择本次草稿使用的 source_id 作为证据来源。' },
  missing_endpoint: { label: '关系端点不完整', suggestion: '补齐 source 和 target。' },
  missing_title: { label: '缺少资源标题', suggestion: '补充便于识别的资料标题。' },
  missing_url: { label: '缺少资源 URL', suggestion: '补充资料链接。' },
  missing_resource_type: { label: '缺少资源类型', suggestion: '填写 article、video、course、book 或 doc 等类型。' },
  missing_evidence_source_id: { label: '缺少资源证据来源', suggestion: '为资源候选关联一个来源。' },
}

export function useOverlayCandidateEditor({
  projectId,
  lastOverlaySession,
  overlayError,
  refreshAfterSave,
  getErrorMessage,
  notifySuccess,
}: UseOverlayCandidateEditorOptions) {
  const candidateEditor = ref<CandidateEditorState>(createEmptyCandidateEditor())
  const candidateEditorIssueSummary = computed(() => {
    const errors = candidateEditor.value.errors
    if (!errors.length) return '当前候选暂无校验问题。'
    return `当前候选有 ${errors.length} 个问题：${errors.map(validationErrorMessage).join('；')}`
  })
  const candidateEditorQuickFixErrors = computed(() => candidateEditor.value.errors.filter(isCandidateQuickFixAvailable))

  function resetCandidateEditor() {
    candidateEditor.value = createEmptyCandidateEditor()
  }

  function openNodeCandidateEditor(node: OverlayNodeCandidate) {
    candidateEditor.value = {
      visible: true,
      saving: false,
      kind: 'node',
      id: node.node_id,
      title: `编辑节点候选：${node.name || node.node_id}`,
      errors: node.validation_errors || [],
      validationStatus: node.validation_status || 'unknown',
      reviewStatus: node.review_status || 'pending',
      form: {
        name: node.name,
        summary: node.summary || '',
        group: node.group || '',
        category: node.category || '',
        difficulty_final: node.difficulty_final ?? 2,
        importance_final: node.importance_final ?? 3,
        estimated_hours: node.estimated_hours ?? 2,
        req_math: node.req_math ?? 2,
        req_coding: node.req_coding ?? 2,
        req_ml: node.req_ml ?? 1,
        theory_weight: node.theory_weight ?? 0.6,
        practice_weight: node.practice_weight ?? 0.4,
        confidence: node.confidence ?? null,
        legality_rationale: node.legality_rationale || '',
      },
    }
  }

  function openEdgeCandidateEditor(edge: OverlayEdgeCandidate) {
    candidateEditor.value = {
      visible: true,
      saving: false,
      kind: 'edge',
      id: edge.edge_id,
      title: `编辑关系候选：${edge.source_node_id || edge.source_name_or_id || '未知来源'} → ${edge.target_node_id || edge.target_name_or_id || '未知目标'}`,
      errors: edge.validation_errors || [],
      validationStatus: edge.validation_status || 'unknown',
      reviewStatus: edge.review_status || 'pending',
      form: {
        source_node_id: edge.source_node_id || edge.source_name_or_id || '',
        target_node_id: edge.target_node_id || edge.target_name_or_id || '',
        relation_type: edge.relation_type || 'RELATED_TO',
        confidence: edge.confidence ?? null,
        legality_rationale: edge.legality_rationale || '',
      },
    }
  }

  function openResourceCandidateEditor(resource: OverlayResourceCandidate) {
    candidateEditor.value = {
      visible: true,
      saving: false,
      kind: 'resource',
      id: resource.resource_id,
      title: `编辑资源候选：${resource.title || resource.resource_id}`,
      errors: resource.validation_errors || [],
      validationStatus: resource.validation_status || 'unknown',
      reviewStatus: resource.review_status || 'pending',
      form: {
        title: resource.title || '',
        url: resource.url || '',
        resource_type: resource.resource_type || 'article',
        summary: resource.summary || '',
        quality_score: resource.quality_score ?? 0.8,
        confidence: resource.confidence ?? null,
        evidence_source_id: resource.evidence_source_id || resource.source_ids?.[0] || '',
      },
    }
  }

  async function saveCandidateEditor() {
    const currentProjectId = projectId.value
    if (!currentProjectId || !candidateEditor.value.id) return
    candidateEditor.value.saving = true
    overlayError.value = ''
    try {
      const patch = candidateEditorPatch(candidateEditor.value.form)
      if (candidateEditor.value.kind === 'node') {
        lastOverlaySession.value = await graphApi.updateOverlayNodeCandidate(currentProjectId, candidateEditor.value.id, patch)
      } else if (candidateEditor.value.kind === 'edge') {
        lastOverlaySession.value = await graphApi.updateOverlayEdgeCandidate(currentProjectId, candidateEditor.value.id, patch)
      } else {
        lastOverlaySession.value = await graphApi.updateOverlayResourceCandidate(currentProjectId, candidateEditor.value.id, patch)
      }
      candidateEditor.value.visible = false
      await refreshAfterSave()
      notifySuccess?.('候选已保存并重新校验')
    } catch (error: unknown) {
      overlayError.value = getErrorMessage(error)
    } finally {
      candidateEditor.value.saving = false
    }
  }

  function candidateEditorFieldIssue(field: string) {
    const error = candidateEditor.value.errors.find((code) => validationErrorFields(code).includes(field))
    return error ? validationErrorMessage(error) : ''
  }

  function applyCandidateQuickFix(code: string) {
    if (code.startsWith('missing_fields:')) {
      validationErrorFields(code).forEach(applyCandidateFieldDefault)
      return
    }
    if (code === 'invalid_weight_sum') {
      normalizeCandidateEditorWeights()
      return
    }
    if (code === 'invalid_confidence') {
      candidateEditor.value.form.confidence = null
      return
    }
    if (code === 'invalid_relation_type') {
      candidateEditor.value.form.relation_type = 'RELATED_TO'
      return
    }
    validationErrorFields(code).forEach(applyCandidateFieldDefault)
  }

  function applyCandidateFieldDefault(field: string) {
    if (!canApplyCandidateFieldDefault(field)) return
    const form = candidateEditor.value.form
    if (field === 'summary') {
      form.summary = form.summary || `${candidateEditor.value.title.replace(/^编辑(节点|关系|资源)候选：/, '')} 的学习扩展说明。`
    } else if (field === 'legality_rationale') {
      form.legality_rationale = form.legality_rationale || '该候选来自项目资料，可作为机器学习基础学习路径的补充内容。'
    } else if (field === 'difficulty_final') {
      form.difficulty_final = clampInteger(form.difficulty_final, 1, 5, 2)
    } else if (field === 'importance_final') {
      form.importance_final = clampInteger(form.importance_final, 1, 5, 3)
    } else if (field === 'estimated_hours') {
      form.estimated_hours = Number(form.estimated_hours) > 0 ? Number(form.estimated_hours) : 2
    } else if (field === 'req_math' || field === 'req_coding' || field === 'req_ml') {
      form[field] = clampInteger(form[field], 1, 5, field === 'req_ml' ? 1 : 2)
    } else if (field === 'theory_weight' || field === 'practice_weight') {
      normalizeCandidateEditorWeights()
    } else if (field === 'quality_score') {
      form.quality_score = normalizeRatio(form.quality_score, 0.8)
    } else if (field === 'resource_type') {
      form.resource_type = form.resource_type || 'article'
    }
  }

  function normalizeCandidateEditorWeights() {
    const theory = normalizeRatio(candidateEditor.value.form.theory_weight, 0.6)
    const safeTheory = theory <= 0 || theory >= 1 ? 0.6 : theory
    candidateEditor.value.form.theory_weight = Number(safeTheory.toFixed(2))
    candidateEditor.value.form.practice_weight = Number((1 - safeTheory).toFixed(2))
  }

  return {
    candidateEditor,
    candidateEditorIssueSummary,
    candidateEditorQuickFixErrors,
    candidateEditorFieldIssue,
    openNodeCandidateEditor,
    openEdgeCandidateEditor,
    openResourceCandidateEditor,
    saveCandidateEditor,
    resetCandidateEditor,
    validationErrorMessage,
    quickFixLabel,
    applyCandidateQuickFix,
  }
}

function createEmptyCandidateEditor(): CandidateEditorState {
  return {
    visible: false,
    saving: false,
    kind: 'node',
    id: '',
    title: '',
    errors: [],
    validationStatus: 'unknown',
    reviewStatus: 'pending',
    form: {},
  }
}

function candidateEditorPatch(form: Record<string, any>) {
  return Object.fromEntries(
    Object.entries(form).map(([key, value]) => [
      key,
      typeof value === 'string' ? value.trim() || null : value,
    ]).filter(([, value]) => value !== undefined),
  )
}

function validationErrorMessage(code: string) {
  if (code.startsWith('missing_fields:')) {
    const fields = code.slice('missing_fields:'.length).split(',').filter(Boolean).join('、')
    return `缺少规划字段：${fields}。建议补齐难度、重要性、时间和画像需求字段。`
  }
  const hint = VALIDATION_ERROR_HINTS[code]
  return hint ? `${hint.label}。${hint.suggestion}` : code
}

function validationErrorFields(code: string) {
  if (code.startsWith('missing_fields:')) {
    return code.slice('missing_fields:'.length).split(',').filter(Boolean)
  }
  return VALIDATION_ERROR_FIELDS[code] || []
}

function quickFixLabel(code: string) {
  if (code.startsWith('missing_fields:')) return '补齐规划字段'
  return QUICK_FIX_LABELS[code] || '应用建议'
}

function isCandidateQuickFixAvailable(code: string) {
  if (code.startsWith('missing_fields:')) {
    return validationErrorFields(code).some(canApplyCandidateFieldDefault)
  }
  return Boolean(QUICK_FIX_LABELS[code])
}

function canApplyCandidateFieldDefault(field: string) {
  return [
    'summary',
    'legality_rationale',
    'difficulty_final',
    'importance_final',
    'estimated_hours',
    'req_math',
    'req_coding',
    'req_ml',
    'theory_weight',
    'practice_weight',
    'quality_score',
    'resource_type',
  ].includes(field)
}

function clampInteger(value: unknown, min: number, max: number, fallback: number) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return fallback
  return Math.min(max, Math.max(min, Math.round(numeric)))
}

function normalizeRatio(value: unknown, fallback: number) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return fallback
  return Math.min(1, Math.max(0, Number(numeric.toFixed(2))))
}
