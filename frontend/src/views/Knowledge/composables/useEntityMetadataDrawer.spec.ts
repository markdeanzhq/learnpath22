import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useEntityMetadataDrawer } from './useEntityMetadataDrawer'
import type { GraphEntityMetadata } from '@/api/modules/graph'

const { getGraphEntitiesMock } = vi.hoisted(() => ({
  getGraphEntitiesMock: vi.fn(),
}))

vi.mock('@/api/modules/graph', () => ({
  graphApi: {
    getGraphEntities: getGraphEntitiesMock,
  },
}))

function createMetadata(domain = 'machine_learning'): GraphEntityMetadata {
  return {
    domain,
    stages: [],
    resources: [],
    relationships: {
      stage_sequences: [],
      stage_nodes: [],
      stage_resources: [],
      resource_nodes: [],
    },
    is_empty: false,
  }
}

function createDeferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

describe('useEntityMetadataDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads entity metadata and opens the drawer', async () => {
    const metadata = createMetadata()
    getGraphEntitiesMock.mockResolvedValue(metadata)
    const projectId = ref<string | undefined>('project-001')
    const drawer = useEntityMetadataDrawer(projectId)

    await drawer.onShowEntities()

    expect(getGraphEntitiesMock).toHaveBeenCalledWith('project-001')
    expect(drawer.entityDrawerVisible.value).toBe(true)
    expect(drawer.entityLoading.value).toBe(false)
    expect(drawer.entityMetadata.value).toEqual(metadata)
  })

  it('skips loading when project is missing', async () => {
    const projectId = ref<string | undefined>()
    const drawer = useEntityMetadataDrawer(projectId)

    await drawer.onShowEntities()

    expect(getGraphEntitiesMock).not.toHaveBeenCalled()
    expect(drawer.entityDrawerVisible.value).toBe(false)
  })

  it('closes the drawer when metadata loading fails', async () => {
    getGraphEntitiesMock.mockRejectedValue(new Error('offline'))
    const projectId = ref<string | undefined>('project-001')
    const drawer = useEntityMetadataDrawer(projectId)

    await drawer.onShowEntities()

    expect(drawer.entityDrawerVisible.value).toBe(false)
    expect(drawer.entityLoading.value).toBe(false)
    expect(drawer.entityMetadata.value).toBeNull()
  })

  it('ignores stale metadata responses', async () => {
    const firstLoad = createDeferred<GraphEntityMetadata>()
    const secondLoad = createDeferred<GraphEntityMetadata>()
    getGraphEntitiesMock
      .mockReturnValueOnce(firstLoad.promise)
      .mockReturnValueOnce(secondLoad.promise)
    const projectId = ref<string | undefined>('project-001')
    const drawer = useEntityMetadataDrawer(projectId)

    const firstRequest = drawer.onShowEntities()
    const secondRequest = drawer.onShowEntities()
    secondLoad.resolve(createMetadata('new-domain'))
    await secondRequest
    firstLoad.resolve(createMetadata('stale-domain'))
    await firstRequest

    expect(drawer.entityMetadata.value?.domain).toBe('new-domain')
    expect(drawer.entityLoading.value).toBe(false)
  })
})
