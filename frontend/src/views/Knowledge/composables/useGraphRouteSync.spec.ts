import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useGraphRouteSync } from './useGraphRouteSync'

const {
  routeState,
  replaceMock,
} = vi.hoisted(() => ({
  routeState: {
    query: {} as Record<string, unknown>,
  },
  replaceMock: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ replace: replaceMock }),
}))

describe('useGraphRouteSync', () => {
  beforeEach(() => {
    routeState.query = {}
    replaceMock.mockClear()
  })

  it('normalizes invalid scope to latest path graph', () => {
    routeState.query = { scope: 'bad-scope' }

    const routeSync = useGraphRouteSync()

    expect(routeSync.scope.value).toBe('path')
    expect(routeSync.requestedScope.value).toBe('path')
    expect(routeSync.requestedPathId.value).toBe('latest')
    expect(routeSync.graphQuery.value).toEqual({ scope: 'path', path_id: 'latest' })
  })

  it('normalizes route arrays and goal draft session query', () => {
    routeState.query = {
      scope: ['path'],
      path_id: ['custom-path'],
      nodeId: ['ml_c01'],
      sessionId: ['sess-001'],
      goalDraft: ['true'],
      resolutionSessionId: ['res-001'],
    }

    const routeSync = useGraphRouteSync()

    expect(routeSync.requestedPathId.value).toBe('custom-path')
    expect(routeSync.requestedNodeId.value).toBe('ml_c01')
    expect(routeSync.requestedSessionId.value).toBe('sess-001')
    expect(routeSync.goalDraftResolutionSessionId.value).toBe('res-001')
    expect(routeSync.graphQuery.value).toEqual({ scope: 'path', path_id: 'custom-path', nodeId: 'ml_c01' })
  })

  it('writes route query while preserving active session id by default', async () => {
    routeState.query = { sessionId: 'sess-001' }
    const routeSync = useGraphRouteSync()

    await routeSync.replaceGraphRoute('project', 'ml_c01')

    expect(replaceMock).toHaveBeenCalledWith({
      name: 'Knowledge',
      query: {
        scope: 'project',
        nodeId: 'ml_c01',
        sessionId: 'sess-001',
      },
    })
  })

  it('filters null query values and writes path fallback id', async () => {
    routeState.query = {}
    const routeSync = useGraphRouteSync()

    await routeSync.replaceGraphRoute('path', null, null)

    expect(replaceMock).toHaveBeenCalledWith({
      name: 'Knowledge',
      query: {
        scope: 'path',
        path_id: 'latest',
      },
    })
  })
})
