import { ref } from 'vue'
import { describe, expect, it } from 'vitest'
import type { GraphNodeData, OverlayPreflightResponse } from '@/api/modules/graph'
import {
  OVERLAY_CANDIDATE_FILTER_OPTIONS,
  useOverlayCandidateWorkflow,
  type CandidateIssueFilter,
  type OverlaySessionView,
} from './useOverlayCandidateWorkflow'

function createPreflight(
  visibleNodes = 0,
  visibleEdges = 0,
  options: {
    status?: string
    nodeCounts?: Partial<Record<'invalid' | 'pending_review' | 'planning_disabled', number>>
    edgeCounts?: Partial<Record<'invalid' | 'pending_review' | 'planning_disabled', number>>
    blockingItems?: Array<{ kind: string; message: string }>
    warningItems?: Array<{ kind: string; message: string }>
  } = {},
) {
  return {
    status: options.status || 'warning',
    counts: {
      active_nodes: visibleNodes,
      active_edges: visibleEdges,
      visible_overlay_nodes: visibleNodes,
      visible_overlay_edges: visibleEdges,
      path_overlay_nodes: 0,
      path_overlay_edges: 0,
      ignored_overlay_edges: 0,
      nodes: { invalid: 0, pending_review: 0, planning_disabled: 0, ...options.nodeCounts },
      edges: { invalid: 0, pending_review: 0, planning_disabled: 0, ...options.edgeCounts },
    },
    blocking_items: options.blockingItems || [],
    warning_items: options.warningItems || [],
  } as OverlayPreflightResponse
}

