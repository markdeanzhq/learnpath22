import { watch, type Ref } from 'vue'
import type { GraphNodeData, GraphScope } from '@/api/modules/graph'
import type { GraphState, GraphWorkspaceLoadOptions } from './useGraphWorkspaceLoader'

type UseGraphWorkspaceOrchestrationOptions = {
  projectId: Readonly<Ref<string | undefined>>
  nodes: Readonly<Ref<GraphNodeData[]>>
  scope: Ref<GraphScope>
  requestedScope: Readonly<Ref<GraphScope>>
  requestedPathId: Readonly<Ref<string | undefined>>
  requestedNodeId: Readonly<Ref<string | null>>
  requestedSessionId: Readonly<Ref<string | null>>
  activeGoalDraftResolutionSessionId: Readonly<Ref<string | null>>
  manualGoalDraftResolutionSessionId: Ref<string | null>
  graphState: Readonly<Ref<GraphState>>
  selectedNodeId: Ref<string | null>
  abortGraphLoad: () => void
  resetGraphState: () => void
  resetOverlayState: () => void
  loadRequestedOverlaySession: () => Promise<void>
  loadGraphWorkspace: (options?: GraphWorkspaceLoadOptions) => Promise<void>
  focusRequestedNode: () => Promise<void>
  openGoalDraftEntry: () => Promise<void>
}

export function useGraphWorkspaceOrchestration({
  projectId,
  nodes,
  scope,
  requestedScope,
  requestedPathId,
  requestedNodeId,
  requestedSessionId,
  activeGoalDraftResolutionSessionId,
  manualGoalDraftResolutionSessionId,
  graphState,
  selectedNodeId,
  abortGraphLoad,
  resetGraphState,
  resetOverlayState,
  loadRequestedOverlaySession,
  loadGraphWorkspace,
  focusRequestedNode,
  openGoalDraftEntry,
}: UseGraphWorkspaceOrchestrationOptions) {
  watch(nodes, (nextNodes) => {
    if (selectedNodeId.value && !nextNodes.some((node) => node.id === selectedNodeId.value)) {
      selectedNodeId.value = null
    }
  })

  watch(
    projectId,
    async (nextProjectId, previousProjectId) => {
      if (!nextProjectId) {
        abortGraphLoad()
        manualGoalDraftResolutionSessionId.value = null
        resetGraphState()
        resetOverlayState()
        return
      }

      if (nextProjectId !== previousProjectId) {
        manualGoalDraftResolutionSessionId.value = null
        resetGraphState()
        resetOverlayState()
      }

      scope.value = requestedScope.value
      await loadGraphWorkspace({
        includePersistedSearchResults: true,
        includeRequestedOverlaySession: true,
        includeGoalDraftEntry: true,
      })
    },
    { immediate: true },
  )

  watch([requestedScope, requestedPathId], async ([nextScope, nextPathId], [previousScope, previousPathId]) => {
    if (!projectId.value || (scope.value === nextScope && nextScope === previousScope && nextPathId === previousPathId)) {
      return
    }

    scope.value = nextScope
    selectedNodeId.value = null
    resetOverlayState()
    await loadGraphWorkspace()
  })

  watch([requestedPathId, requestedNodeId, graphState], async () => {
    await focusRequestedNode()
  })

  async function syncRequestedOverlaySession(nextSessionId: string | null) {
    if (!nextSessionId) {
      resetOverlayState()
      return
    }
    await loadRequestedOverlaySession()
  }

  watch(requestedSessionId, syncRequestedOverlaySession)
  watch(activeGoalDraftResolutionSessionId, async (nextSessionId) => {
    if (!nextSessionId) return
    resetOverlayState()
    await openGoalDraftEntry()
  })

  return {
    syncRequestedOverlaySession,
  }
}
