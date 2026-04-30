import { ref, type Ref } from 'vue'
import {
  graphApi,
  type GraphData,
  type GraphElement,
  type GraphWorkspaceData,
  type GraphWorkspaceParams,
  type OverlayPreflightResponse,
  type OverlayProjectionStatusResponse,
} from '@/api/modules/graph'
import { searchApi, type PersistedSearchResult } from '@/api/modules/search'
import { isCanceledRequest } from '@/api/request'
import type { OverlaySessionView } from './useOverlayCandidateWorkflow'

export type GraphState = 'loading' | 'ready' | 'empty' | 'error'

export type GraphWorkspaceLoadOptions = {
  includePersistedSearchResults?: boolean
  includeRequestedOverlaySession?: boolean
  includeGoalDraftEntry?: boolean
}

type UseGraphWorkspaceLoaderOptions = {
  projectId: Readonly<Ref<string | undefined>>
  graphQuery: Readonly<Ref<GraphWorkspaceParams>>
  requestedSessionId: Readonly<Ref<string | null>>
  activeGoalDraftResolutionSessionId: Readonly<Ref<string | null>>
  overlayDrawerVisible: Ref<boolean>
  overlayError: Ref<string>
  lastOverlaySession: Ref<OverlaySessionView | null>
  selectedNodeId: Ref<string | null>
  goalDraftProposalLoading: Ref<boolean>
  resetOverlayState: () => void
  prepareWorkspaceGoalDraftLoading: () => void
  applyWorkspaceGoalDraftProposal: (proposal: GraphWorkspaceData['goal_draft_proposal']) => void
  refreshGraphCacheStats: () => Promise<void>
  focusRequestedNode: () => Promise<void>
  notifyError: (message: string) => void
}

