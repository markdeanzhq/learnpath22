import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useGraphToolbarActions, type GraphLayout } from './useGraphToolbarActions'
import type { GraphElement, GraphScope } from '@/api/modules/graph'
import type { GraphState } from './useGraphWorkspaceLoader'

const { syncGraphMock } = vi.hoisted(() => ({
  syncGraphMock: vi.fn(),
}))

vi.mock('@/api/modules/graph', () => ({
  graphApi: {
    syncGraph: syncGraphMock,
  },
}))

function createActions(overrides: Partial<ReturnType<typeof createRefs>> = {}) {
  const refs = {
    projectId: ref<string | undefined>('project-001'),
    scope: ref<GraphScope>('path'),
    layout: ref<GraphLayout>('cose'),
    elements: ref<GraphElement[]>([{ group: 'nodes', data: { id: 'ml_c01' } } as GraphElement]),
    selectedNodeId: ref<string | null>('ml_c01'),
    syncing: ref(false),
    errorMessage: ref('old error'),
    lastRefreshError: ref('old refresh error'),
    emptyReason: ref<string | undefined>('old reason'),
    graphState: ref<GraphState>('ready'),
    graphRef: ref({
      zoomIn: vi.fn(),
      zoomOut: vi.fn(),
      fitView: vi.fn(),
      highlightBySearch: vi.fn(),
    }),
    resetOverlayState: vi.fn(),
    replaceGraphRoute: vi.fn().mockResolvedValue(undefined),
    loadGraphWorkspace: vi.fn().mockResolvedValue(undefined),
    notifySuccess: vi.fn(),
    notifyError: vi.fn(),
    ...overrides,
  }
  const actions = useGraphToolbarActions(refs)
  return { ...refs, actions }
}

function createRefs() {
  return {
    projectId: ref<string | undefined>('project-001'),
    scope: ref<GraphScope>('path'),
    layout: ref<GraphLayout>('cose'),
    elements: ref<GraphElement[]>([]),
    selectedNodeId: ref<string | null>(null),
    syncing: ref(false),
    errorMessage: ref(''),
    lastRefreshError: ref(''),
    emptyReason: ref<string | undefined>(),
    graphState: ref<GraphState>('ready'),
    graphRef: ref(),
    resetOverlayState: vi.fn(),
    replaceGraphRoute: vi.fn().mockResolvedValue(undefined),
    loadGraphWorkspace: vi.fn().mockResolvedValue(undefined),
    notifySuccess: vi.fn(),
    notifyError: vi.fn(),
  }
}

describe('useGraphToolbarActions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('updates layout and proxies canvas actions', () => {
    const context = createActions()

    context.actions.onLayoutChange('breadthfirst')
    context.actions.onSearch('逻辑回归')
    context.actions.onZoomIn()
    context.actions.onZoomOut()
    context.actions.onFitView()

    expect(context.layout.value).toBe('breadthfirst')
    expect(context.graphRef.value?.highlightBySearch).toHaveBeenCalledWith('逻辑回归')
    expect(context.graphRef.value?.zoomIn).toHaveBeenCalled()
    expect(context.graphRef.value?.zoomOut).toHaveBeenCalled()
    expect(context.graphRef.value?.fitView).toHaveBeenCalled()
  })

  it('writes selected node into route on node click', () => {
    const context = createActions()

    context.actions.onNodeClick({ id: 'ml_c02' } as any)

    expect(context.selectedNodeId.value).toBe('ml_c02')
    expect(context.replaceGraphRoute).toHaveBeenCalledWith('path', 'ml_c02')
  })

  it('changes graph scope and refreshes workspace', async () => {
    const context = createActions()

    await context.actions.onScopeChange('project')

    expect(context.scope.value).toBe('project')
    expect(context.selectedNodeId.value).toBeNull()
    expect(context.resetOverlayState).toHaveBeenCalled()
    expect(context.replaceGraphRoute).toHaveBeenCalledWith('project')
    expect(context.loadGraphWorkspace).toHaveBeenCalled()
  })

  it('skips graph scope refresh when scope is unchanged', async () => {
    const context = createActions()

    await context.actions.onScopeChange('path')

    expect(context.resetOverlayState).not.toHaveBeenCalled()
    expect(context.replaceGraphRoute).not.toHaveBeenCalled()
    expect(context.loadGraphWorkspace).not.toHaveBeenCalled()
  })

  it('refreshes workspace on demand', async () => {
    const context = createActions()

    await context.actions.onRefresh()

    expect(context.loadGraphWorkspace).toHaveBeenCalled()
  })

  it('syncs graph and reloads workspace on success', async () => {
    syncGraphMock.mockResolvedValue({})
    const context = createActions()

    await context.actions.onSync()

    expect(syncGraphMock).toHaveBeenCalledWith('project-001')
    expect(context.errorMessage.value).toBe('')
    expect(context.notifySuccess).toHaveBeenCalledWith('知识图谱同步成功')
    expect(context.loadGraphWorkspace).toHaveBeenCalled()
    expect(context.syncing.value).toBe(false)
  })

  it('keeps existing graph visible when sync fails after data is loaded', async () => {
    syncGraphMock.mockRejectedValue(new Error('offline'))
    const context = createActions()

    await context.actions.onSync()

    expect(context.errorMessage.value).toBe('offline')
    expect(context.lastRefreshError.value).toBe('offline')
    expect(context.graphState.value).toBe('ready')
    expect(context.notifyError).toHaveBeenCalledWith('offline')
    expect(context.syncing.value).toBe(false)
  })

  it('moves empty initial graph into error state when sync fails', async () => {
    syncGraphMock.mockRejectedValue({ response: { data: { error: 'sync failed' } } })
    const context = createActions({
      elements: ref<GraphElement[]>([]),
      graphState: ref<GraphState>('ready'),
    })

    await context.actions.onSync()

    expect(context.errorMessage.value).toBe('sync failed')
    expect(context.lastRefreshError.value).toBe('')
    expect(context.emptyReason.value).toBeUndefined()
    expect(context.graphState.value).toBe('error')
    expect(context.notifyError).toHaveBeenCalledWith('sync failed')
  })

  it('skips sync when project is missing', async () => {
    const context = createActions({ projectId: ref<string | undefined>() })

    await context.actions.onSync()

    expect(syncGraphMock).not.toHaveBeenCalled()
    expect(context.loadGraphWorkspace).not.toHaveBeenCalled()
  })
})
