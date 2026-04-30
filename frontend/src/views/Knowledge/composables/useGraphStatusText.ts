import { computed, type Ref } from 'vue'
import type { GraphScope, OverlayProjectionStatusResponse } from '@/api/modules/graph'
import { formatServiceReason } from '@/utils/displayLabels'
import type { GraphState } from './useGraphWorkspaceLoader'

const PROJECT_LATEST_PLAN_MISSING = 'project_latest_plan_missing'

type UseGraphStatusTextOptions = {
  scope: Readonly<Ref<GraphScope>>
  graphState: Readonly<Ref<GraphState>>
  errorMessage: Readonly<Ref<string>>
  emptyReason: Readonly<Ref<string | undefined>>
  projectionStatus: Readonly<Ref<OverlayProjectionStatusResponse | null>>
}

export function useGraphStatusText({
  scope,
  graphState,
  errorMessage,
  emptyReason,
  projectionStatus,
}: UseGraphStatusTextOptions) {
  const emptyDescription = computed(() =>
    emptyReason.value === PROJECT_LATEST_PLAN_MISSING
      ? '当前项目尚未生成学习路径，暂时无法展示路径子图；项目图谱仍可显示领域基线与项目扩展草稿。'
      : '当前范围暂无图谱数据，可刷新或先同步领域知识包到 Neo4j',
  )
  const projectionAlertType = computed(() => projectionStatus.value?.status === 'ok' ? 'success' : 'warning')
  const projectionStatusTitle = computed(() => {
    if (!projectionStatus.value) return ''
    const status = projectionStatus.value.status === 'ok' ? '项目扩展投影已同步' : '项目扩展投影需关注'
    const reason = formatServiceReason(projectionStatus.value.reason)
    return reason ? `${status}：${reason}` : status
  })
  const graphScopeLabel = computed(() => {
    if (scope.value === 'domain') return '领域基线图'
    if (scope.value === 'project') return '项目增强图'
    return '学习路径子图'
  })
  const graphStatusHint = computed(() => {
    if (graphState.value === 'loading') return '正在读取本地图谱视图与审核状态。'
    if (graphState.value === 'empty') return emptyDescription.value
    if (graphState.value === 'error') return errorMessage.value || '图谱读取失败，请稍后重试。'
    if (scope.value === 'path') return '仅展示最新学习路径命中的知识点和依赖关系。'
    if (scope.value === 'project') return '展示领域基线叠加已审核且允许规划的项目扩展候选。'
    return '展示领域知识包的稳定基线，不依赖 Neo4j 读取链路。'
  })

  return {
    emptyDescription,
    projectionAlertType,
    projectionStatusTitle,
    graphScopeLabel,
    graphStatusHint,
  }
}