describe('useOverlayCandidateWorkflow', () => {
  it('summarizes, filters, and prioritizes overlay candidates', () => {
    const lastOverlaySession = ref({
      nodes: [
        { node_id: 'draft-invalid', name: '待修复节点', validation_status: 'invalid', review_status: 'pending' },
        { node_id: 'draft-pending', name: '待审核节点', validation_status: 'valid', review_status: 'pending' },
      ],
      edges: [
        { edge_id: 'edge-review', source_node_id: 'draft-pending', target_node_id: 'ml_c01', validation_status: 'needs_review', review_status: 'pending' },
      ],
      resources: [
        { resource_id: 'resource-ready', title: '已确认资料', validation_status: 'valid', review_status: 'confirmed' },
      ],
    } as unknown as OverlaySessionView)
    const overlayPreflight = ref(createPreflight())
    const nodes = ref([
      { id: 'ml_c01', label: '机器学习概览' },
    ] as GraphNodeData[])
    const overlayCandidateFilter = ref<CandidateIssueFilter>('blocking')

    const workflow = useOverlayCandidateWorkflow({ lastOverlaySession, overlayPreflight, nodes, overlayCandidateFilter })

    expect(OVERLAY_CANDIDATE_FILTER_OPTIONS.map((option) => option.value)).toEqual(['all', 'blocking', 'review', 'pending', 'ready'])
    expect(workflow.overlaySessionStats.value).toEqual({ invalid: 1, needsReview: 1, valid: 2, pendingReview: 3 })
    expect(workflow.overlayWorkflowCurrentStep.value?.title).toBe('校验修复')
    expect(workflow.overlayPreflightTagType.value).toBe('warning')
    expect(workflow.overlayPreflightStatusLabel.value).toBe('需关注')
    expect(workflow.overlayCandidateFilterCounts.value).toEqual({ all: 4, blocking: 1, review: 1, pending: 1, ready: 1 })
    expect(workflow.filteredOverlayNodes.value).toHaveLength(1)
    expect(workflow.filteredOverlayCandidateCount.value).toBe(1)
    expect(workflow.overlayCandidateRepairTargetLabel.value).toContain('待修复节点')
  })

  it('builds endpoint options and graph-ready guidance', () => {
    const lastOverlaySession = ref({
      nodes: [
        { node_id: 'draft-valid', name: '可用草稿节点', validation_status: 'valid', review_status: 'confirmed' },
        { node_id: 'draft-invalid', name: '不可用草稿节点', validation_status: 'invalid', review_status: 'pending' },
      ],
      edges: [],
      resources: [],
    } as unknown as OverlaySessionView)
    const overlayPreflight = ref(createPreflight(1, 1))
    const nodes = ref([
      { id: 'ml_c01', label: '机器学习概览' },
    ] as GraphNodeData[])
    const overlayCandidateFilter = ref<CandidateIssueFilter>('all')

    const workflow = useOverlayCandidateWorkflow({ lastOverlaySession, overlayPreflight, nodes, overlayCandidateFilter })

    expect(workflow.overlayEndpointOptions.value).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'ml_c01', label: '机器学习概览（ml_c01）', hint: '当前图谱节点' }),
      expect.objectContaining({ id: 'draft-valid', label: '可用草稿节点（draft-valid）', hint: '本次草稿节点' }),
      expect.objectContaining({ id: 'draft-invalid', disabled: true, hint: '本次草稿节点（需先修复节点）' }),
    ]))
    expect(workflow.overlayWorkflowCurrentStep.value?.title).toBe('校验修复')

    lastOverlaySession.value = {
      nodes: [
        { node_id: 'draft-valid', name: '可用草稿节点', validation_status: 'valid', review_status: 'confirmed' },
      ],
      edges: [],
      resources: [],
    } as unknown as OverlaySessionView

    const finalStep = workflow.overlayWorkflowSteps.value[workflow.overlayWorkflowSteps.value.length - 1]
    expect(workflow.overlayWorkflowCurrentStep.value?.title).toBe('进入增强图谱 / 可选同步')
    expect(finalStep.description).toContain('当前已有 1 个节点 / 1 条关系')
    expect(workflow.overlayPreflightGuidance.value).toContain('增强图谱已可用于项目图谱和路径预检')
  })

  it('interprets preflight guidance, status labels, and issue lists', () => {
    const lastOverlaySession = ref({ nodes: [], edges: [], resources: [] } as unknown as OverlaySessionView)
    const overlayPreflight = ref(createPreflight(0, 0, {
      status: 'blocked',
      nodeCounts: { invalid: 1 },
      blockingItems: [{ kind: 'invalid_nodes', message: '存在无效节点' }],
      warningItems: [{ kind: 'projection_missing', message: '投影未同步' }],
    }))
    const nodes = ref([] as GraphNodeData[])
    const overlayCandidateFilter = ref<CandidateIssueFilter>('all')

    const workflow = useOverlayCandidateWorkflow({ lastOverlaySession, overlayPreflight, nodes, overlayCandidateFilter })

    expect(workflow.overlayPreflightTagType.value).toBe('danger')
    expect(workflow.overlayPreflightStatusLabel.value).toBe('阻塞')
    expect(workflow.overlayPreflightGuidance.value).toContain('先修复校验失败候选')
    expect(workflow.overlayPreflightIssues.value.map((item) => item.message)).toEqual(['存在无效节点', '投影未同步'])

    overlayPreflight.value = createPreflight(0, 0, { nodeCounts: { pending_review: 1 } })
    expect(workflow.overlayPreflightGuidance.value).toContain('请逐项确认审核')

    overlayPreflight.value = createPreflight(0, 0, { edgeCounts: { planning_disabled: 1 } })
    expect(workflow.overlayPreflightGuidance.value).toContain('重新开启规划开关')

    overlayPreflight.value = createPreflight(0, 0, { status: 'ok' })
    expect(workflow.overlayPreflightTagType.value).toBe('success')
    expect(workflow.overlayPreflightStatusLabel.value).toBe('可用')
    expect(workflow.overlayPreflightGuidance.value).toContain('当前草稿尚未产生可进入增强图谱')
  })
})
