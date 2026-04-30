import { ref, type Ref } from 'vue'
import { graphApi, type GraphEntityMetadata } from '@/api/modules/graph'

export function useEntityMetadataDrawer(projectId: Readonly<Ref<string | undefined>>) {
  const entityDrawerVisible = ref(false)
  const entityLoading = ref(false)
  const entityMetadata = ref<GraphEntityMetadata | null>(null)
  let metadataLoadRequestId = 0

  async function onShowEntities() {
    const currentProjectId = projectId.value
    if (!currentProjectId) return

    const requestId = ++metadataLoadRequestId
    entityDrawerVisible.value = true
    entityLoading.value = true

    try {
      const metadata = await graphApi.getGraphEntities(currentProjectId)
      if (requestId === metadataLoadRequestId && projectId.value === currentProjectId) {
        entityMetadata.value = metadata
      }
    } catch {
      if (requestId === metadataLoadRequestId) {
        entityDrawerVisible.value = false
      }
    } finally {
      if (requestId === metadataLoadRequestId) {
        entityLoading.value = false
      }
    }
  }

  function resetEntityMetadataDrawer() {
    metadataLoadRequestId += 1
    entityDrawerVisible.value = false
    entityLoading.value = false
    entityMetadata.value = null
  }

  return {
    entityDrawerVisible,
    entityLoading,
    entityMetadata,
    onShowEntities,
    resetEntityMetadataDrawer,
  }
}
