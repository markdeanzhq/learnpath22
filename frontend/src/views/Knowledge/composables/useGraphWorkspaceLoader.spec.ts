import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useGraphWorkspaceLoader } from './useGraphWorkspaceLoader'
import type { GraphWorkspaceData, GraphWorkspaceParams } from '@/api/modules/graph'
import type { OverlaySessionView } from './useOverlayCandidateWorkflow'

const {
  getGraphWorkspaceMock,
  getOverlayProjectionStatusMock,
  getOverlayPreflightMock,
  getOverlayExtractionSessionMock,
  listPersistedResultsMock,
} = vi.hoisted(() => ({
  getGraphWorkspaceMock: vi.fn(),
  getOverlayProjectionStatusMock: vi.fn(),
  getOverlayPreflightMock: vi.fn(),
  getOverlayExtractionSessionMock: vi.fn(),
  listPersistedResultsMock: vi.fn(),
}))

vi.mock('@/api/modules/graph', () => ({
  graphApi: {
    getGraphWorkspace: getGraphWorkspaceMock,
    getOverlayProjectionStatus: getOverlayProjectionStatusMock,
    getOverlayPreflight: getOverlayPreflightMock,
    getOverlayExtractionSession: getOverlayExtractionSessionMock,
  },
}))

vi.mock('@/api/modules/search', () => ({
  searchApi: {
    listPersistedResults: listPersistedResultsMock,
  },
}))

function createWorkspace(overrides: Partial<GraphWorkspaceData> = {}): GraphWorkspaceData {
  return {
    project_id: 'project-001',
    graph: {
      scope: 'project',
      elements: [
        { group: 'nodes', data: { id: 'ml_c01', label: '机器学习导论' } },
      ],
      is_empty: false,
      path_id: null,
    },
    projection_status: {
      project_id: 'project-001',
      status: 'ok',
      ready: true,
      in_sync: true,
    },
    overlay_preflight: {
      project_id: 'project-001',
      status: 'ok',
      summary: 'ok',
      counts: {
        active_nodes: 0,
        active_edges: 0,
        visible_overlay_nodes: 0,
        visible_overlay_edges: 0,
        path_overlay_nodes: 0,
        path_overlay_edges: 0,
        blocking_items: 0,
        warning_items: 0,
        nodes: { total: 0, valid: 0, confirmed: 0, pending_review: 0, planning_disabled: 0, invalid: 0 },
        edges: { total: 0, valid: 0, confirmed: 0, pending_review: 0, planning_disabled: 0, invalid: 0 },
      },
      visible_overlay_node_ids: [],
      visible_overlay_edge_ids: [],
      path_overlay_node_ids: [],
      path_overlay_edge_ids: [],
      ignored_overlay_edge_ids: [],
      shadowed_edge_ids: [],
      cycle_edge_ids: [],
      blocking_items: [],
      warning_items: [],
      project_graph_hash: 'hash-001',
    },
    persisted_search_results: null,
    overlay_session: null,
    goal_draft_proposal: null,
    ...overrides,
  }
}

function createLoader() {
  const projectId = ref<string | undefined>('project-001')
  const graphQuery = ref<GraphWorkspaceParams>({ scope: 'project' })
  const requestedSessionId = ref<string | null>(null)
  const activeGoalDraftResolutionSessionId = ref<string | null>(null)
  const overlayDrawerVisible = ref(false)
  const overlayError = ref('')
  const lastOverlaySession = ref<OverlaySessionView | null>(null)
  const selectedNodeId = ref<string | null>(null)
  const goalDraftProposalLoading = ref(false)
  const resetOverlayState = vi.fn()
  const prepareWorkspaceGoalDraftLoading = vi.fn()
  const applyWorkspaceGoalDraftProposal = vi.fn()
  const refreshGraphCacheStats = vi.fn().mockResolvedValue(undefined)
  const focusRequestedNode = vi.fn().mockResolvedValue(undefined)
  const notifyError = vi.fn()
  const loader = useGraphWorkspaceLoader({
    projectId,
    graphQuery,
    requestedSessionId,
    activeGoalDraftResolutionSessionId,
    overlayDrawerVisible,
    overlayError,
    lastOverlaySession,
    selectedNodeId,
    goalDraftProposalLoading,
    resetOverlayState,
    prepareWorkspaceGoalDraftLoading,
    applyWorkspaceGoalDraftProposal,
    refreshGraphCacheStats,
    focusRequestedNode,
    notifyError,
  })
  return {
    projectId,
    graphQuery,
    requestedSessionId,
    activeGoalDraftResolutionSessionId,
    overlayDrawerVisible,
    overlayError,
    lastOverlaySession,
    selectedNodeId,
    goalDraftProposalLoading,
    resetOverlayState,
    prepareWorkspaceGoalDraftLoading,
    applyWorkspaceGoalDraftProposal,
    refreshGraphCacheStats,
    focusRequestedNode,
    notifyError,
    loader,
  }
}

