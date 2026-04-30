import { type Ref } from 'vue'
import {
  graphApi,
  type GraphElement,
  type GraphNodeData,
  type GraphScope,
} from '@/api/modules/graph'
import type { GraphState } from './useGraphWorkspaceLoader'

export type GraphLayout = 'cose' | 'breadthfirst'

export type GraphCanvasActionHandle = {
  zoomIn: () => void
  zoomOut: () => void
  fitView: () => void
  highlightBySearch: (keyword: string) => void
}

type UseGraphToolbarActionsOptions = {
  projectId: Readonly<Ref<string | undefined>>
  scope: Ref<GraphScope>
  layout: Ref<GraphLayout>
  elements: Readonly<Ref<GraphElement[]>>
  selectedNodeId: Ref<string | null>
  syncing: Ref<boolean>
  errorMessage: Ref<string>
  lastRefreshError: Ref<string>
  emptyReason: Ref<string | undefined>
  graphState: Ref<GraphState>
  graphRef: Ref<GraphCanvasActionHandle | undefined>
  resetOverlayState: () => void
  replaceGraphRoute: (scope: GraphScope, nodeId?: string | null) => Promise<void>
  loadGraphWorkspace: () => Promise<void>
  notifySuccess: (message: string) => void
  notifyError: (message: string) => void
}

export function useGraphToolbarActions({
  projectId,
  scope,
  layout,
  elements,
  selectedNodeId,
  syncing,
  errorMessage,
  lastRefreshError,
  emptyReason,
  graphState,
  graphRef,
  resetOverlayState,
  replaceGraphRoute,
  loadGraphWorkspace,
  notifySuccess,
  notifyError,
}: UseGraphToolbarActionsOptions) {
  function onLayoutChange(newLayout: string) {
    layout.value = newLayout as GraphLayout
  }

  function onNodeClick(data: GraphNodeData) {
    selectedNodeId.value = data.id
    void replaceGraphRoute(scope.value, data.id)
  }

  function onSearch(keyword: string) {
    graphRef.value?.highlightBySearch(keyword)
  }

  function onZoomIn() {
    graphRef.value?.zoomIn()
  }

  function onZoomOut() {
    graphRef.value?.zoomOut()
  }

  function onFitView() {
    graphRef.value?.fitView()
  }

  async function onScopeChange(nextScope: GraphScope) {
    if (scope.value === nextScope) return
    scope.value = nextScope
    selectedNodeId.value = null
    resetOverlayState()
    await replaceGraphRoute(nextScope)
    await loadGraphWorkspace()
  }

  async function onRefresh() {
    await loadGraphWorkspace()
  }

  async function onSync() {
    const currentProjectId = projectId.value
    if (!currentProjectId) return

    const hasExistingGraph = elements.value.length > 0

    syncing.value = true
    errorMessage.value = ''

    try {
      await graphApi.syncGraph(currentProjectId)
      notifySuccess('知识图谱同步成功')
      await loadGraphWorkspace()
    } catch (e: any) {
      const message = e?.response?.data?.error || e?.message || '知识图谱同步失败，请稍后重试'
      errorMessage.value = message

      if (hasExistingGraph) {
        lastRefreshError.value = message
        notifyError(message)
        return
      }

      lastRefreshError.value = ''

      if (graphState.value !== 'empty') {
        emptyReason.value = undefined
        graphState.value = 'error'
      }

      notifyError(message)
    } finally {
      syncing.value = false
    }
  }

  return {
    onLayoutChange,
    onNodeClick,
    onSearch,
    onZoomIn,
    onZoomOut,
    onFitView,
    onScopeChange,
    onRefresh,
    onSync,
  }
}
