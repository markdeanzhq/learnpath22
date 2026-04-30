import { computed, ref, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import {
  graphApi,
  type OverlayElementGroup,
  type OverlayStatusResponse,
} from '@/api/modules/graph'
import type { OverlaySessionView } from './useOverlayCandidateWorkflow'

type OverlayBatchPlanningTarget = {
  group: OverlayElementGroup
  id: string
}

type UseOverlayCandidateBatchPlanningOptions = {
  projectId: Readonly<Ref<string | undefined>>
  lastOverlaySession: Ref<OverlaySessionView | null>
  overlayError: Ref<string>
  refreshAfterBatch: () => Promise<void>
  getErrorMessage: (error: unknown) => string
  notifySuccess?: (message: string) => void
}

export function useOverlayCandidateBatchPlanning({
  projectId,
  lastOverlaySession,
  overlayError,
  refreshAfterBatch,
  getErrorMessage,
  notifySuccess,
}: UseOverlayCandidateBatchPlanningOptions) {
  const overlayBatchPlanningLoading = ref(false)
  const overlayBatchPlanningTargets = computed(() => collectPlanningTargets(lastOverlaySession.value))
  const overlayBatchPlannableCount = computed(() => overlayBatchPlanningTargets.value.length)

  async function enableConfirmedOverlayCandidatesPlanning() {
    const currentProjectId = projectId.value
    const targets = overlayBatchPlanningTargets.value
    if (!currentProjectId || !targets.length) return

    if (!(await confirmBatchPlanning(targets.length))) {
      return
    }

    overlayBatchPlanningLoading.value = true
    overlayError.value = ''
    try {
      const results = await Promise.all(
        targets.map((target) => graphApi.setOverlayPlanning(
          currentProjectId,
          target.group,
          target.id,
          true,
        )),
      )
      patchOverlaySessionPlanningStatus(lastOverlaySession, results)
      await refreshAfterBatch()
      notifySuccess?.(`已将 ${results.length} 个候选纳入规划，请查看增强图谱预检结果。`)
    } catch (error: unknown) {
      overlayError.value = getErrorMessage(error) || '批量纳入规划失败'
    } finally {
      overlayBatchPlanningLoading.value = false
    }
  }

  return {
    overlayBatchPlanningLoading,
    overlayBatchPlannableCount,
    enableConfirmedOverlayCandidatesPlanning,
  }
}

function collectPlanningTargets(session: OverlaySessionView | null): OverlayBatchPlanningTarget[] {
  if (!session) return []
  return [
    ...(session.nodes || [])
      .filter(isConfirmedPlanningCandidate)
      .map((candidate) => ({ group: 'nodes' as const, id: candidate.node_id })),
    ...(session.edges || [])
      .filter(isConfirmedPlanningCandidate)
      .map((candidate) => ({ group: 'edges' as const, id: candidate.edge_id })),
    ...(session.resources || [])
      .filter(isConfirmedPlanningCandidate)
      .map((candidate) => ({ group: 'resources' as const, id: candidate.resource_id })),
  ]
}

function isConfirmedPlanningCandidate(candidate: { validation_status?: string | null; review_status?: string | null; planning_enabled?: boolean | null }) {
  return candidate.validation_status === 'valid' && candidate.review_status === 'confirmed' && !candidate.planning_enabled
}

async function confirmBatchPlanning(count: number) {
  try {
    await ElMessageBox.confirm(
      `将 ${count} 个已确认候选纳入增强图谱规划；该操作只影响项目增强图谱预检，不会直接生成正式学习路径，是否继续？`,
      '批量纳入规划',
      {
        type: 'warning',
        confirmButtonText: '纳入规划',
        cancelButtonText: '取消',
      },
    )
    return true
  } catch (error) {
    if (isMessageBoxCancel(error)) return false
    throw error
  }
}

function patchOverlaySessionPlanningStatus(
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