describe('useGraphWorkspaceLoader', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads graph workspace and optional companion data', async () => {
    const workspace = createWorkspace({
      persisted_search_results: [{ result_id: 'result-001', title: '搜索结果' } as any],
      overlay_session: { session: { session_id: 'sess-001' }, nodes: [], edges: [], resources: [] } as any,
      goal_draft_proposal: { resolution_session_id: 'res-001', project_id: 'project-001', session_status: 'draft_previewed', draft_proposal: { counts: { nodes: 1, edges: 0, resources: 0 }, nodes: [], edges: [], resources: [], missing_concepts: [] } } as any,
    })
    getGraphWorkspaceMock.mockResolvedValue(workspace)
    const context = createLoader()
    context.requestedSessionId.value = 'sess-001'
    context.activeGoalDraftResolutionSessionId.value = 'res-001'

    await context.loader.loadGraphWorkspace({
      includePersistedSearchResults: true,
      includeRequestedOverlaySession: true,
      includeGoalDraftEntry: true,
    })

    expect(getGraphWorkspaceMock).toHaveBeenCalledWith('project-001', expect.objectContaining({
      scope: 'project',
      include_persisted_search_results: true,
      session_id: 'sess-001',
      goal_draft_resolution_session_id: 'res-001',
    }), expect.objectContaining({ silent: true }))
    expect(context.loader.elements.value).toHaveLength(1)
    expect(context.loader.graphState.value).toBe('ready')
    expect(context.loader.persistedSearchResults.value).toHaveLength(1)
    expect(context.lastOverlaySession.value?.session.session_id).toBe('sess-001')
    expect(context.overlayDrawerVisible.value).toBe(true)
    expect(context.prepareWorkspaceGoalDraftLoading).toHaveBeenCalled()
    expect(context.applyWorkspaceGoalDraftProposal).toHaveBeenCalledWith(workspace.goal_draft_proposal)
    expect(context.goalDraftProposalLoading.value).toBe(false)
    expect(context.refreshGraphCacheStats).toHaveBeenCalled()
    expect(context.focusRequestedNode).toHaveBeenCalled()
  })

  it('keeps existing graph visible when a refresh fails', async () => {
    getGraphWorkspaceMock.mockResolvedValueOnce(createWorkspace())
    const context = createLoader()
    await context.loader.loadGraphWorkspace()

    getGraphWorkspaceMock.mockRejectedValueOnce(new Error('network down'))
    await context.loader.loadGraphWorkspace()

    expect(context.loader.graphState.value).toBe('ready')
    expect(context.loader.lastRefreshError.value).toBe('network down')
    expect(context.notifyError).toHaveBeenCalledWith('network down')
  })

  it('ignores canceled workspace requests', async () => {
    getGraphWorkspaceMock.mockRejectedValue({ code: 'ERR_CANCELED', message: 'canceled' })
    const context = createLoader()

    await context.loader.loadGraphWorkspace()

    expect(context.loader.loading.value).toBe(false)
    expect(context.loader.errorMessage.value).toBe('')
    expect(context.notifyError).not.toHaveBeenCalled()
  })

  it('loads independent projection, preflight, persisted search and requested session state', async () => {
    getOverlayProjectionStatusMock.mockResolvedValue({ project_id: 'project-001', status: 'ok', ready: true, in_sync: true })
    getOverlayPreflightMock.mockResolvedValue(createWorkspace().overlay_preflight)
    listPersistedResultsMock.mockResolvedValue([{ result_id: 'result-001', title: '搜索结果' }])
    getOverlayExtractionSessionMock.mockResolvedValue({ session: { session_id: 'sess-001' }, nodes: [], edges: [], resources: [] })
    const context = createLoader()
    context.requestedSessionId.value = 'sess-001'

    await context.loader.loadProjectionStatus()
    await context.loader.loadOverlayPreflight()
    await context.loader.loadPersistedSearchResults()
    await context.loader.loadRequestedOverlaySession()

    expect(context.loader.projectionStatus.value?.status).toBe('ok')
    expect(context.loader.overlayPreflight.value?.status).toBe('ok')
    expect(context.loader.persistedSearchResults.value).toHaveLength(1)
    expect(context.lastOverlaySession.value?.session.session_id).toBe('sess-001')
    expect(context.overlayDrawerVisible.value).toBe(true)
  })

  it('maps projection and optional overlay session errors into UI state', async () => {
    getOverlayProjectionStatusMock.mockRejectedValue(new Error('offline'))
    const context = createLoader()

    await context.loader.loadProjectionStatus()

    expect(context.loader.projectionStatus.value?.status).toBe('error')

    getGraphWorkspaceMock.mockResolvedValue(createWorkspace({
      overlay_session_error: '扩展会话不可用',
      overlay_session_error_detail: { code: 'SESSION_MISSING', message: '扩展会话不可用', source: 'overlay_session', recoverable: true },
    }))
    context.requestedSessionId.value = 'sess-missing'

    await context.loader.loadGraphWorkspace({ includeRequestedOverlaySession: true })

    expect(context.resetOverlayState).toHaveBeenCalled()
    expect(context.overlayError.value).toBe('扩展会话不可用')
  })
})
