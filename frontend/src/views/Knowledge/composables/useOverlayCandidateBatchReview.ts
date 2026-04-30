import { computed, ref, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import {
  graphApi,
  type OverlayElementGroup,
  type OverlayReviewStatus,
  type OverlayStatusResponse,
} from '@/api/modules/graph'
import type { OverlaySessionView } from './useOverlayCandidateWorkflow'

type OverlayBatchReviewTarget = {
  group: OverlayElementGroup
  id: string
}

type UseOverlayCandidateBatchReviewOptions = {
  projectId: Readonly<Ref<string | undefined>>
  lastOverlaySession: Ref<OverlaySessionView | null>
  overlayError: Ref<string>
  refreshAfterBatch: () => Promise<void>
  getErrorMessage: (error: unknown) => string
  notifySuccess?: (message: string) => void
}

export function useOverlayCandidateBatchReview({
  projectId,
  lastOverlaySession,
  overlayError,
  refreshAfterBatch,
  getErrorMessage,
  notifySuccess,
}: UseOverlayCandidateBatchReviewOptions) {
  const overlayBatchReviewLoading = ref(false)
  const overlayBatchConfirmTargets = computed(() => collectConfirmableTargets(lastOverlaySession.value))
  const overlayBatchConfirmableCount = computed(() => overlayBatchConfirmTargets.value.length)

  async function confirmValidPendingOverlayCandidates() {
    const currentProjectId = projectId.value
    const targets = overlayBatchConfirmTargets.value
    if (!currentProjectId || !targets.length) return

    if (!(await confirmBatchReview(targets.length))) {
      return
    }

    overlayBatchReviewLoading.value = true
    overlayError.value = ''
    try {
      const results = await Promise.all(
        targets.map((target) => graphApi.reviewOverlayElement(
          currentProjectId,
          target.group,
          target.id,
          'confirmed' as OverlayReviewStatus,
        )),
      )
      patchOverlaySessionReviewStatus(lastOverlaySession, results)
      await refreshAfterBatch()
      notifySuccess?.(`已批量确认 ${results.length} 个候选，请继续检查规划开关和路径预检。`)
    } catch (error: unknown) {
      overlayError.value = getErrorMessage(error) || '批量确认候选失败'
    } finally {
      overlayBatchReviewLoading.value = false
    }
  }

  return {
    overlayBatchReviewLoading,
    overlayBatchConfirmableCount,
    confirmValidPendingOverlayCandidates,
  }
}

function collectConfirmableTargets(session: OverlaySessionView | null): OverlayBatchReviewTarget[] {
  if (!session) return []
  return [
    ...(session.nodes || [])
      .filter(isValidPendingCandidate)
      .map((candidate) => ({ group: 'nodes' as const, id: candidate.node_id })),
    ...(session.edges || [])
      .filter(isValidPendingCandidate)
      .map((candidate) => ({ group: 'edges' as const, id: candidate.edge_id })),
    ...(session.resources || [])
      .filter(isValidPendingCandidate)
      .map((candidate) => ({ group: 'resources' as const, id: candidate.resource_id })),
  ]
}

function isValidPendingCandidate(candidate: { validation_status?: string | null; review_status?: string | null }) {
  return candidate.validation_status === 'valid' && candidate.review_status === 'pending'
}

async function confirmBatchReview(count: number) {
  try {
    await ElMessageBox.confirm(
      `将批量确认 ${count} 个已通过机器校验的候选；该操作不会直接写入正式图谱或生成学习路径，是否继续？`,
      '批量确认待审核候选',
      {
        type: 'warning',
        confirmButtonText: '批量确认',
        cancelButtonText: '取消',
      },
    )
    return true
  } catch (error) {
    if (isMessageBoxCancel(error)) return false
    throw error
  }
}

function patchOverlaySessionReviewStatus(
  lastOverlaySession: Ref<OverlaySessionView | null>,
  results: OverlayStatusResponse[],
) {
  const session = lastOverlaySession.value
  if (!session) return
  const byId = new Map(results.map((result) => [result.element_id, result]))
  lastOverlaySession.value = {
    ...session,
    nodes: (session.nodes || []).map((candidate) => patchCandidateStatus(candidate, byId.get(candidate.node_id))),
    edges: (session.edges || []).map((candidate) => patchCandidateStatus(candidate, byId.get(candidate.edge_id))),
    resources: (session.resources || []).map((candidate) => patchCandidateStatus(candidate, byId.get(candidate.resource_id))),
  }
}

function patchCandidateStatus<T extends { review_status?: string; planning_enabled?: boolean; promotion_status?: string; validation_status?: string }>(
  candidate: T,
  status?: OverlayStatusResponse,
): T {
  if (!status) return candidate
  return {
    ...candidate,
    validation_status: status.validation_status,
    review_status: status.review_status,
    planning_enabled: status.planning_enabled,
    promotion_status: status.promotion_status,
  }
}

function isMessageBoxCancel(error: unknown): boolean {
  if (typeof error === 'string') {
    return error === 'cancel' || error === 'close'
  }
  if (error && typeof error === 'object' && 'action' in error) {
    const action = (error as { action?: unknown }).action
    return action === 'cancel' || action === 'close'
  }
  return false
}
