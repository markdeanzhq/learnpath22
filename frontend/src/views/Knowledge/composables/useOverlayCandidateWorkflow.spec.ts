import { ref } from 'vue'
import { describe, expect, it } from 'vitest'
import type { GraphNodeData, OverlayPreflightResponse } from '@/api/modules/graph'
import {
  OVERLAY_CANDIDATE_FILTER_OPTIONS,
  useOverlayCandidateWorkflow,
  type CandidateIssueFilter,
  type OverlaySessionView,
} from './useOverlayCandidateWorkflow'

function createPreflight(visibleNodes = 0, visibleEdges = 0) {
  return {
    counts: {
      visible_overlay_nodes: visibleNodes,
      visible_overlay_edges: visibleEdges,
    },
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
  })
})
