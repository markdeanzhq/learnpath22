import { computed, ref, type Ref } from 'vue'
import {
  graphApi,
  type GraphNodeData,
  type OverlayPromotionResponse,
} from '@/api/modules/graph'
import { resourceApi } from '@/api/modules/resource'
import {
  formatServiceReason,
  promotionPreviewStatusMeta,
} from '@/utils/displayLabels'
import type { OverlaySessionView } from './useOverlayCandidateWorkflow'

type ResourceBindingForm = {
  resourceId: string
  targetType: 'project_node' | 'path_stage'
  targetId: string
}

type UseOverlayPostActionsOptions = {
  projectId: Readonly<Ref<string | undefined>>
  nodes: Readonly<Ref<GraphNodeData[]>>
  lastOverlaySession: Ref<OverlaySessionView | null>
  overlayError: Ref<string>
  refreshProjectionStatus: () => Promise<void>
  refreshGraphWorkspace: () => Promise<void>
  notifySuccess?: (message: string) => void
}

export function useOverlayPostActions({
  projectId,
  nodes,
  lastOverlaySession,
  overlayError,
  refreshProjectionStatus,
  refreshGraphWorkspace,
  notifySuccess,
}: UseOverlayPostActionsOptions) {
  const promotionPreview = ref<OverlayPromotionResponse | null>(null)
  const promotionResult = ref<OverlayPromotionResponse | null>(null)
  const promotionSecret = ref('')
  const promotionLoading = ref(false)
  const resourceBinding = ref<ResourceBindingForm>({ resourceId: '', targetType: 'project_node', targetId: '' })

  const promotionStatusMessage = computed(() => {
    if (!promotionResult.value) return ''
    if (promotionResult.value.reason === 'promoted') return '推广成功，候选已归档隐藏。'
    return formatServiceReason(promotionResult.value.reason) || promotionPreviewStatusMeta(promotionResult.value.status).label || '推广状态已更新'
  })

  const resourceTargetOptions = computed(() => nodes.value.map((node) => ({
    id: node.id,
    label: node.label || node.id,
  })))

  function resetOverlayPostActions() {
    promotionPreview.value = null
    promotionResult.value = null
    promotionSecret.value = ''
    resourceBinding.value = { resourceId: '', targetType: 'project_node', targetId: '' }
  }

  async function bindOverlayResource() {
    if (!projectId.value || !resourceBinding.value.resourceId || !resourceBinding.value.targetId.trim()) {
      overlayError.value = '请选择资源和绑定目标'
      return
    }
    try {
      await resourceApi.bindProjectResource(projectId.value, {
        resource_id: resourceBinding.value.resourceId,
        target_type: resourceBinding.value.targetType,
        target_id: resourceBinding.value.targetId.trim(),
        binding_source: 'overlay',
      })
      if (lastOverlaySession.value) {
        lastOverlaySession.value = await graphApi.getOverlayExtractionSession(projectId.value, lastOverlaySession.value.session.session_id)
      }
      await refreshProjectionStatus()
      notifySuccess?.('资源绑定已保存')
    } catch (error: any) {
      overlayError.value = error?.response?.data?.error || '资源绑定失败'
    }
  }

  async function previewPromotion() {
    if (!projectId.value) return
    promotionLoading.value = true
    promotionResult.value = null
    try {
      promotionPreview.value = await graphApi.previewOverlayPromotion(projectId.value)
    } catch (error: any) {
      overlayError.value = formatServiceReason(error?.response?.data?.error) || '推广预览失败'
    } finally {
      promotionLoading.value = false
    }
  }

  async function commitPromotion() {
    const currentProjectId = projectId.value
    if (!currentProjectId) return
    if (!promotionSecret.value.trim()) {
      overlayError.value = '请输入 admin secret'
      return
    }
    promotionLoading.value = true
    try {
      promotionResult.value = await graphApi.commitOverlayPromotion(currentProjectId, {
        admin_secret: promotionSecret.value,
        requested_by: 'frontend',
      })
      promotionSecret.value = ''
      const sessionId = lastOverlaySession.value?.session.session_id
      await Promise.all([
        refreshGraphWorkspace(),
        sessionId
          ? graphApi.getOverlayExtractionSession(currentProjectId, sessionId).then((session) => {
            if (projectId.value === currentProjectId) {
              lastOverlaySession.value = session
            }
          })
          : Promise.resolve(),
      ])
    } catch (error: any) {
      const code = error?.response?.data?.error
      overlayError.value = formatServiceReason(code) || '确认推广失败'
      promotionResult.value = error?.response?.data?.details?.preview || error?.response?.data?.details || null
    } finally {
      promotionLoading.value = false
    }
  }

  return {
    promotionPreview,
    promotionResult,
    promotionSecret,
    promotionLoading,
    resourceBinding,
    promotionStatusMessage,
    resourceTargetOptions,
    resetOverlayPostActions,
    bindOverlayResource,
    previewPromotion,
    commitPromotion,
  }
}
