import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useGraphReviewActions } from './useGraphReviewActions'

const {
  reviewNodeMock,
  reviewEdgeMock,
  reviewOverlayElementMock,
  setOverlayPlanningMock,
  confirmMock,
} = vi.hoisted(() => ({
  reviewNodeMock: vi.fn(),
  reviewEdgeMock: vi.fn(),
  reviewOverlayElementMock: vi.fn(),
  setOverlayPlanningMock: vi.fn(),
  confirmMock: vi.fn(),
}))

vi.mock('@/api/modules/graph', () => ({
  graphApi: {
    reviewNode: reviewNodeMock,
    reviewEdge: reviewEdgeMock,
    reviewOverlayElement: reviewOverlayElementMock,
    setOverlayPlanning: setOverlayPlanningMock,
  },
}))

vi.mock('element-plus/es/components/message-box/index', () => ({
  ElMessageBox: {
    confirm: confirmMock,
  },
}))

function createReviewActions() {
  const projectId = ref<string | undefined>('project-001')
  const nodes = ref([
    { id: 'ml_c01', label: '机器学习导论', origin: 'domain' },
    { id: 'po:node-001', label: '扩展节点', origin: 'overlay' },
  ] as any[])
  const edges = ref([
    { id: 'ml_c01->ml_c02', source: 'ml_c01', target: 'ml_c02', origin: 'domain' },
    { id: 'po:edge-001', source: 'po:node-001', target: 'ml_c01', origin: 'overlay' },
  ] as any[])
  const elements = ref([
    { group: 'nodes', data: { id: 'ml_c01', review_status: 'pending' } },
    { group: 'nodes', data: { id: 'po:node-001', review_status: 'pending', origin: 'overlay' } },
    { group: 'edges', data: { id: 'po:edge-001', review_status: 'pending', origin: 'overlay' } },
  ] as any[])
  const selectedNodeId = ref<string | null>(null)
  const refreshOverlayPreflight = vi.fn().mockResolvedValue(undefined)
  const setCanvasNodeReviewStatus = vi.fn()
  const setCanvasEdgeReviewStatus = vi.fn()
  const notifySuccess = vi.fn()
  const notifyError = vi.fn()
  const reviewActions = useGraphReviewActions({
    projectId,
    nodes,
    edges,
    elements,
    selectedNodeId,
    refreshOverlayPreflight,
    setCanvasNodeReviewStatus,
    setCanvasEdgeReviewStatus,
    notifySuccess,
    notifyError,
  })
  return {
    projectId,
    nodes,
    edges,
    elements,
    selectedNodeId,
    refreshOverlayPreflight,
    setCanvasNodeReviewStatus,
    setCanvasEdgeReviewStatus,
    notifySuccess,
    notifyError,
    reviewActions,
  }
}

describe('useGraphReviewActions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    confirmMock.mockResolvedValue('confirm')
  })

  it('reviews overlay nodes with confirmation and preflight refresh', async () => {
    reviewOverlayElementMock.mockResolvedValue({ review_status: 'confirmed', planning_enabled: true, validation_status: 'valid' })
    const { reviewActions, elements, selectedNodeId, refreshOverlayPreflight, setCanvasNodeReviewStatus, notifySuccess } = createReviewActions()

    await reviewActions.onReviewNode('po:node-001', 'confirmed')

    expect(confirmMock).toHaveBeenCalled()
    expect(reviewOverlayElementMock).toHaveBeenCalledWith('project-001', 'nodes', 'po:node-001', 'confirmed')
    expect(selectedNodeId.value).toBe('po:node-001')
    expect(elements.value.find((item) => item.data.id === 'po:node-001')?.data.review_status).toBe('confirmed')
    expect(setCanvasNodeReviewStatus).toHaveBeenCalledWith('po:node-001', 'confirmed')
    expect(refreshOverlayPreflight).toHaveBeenCalled()
    expect(notifySuccess).toHaveBeenCalledWith('节点审核状态已更新')
  })

  it('reviews baseline graph nodes without overlay confirmation', async () => {
    reviewNodeMock.mockResolvedValue({})
    const { reviewActions, elements, setCanvasNodeReviewStatus } = createReviewActions()

    await reviewActions.onReviewNode('ml_c01', 'confirmed')

    expect(confirmMock).not.toHaveBeenCalled()
    expect(reviewNodeMock).toHaveBeenCalledWith('project-001', 'ml_c01', 'confirmed')
    expect(elements.value.find((item) => item.data.id === 'ml_c01')?.data.review_status).toBe('confirmed')
    expect(setCanvasNodeReviewStatus).toHaveBeenCalledWith('ml_c01', 'confirmed')
  })

  it('sets overlay planning for edge candidates', async () => {
    setOverlayPlanningMock.mockResolvedValue({ planning_enabled: true })
    const { reviewActions, elements, refreshOverlayPreflight, notifySuccess } = createReviewActions()

    await reviewActions.onSetOverlayPlanning({ id: 'po:edge-001', source: 'po:node-001', target: 'ml_c01', origin: 'overlay' } as any, true)

    expect(confirmMock).toHaveBeenCalled()
    expect(setOverlayPlanningMock).toHaveBeenCalledWith('project-001', 'edges', 'po:edge-001', true)
    expect(elements.value.find((item) => item.data.id === 'po:edge-001')?.data.planning_enabled).toBe(true)
    expect(refreshOverlayPreflight).toHaveBeenCalled()
    expect(notifySuccess).toHaveBeenCalledWith('已允许参与规划')
  })

  it('skips overlay review updates when confirmation is cancelled', async () => {
    confirmMock.mockRejectedValue('cancel')
    const { reviewActions, notifySuccess } = createReviewActions()

    await reviewActions.onReviewNode('po:node-001', 'confirmed')

    expect(reviewOverlayElementMock).not.toHaveBeenCalled()
    expect(notifySuccess).not.toHaveBeenCalled()
  })
})
