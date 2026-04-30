import { effectScope, ref, type EffectScope } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useGraphWorkspaceOrchestration } from './useGraphWorkspaceOrchestration'
import type { GraphNodeData, GraphScope } from '@/api/modules/graph'
import type { GraphState } from './useGraphWorkspaceLoader'

let activeScope: EffectScope | null = null

function createOrchestration(overrides: Partial<ReturnType<typeof createRefs>> = {}) {
  const refs = {
    ...createRefs(),
    ...overrides,
  }
  activeScope = effectScope()
  let orchestration!: ReturnType<typeof useGraphWorkspaceOrchestration>
  activeScope.run(() => {
    orchestration = useGraphWorkspaceOrchestration(refs)
  })
  return { ...refs, orchestration }
}

function createRefs() {
  return {
    projectId: ref<string | undefined>(),
    nodes: ref<GraphNodeData[]>([]),
    scope: ref<GraphScope>('path'),
    requestedScope: ref<GraphScope>('path'),
    requestedPathId: ref<string | undefined>('latest'),
    requestedNodeId: ref<string | null>(null),
    requestedSessionId: ref<string | null>(null),
    activeGoalDraftResolutionSessionId: ref<string | null>(null),
    manualGoalDraftResolutionSessionId: ref<string | null>('manual-res'),
    graphState: ref<GraphState>('loading'),
    selectedNodeId: ref<string | null>(null),
    abortGraphLoad: vi.fn(),
    resetGraphState: vi.fn(),
    resetOverlayState: vi.fn(),
    loadRequestedOverlaySession: vi.fn().mockResolvedValue(undefined),
    loadGraphWorkspace: vi.fn().mockResolvedValue(undefined),
    focusRequestedNode: vi.fn().mockResolvedValue(undefined),
    openGoalDraftEntry: vi.fn().mockResolvedValue(undefined),
  }
}

describe('useGraphWorkspaceOrchestration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    activeScope?.stop()
    activeScope = null
  })

  it('aborts and resets state when project is missing', async () => {
    const context = createOrchestration()
    await flushPromises()

    expect(context.abortGraphLoad).toHaveBeenCalled()
    expect(context.manualGoalDraftResolutionSessionId.value).toBeNull()
    expect(context.resetGraphState).toHaveBeenCalled()
    expect(context.resetOverlayState).toHaveBeenCalled()
    expect(context.loadGraphWorkspace).not.toHaveBeenCalled()
  })

  it('loads first-screen workspace with companion data when project exists', async () => {
    const context = createOrchestration({
      projectId: ref<string | undefined>('project-001'),
      requestedScope: ref<GraphScope>('project'),
    })
    await flushPromises()

    expect(context.scope.value).toBe('project')
    expect(context.loadGraphWorkspace).toHaveBeenCalledWith({
      includePersistedSearchResults: true,
      includeRequestedOverlaySession: true,
      includeGoalDraftEntry: true,
    })
  })

  it('resets graph and overlay state when project changes', async () => {
    const context = createOrchestration({ projectId: ref<string | undefined>('project-001') })
    await flushPromises()
    vi.clearAllMocks()
    context.manualGoalDraftResolutionSessionId.value = 'manual-res'

    context.projectId.value = 'project-002'
    await flushPromises()

    expect(context.manualGoalDraftResolutionSessionId.value).toBeNull()
    expect(context.resetGraphState).toHaveBeenCalled()
    expect(context.resetOverlayState).toHaveBeenCalled()
    expect(context.loadGraphWorkspace).toHaveBeenCalled()
  })

  it('reloads workspace when route scope or path changes', async () => {
    const context = createOrchestration({
      projectId: ref<string | undefined>('project-001'),
      selectedNodeId: ref<string | null>('ml_c01'),
    })
    await flushPromises()
    vi.clearAllMocks()

    context.requestedScope.value = 'project'
    context.requestedPathId.value = undefined
    await flushPromises()

    expect(context.scope.value).toBe('project')
    expect(context.selectedNodeId.value).toBeNull()
    expect(context.resetOverlayState).toHaveBeenCalled()
    expect(context.loadGraphWorkspace).toHaveBeenCalledWith()
  })

  it('clears selected node when it disappears from graph nodes', async () => {
    const context = createOrchestration({
      selectedNodeId: ref<string | null>('ml_c01'),
      nodes: ref<GraphNodeData[]>([{ id: 'ml_c01', label: '机器学习导论' } as GraphNodeData]),
    })
    await flushPromises()

    context.nodes.value = []
    await flushPromises()

    expect(context.selectedNodeId.value).toBeNull()
  })

  it('focuses requested node when route node or graph state changes', async () => {
    const context = createOrchestration()
    await flushPromises()
    vi.clearAllMocks()

    context.requestedNodeId.value = 'ml_c01'
    await flushPromises()

    expect(context.focusRequestedNode).toHaveBeenCalled()
  })

  it('syncs requested overlay session from deep link', async () => {
    const context = createOrchestration()
    await flushPromises()
    vi.clearAllMocks()

    context.requestedSessionId.value = 'sess-001'
    await flushPromises()

    expect(context.loadRequestedOverlaySession).toHaveBeenCalled()
  })

  it('resets overlay state when requested overlay session is cleared', async () => {
    const context = createOrchestration({ requestedSessionId: ref<string | null>('sess-001') })
    await flushPromises()
    vi.clearAllMocks()

    await context.orchestration.syncRequestedOverlaySession(null)

    expect(context.resetOverlayState).toHaveBeenCalled()
    expect(context.loadRequestedOverlaySession).not.toHaveBeenCalled()
  })

  it('opens goal draft entry when active resolution session appears', async () => {
    const context = createOrchestration()
    await flushPromises()
    vi.clearAllMocks()

    context.activeGoalDraftResolutionSessionId.value = 'res-001'
    await flushPromises()

    expect(context.resetOverlayState).toHaveBeenCalled()
    expect(context.openGoalDraftEntry).toHaveBeenCalled()
  })
})
