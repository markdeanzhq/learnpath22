import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useOverlayPostActions } from './useOverlayPostActions'
import type { OverlaySessionView } from './useOverlayCandidateWorkflow'

const {
  bindProjectResourceMock,
  getOverlayExtractionSessionMock,
  previewOverlayPromotionMock,
  commitOverlayPromotionMock,
} = vi.hoisted(() => ({
  bindProjectResourceMock: vi.fn(),
  getOverlayExtractionSessionMock: vi.fn(),
  previewOverlayPromotionMock: vi.fn(),
  commitOverlayPromotionMock: vi.fn(),
}))

vi.mock('@/api/modules/resource', () => ({
  resourceApi: {
    bindProjectResource: bindProjectResourceMock,
  },
}))

vi.mock('@/api/modules/graph', () => ({
  graphApi: {
    getOverlayExtractionSession: getOverlayExtractionSessionMock,
    previewOverlayPromotion: previewOverlayPromotionMock,
    commitOverlayPromotion: commitOverlayPromotionMock,
  },
}))

function createPostActions() {
  const projectId = ref<string | undefined>('project-001')
  const nodes = ref([
    { id: 'ml_c01', label: '机器学习导论' },
    { id: 'po:node-001', label: '' },
  ] as any[])
  const lastOverlaySession = ref<OverlaySessionView | null>({
    session: { session_id: 'sess-001' },
    nodes: [],
    edges: [],
    resources: [],
  } as unknown as OverlaySessionView)
  const overlayError = ref('')
  const refreshProjectionStatus = vi.fn().mockResolvedValue(undefined)
  const refreshGraphWorkspace = vi.fn().mockResolvedValue(undefined)
  const notifySuccess = vi.fn()
  const postActions = useOverlayPostActions({
    projectId,
    nodes,
    lastOverlaySession,
    overlayError,
    refreshProjectionStatus,
    refreshGraphWorkspace,
    notifySuccess,
  })
  return {
    projectId,
    nodes,
    lastOverlaySession,
    overlayError,
    refreshProjectionStatus,
    refreshGraphWorkspace,
    notifySuccess,
    postActions,
  }
}

describe('useOverlayPostActions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('binds overlay resources and refreshes session state', async () => {
    const refreshedSession = { session: { session_id: 'sess-001' }, nodes: [], edges: [], resources: [{ resource_id: 'res-001' }] } as any
    bindProjectResourceMock.mockResolvedValue({ id: 'binding-001' })
    getOverlayExtractionSessionMock.mockResolvedValue(refreshedSession)
    const { postActions, lastOverlaySession, refreshProjectionStatus, notifySuccess } = createPostActions()

    postActions.resourceBinding.value = {
      resourceId: 'res-001',
      targetType: 'project_node',
      targetId: '  ml_c01  ',
    }
    await postActions.bindOverlayResource()

    expect(bindProjectResourceMock).toHaveBeenCalledWith('project-001', {
      resource_id: 'res-001',
      target_type: 'project_node',
      target_id: 'ml_c01',
      binding_source: 'overlay',
    })
    expect(getOverlayExtractionSessionMock).toHaveBeenCalledWith('project-001', 'sess-001')
    expect(lastOverlaySession.value).toEqual(refreshedSession)
    expect(refreshProjectionStatus).toHaveBeenCalled()
    expect(notifySuccess).toHaveBeenCalledWith('资源绑定已保存')
  })

  it('previews and commits overlay promotion', async () => {
    previewOverlayPromotionMock.mockResolvedValue({ status: 'ready', candidate_count: 2 })
    commitOverlayPromotionMock.mockResolvedValue({ status: 'promoted', reason: 'promoted' })
    getOverlayExtractionSessionMock.mockResolvedValue({ session: { session_id: 'sess-001' }, nodes: [], edges: [], resources: [] })
    const { postActions, refreshGraphWorkspace } = createPostActions()

    await postActions.previewPromotion()
    expect(postActions.promotionPreview.value?.candidate_count).toBe(2)

    postActions.promotionSecret.value = 'secret'
    await postActions.commitPromotion()

    expect(commitOverlayPromotionMock).toHaveBeenCalledWith('project-001', {
      admin_secret: 'secret',
      requested_by: 'frontend',
    })
    expect(postActions.promotionSecret.value).toBe('')
    expect(postActions.promotionStatusMessage.value).toBe('推广成功，候选已归档隐藏。')
    expect(refreshGraphWorkspace).toHaveBeenCalled()
  })

  it('validates promotion secret before committing', async () => {
    const { postActions, overlayError } = createPostActions()

    await postActions.commitPromotion()

    expect(overlayError.value).toBe('请输入 admin secret')
    expect(commitOverlayPromotionMock).not.toHaveBeenCalled()
  })

  it('resets post-action state', () => {
    const { postActions } = createPostActions()
    postActions.promotionPreview.value = { status: 'ready' }
    postActions.promotionResult.value = { status: 'promoted' }
    postActions.promotionSecret.value = 'secret'
    postActions.resourceBinding.value = { resourceId: 'res-001', targetType: 'project_node', targetId: 'ml_c01' }

    postActions.resetOverlayPostActions()

    expect(postActions.promotionPreview.value).toBeNull()
    expect(postActions.promotionResult.value).toBeNull()
    expect(postActions.promotionSecret.value).toBe('')
    expect(postActions.resourceBinding.value).toEqual({ resourceId: '', targetType: 'project_node', targetId: '' })
  })
})