export function useGraphWorkspaceLoader({
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
}: UseGraphWorkspaceLoaderOptions) {
  const elements = ref<GraphElement[]>([])
  const graphState = ref<GraphState>('loading')
  const loading = ref(false)
  const errorMessage = ref('')
  const lastRefreshError = ref('')
  const emptyReason = ref<string | undefined>()
  const projectionStatus = ref<OverlayProjectionStatusResponse | null>(null)
  const overlayPreflight = ref<OverlayPreflightResponse | null>(null)
  const persistedSearchResults = ref<PersistedSearchResult[]>([])
  let graphLoadRequestId = 0
  let graphLoadController: AbortController | null = null

  function resetGraphState() {
    elements.value = []
    selectedNodeId.value = null
    errorMessage.value = ''
    lastRefreshError.value = ''
    emptyReason.value = undefined
    graphState.value = 'loading'
    projectionStatus.value = null
    overlayPreflight.value = null
  }

  function createGraphLoadController() {
    graphLoadController?.abort()
    graphLoadController = new AbortController()
    return graphLoadController
  }

  function clearGraphLoadController(controller: AbortController) {
    if (graphLoadController === controller) {
      graphLoadController = null
    }
  }

  function abortGraphLoad() {
    graphLoadController?.abort()
    graphLoadController = null
  }

  async function loadPersistedSearchResults() {
    const currentProjectId = projectId.value
    if (!currentProjectId) {
      persistedSearchResults.value = []
      return
    }
    const results = await searchApi.listPersistedResults(currentProjectId)
    if (projectId.value === currentProjectId) {
      persistedSearchResults.value = results
    }
  }

  async function loadProjectionStatus() {
    const currentProjectId = projectId.value
    if (!currentProjectId) {
      projectionStatus.value = null
      return
    }
    try {
      const status = await graphApi.getOverlayProjectionStatus(currentProjectId)
      if (projectId.value === currentProjectId) {
        projectionStatus.value = status
      }
    } catch {
      if (projectId.value === currentProjectId) {
        projectionStatus.value = {
          project_id: currentProjectId,
          status: 'error',
          ready: false,
          in_sync: false,
          reason: 'projection_status_unavailable',
        }
      }
    }
  }

  async function loadOverlayPreflight() {
    const currentProjectId = projectId.value
    if (!currentProjectId) {
      overlayPreflight.value = null
      return
    }
    try {
      const preflight = await graphApi.getOverlayPreflight(currentProjectId)
      if (projectId.value === currentProjectId) {
        overlayPreflight.value = preflight
      }
    } catch {
      if (projectId.value === currentProjectId) {
        overlayPreflight.value = null
      }
    }
  }

  function applyGraphData(data: GraphData) {
    const nextElements = data.elements ?? []

    elements.value = nextElements
    errorMessage.value = ''
    lastRefreshError.value = ''
    emptyReason.value = data.empty_reason
    graphState.value = nextElements.length > 0 ? 'ready' : 'empty'
  }

  async function loadRequestedOverlaySession() {
    const currentProjectId = projectId.value
    const currentSessionId = requestedSessionId.value
    if (!currentProjectId || !currentSessionId) {
      return
    }

    try {
      const session = await graphApi.getOverlayExtractionSession(
        currentProjectId,
        currentSessionId,
      )
      if (projectId.value !== currentProjectId || requestedSessionId.value !== currentSessionId) {
        return
      }
      lastOverlaySession.value = session
      overlayDrawerVisible.value = true
    } catch (error: any) {
      if (projectId.value !== currentProjectId || requestedSessionId.value !== currentSessionId) {
        return
      }
      resetOverlayState()
      overlayError.value = error?.response?.data?.error || '扩展抽取会话加载失败'
    }
  }

  async function loadGraphWorkspace(options: GraphWorkspaceLoadOptions = {}) {
    const currentProjectId = projectId.value
    const currentGraphQuery = graphQuery.value
    const currentSessionId = options.includeRequestedOverlaySession ? requestedSessionId.value : null
    const currentGoalDraftResolutionSessionId = options.includeGoalDraftEntry ? activeGoalDraftResolutionSessionId.value : null
    const requestId = ++graphLoadRequestId

    if (!currentProjectId) {
      abortGraphLoad()
      resetGraphState()
      loading.value = false
      return
    }

    const controller = createGraphLoadController()
    const loadStartedAt = performanceNow()
    const hasExistingGraph = elements.value.length > 0
    if (!hasExistingGraph) {
      graphState.value = 'loading'
    }

    if (currentGoalDraftResolutionSessionId) {
      prepareWorkspaceGoalDraftLoading()
    }

    loading.value = true
    errorMessage.value = ''

    try {
      const workspace: GraphWorkspaceData = await graphApi.getGraphWorkspace(currentProjectId, {
        ...currentGraphQuery,
        include_persisted_search_results: options.includePersistedSearchResults,
        session_id: currentSessionId,
        goal_draft_resolution_session_id: currentGoalDraftResolutionSessionId,
      }, {
        signal: controller.signal,
        silent: true,
      })
      const requestDurationMs = Math.round(performanceNow() - loadStartedAt)
      if (requestId !== graphLoadRequestId || projectId.value !== currentProjectId) {
        logKnowledgePerformance('workspace_stale_response', {
          project_id: currentProjectId,
          scope: currentGraphQuery.scope,
          path_id: currentGraphQuery.path_id,
          duration_ms: requestDurationMs,
        })
        return
      }

      applyGraphData(workspace.graph)
      projectionStatus.value = workspace.projection_status
      overlayPreflight.value = workspace.overlay_preflight ?? null

      if (options.includePersistedSearchResults) {
        persistedSearchResults.value = workspace.persisted_search_results ?? []
      }

      applyOptionalOverlaySession(workspace, currentSessionId)
      applyOptionalGoalDraft(workspace, currentGoalDraftResolutionSessionId)
      logWorkspaceLoaded(workspace, currentGraphQuery, currentProjectId, requestDurationMs)
      void refreshGraphCacheStats()
    } catch (e: any) {
      const durationMs = Math.round(performanceNow() - loadStartedAt)
      if (isCanceledRequest(e)) {
        logKnowledgePerformance('workspace_canceled', {
          project_id: currentProjectId,
          scope: currentGraphQuery.scope,
          path_id: currentGraphQuery.path_id,
          duration_ms: durationMs,
        })
        return
      }
      if (requestId !== graphLoadRequestId || projectId.value !== currentProjectId) {
        return
      }
      const message = e?.response?.data?.error || e?.message || '知识图谱加载失败，请稍后重试'

      logKnowledgePerformance('workspace_failed', {
        project_id: currentProjectId,
        scope: currentGraphQuery.scope,
        path_id: currentGraphQuery.path_id,
        duration_ms: durationMs,
        message,
      })
      errorMessage.value = message
      if (hasExistingGraph) {
        lastRefreshError.value = message
        graphState.value = 'ready'
        notifyError(message)
      } else {
        selectedNodeId.value = null
        lastRefreshError.value = ''
        emptyReason.value = undefined
        graphState.value = 'error'
      }
    } finally {
      clearGraphLoadController(controller)
      if (requestId === graphLoadRequestId && projectId.value === currentProjectId) {
        loading.value = false
        if (currentGoalDraftResolutionSessionId) {
          goalDraftProposalLoading.value = false
        }
      }
    }

    await focusRequestedNode()
  }

  function applyOptionalOverlaySession(workspace: GraphWorkspaceData, currentSessionId: string | null) {
    if (!currentSessionId) return
    const overlaySessionError = workspaceErrorMessage(
      workspace.overlay_session_error_detail,
      workspace.overlay_session_error,
    )
    if (overlaySessionError) {
      resetOverlayState()
      overlayError.value = overlaySessionError
    } else if (workspace.overlay_session) {
      lastOverlaySession.value = workspace.overlay_session
      overlayDrawerVisible.value = true
    }
  }

  function applyOptionalGoalDraft(workspace: GraphWorkspaceData, currentGoalDraftResolutionSessionId: string | null) {
    if (!currentGoalDraftResolutionSessionId) return
    applyWorkspaceGoalDraftProposal(workspace.goal_draft_proposal)
    const goalDraftError = workspaceErrorMessage(
      workspace.goal_draft_error_detail,
      workspace.goal_draft_error,
    )
    if (goalDraftError) {
      overlayError.value = goalDraftError
    }
  }

  function logWorkspaceLoaded(
    workspace: GraphWorkspaceData,
    currentGraphQuery: GraphWorkspaceParams,
    currentProjectId: string,
    requestDurationMs: number,
  ) {
    logKnowledgePerformance('workspace_loaded', {
      project_id: currentProjectId,
      scope: workspace.graph.scope,
      path_id: workspace.graph.path_id ?? currentGraphQuery.path_id ?? null,
      duration_ms: requestDurationMs,
      elements: workspace.graph.elements?.length ?? 0,
      optional_errors: [
        workspace.overlay_preflight_error_detail?.code,
        workspace.persisted_search_results_error_detail?.code,
        workspace.overlay_session_error_detail?.code,
        workspace.goal_draft_error_detail?.code,
      ].filter(Boolean),
    })
  }

  return {
    elements,
    graphState,
    loading,
    errorMessage,
    lastRefreshError,
    emptyReason,
    projectionStatus,
    overlayPreflight,
    persistedSearchResults,
    resetGraphState,
    abortGraphLoad,
    loadPersistedSearchResults,
    loadProjectionStatus,
    loadOverlayPreflight,
    loadRequestedOverlaySession,
    loadGraphWorkspace,
  }
}

function workspaceErrorMessage(detail?: { message?: string } | null, fallback?: string | null) {
  return detail?.message || fallback || ''
}

function performanceNow() {
  return typeof performance !== 'undefined' ? performance.now() : Date.now()
}

function logKnowledgePerformance(event: string, payload: Record<string, unknown>) {
  if (!import.meta.env.DEV || typeof console === 'undefined') {
    return
  }
  console.debug('[Knowledge performance]', { event, ...payload })
}
