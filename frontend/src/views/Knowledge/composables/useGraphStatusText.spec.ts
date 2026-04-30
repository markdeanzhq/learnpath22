import { ref } from 'vue'
import { describe, expect, it } from 'vitest'
import { useGraphStatusText } from './useGraphStatusText'
import type { GraphScope, OverlayProjectionStatusResponse } from '@/api/modules/graph'
import type { GraphState } from './useGraphWorkspaceLoader'

function createStatusText() {
  const scope = ref<GraphScope>('path')
  const graphState = ref<GraphState>('ready')
  const errorMessage = ref('')
  const emptyReason = ref<string | undefined>()
  const projectionStatus = ref<OverlayProjectionStatusResponse | null>(null)
  const statusText = useGraphStatusText({
    scope,
    graphState,
    errorMessage,
    emptyReason,
    projectionStatus,
  })
  return { scope, graphState, errorMessage, emptyReason, projectionStatus, statusText }
}

describe('useGraphStatusText', () => {
  it('describes latest path missing empty state separately', () => {
    const { emptyReason, statusText } = createStatusText()

    emptyReason.value = 'project_latest_plan_missing'

    expect(statusText.emptyDescription.value).toBe('当前项目尚未生成学习路径，暂时无法展示路径子图；项目图谱仍可显示领域基线与项目扩展草稿。')
  })

  it('falls back to generic empty description', () => {
    const { statusText } = createStatusText()

    expect(statusText.emptyDescription.value).toBe('当前范围暂无图谱数据，可刷新或先同步领域知识包到 Neo4j')
  })

  it('maps projection status to alert type and readable title', () => {
    const { projectionStatus, statusText } = createStatusText()

    projectionStatus.value = {
      project_id: 'project-001',
      status: 'ok',
      ready: true,
      in_sync: true,
      reason: null,
    }
    expect(statusText.projectionAlertType.value).toBe('success')
    expect(statusText.projectionStatusTitle.value).toBe('项目扩展投影已同步')

    projectionStatus.value = {
      project_id: 'project-001',
      status: 'missing',
      ready: false,
      in_sync: false,
      reason: 'projection_missing',
    }
    expect(statusText.projectionAlertType.value).toBe('warning')
    expect(statusText.projectionStatusTitle.value).toBe('项目扩展投影需关注：已有扩展草稿，但尚未同步为 Neo4j 投影；普通浏览和路径预检不受影响，需要显式同步时再点击同步图谱')
  })

  it('labels graph scope modes', () => {
    const { scope, statusText } = createStatusText()

    scope.value = 'path'
    expect(statusText.graphScopeLabel.value).toBe('学习路径子图')
    scope.value = 'project'
    expect(statusText.graphScopeLabel.value).toBe('项目增强图')
    scope.value = 'domain'
    expect(statusText.graphScopeLabel.value).toBe('领域基线图')
  })

  it('describes graph state and ready scope hints', () => {
    const { scope, graphState, errorMessage, emptyReason, statusText } = createStatusText()

    graphState.value = 'loading'
    expect(statusText.graphStatusHint.value).toBe('正在读取本地图谱视图与审核状态。')

    graphState.value = 'empty'
    emptyReason.value = 'project_latest_plan_missing'
    expect(statusText.graphStatusHint.value).toBe('当前项目尚未生成学习路径，暂时无法展示路径子图；项目图谱仍可显示领域基线与项目扩展草稿。')

    graphState.value = 'error'
    errorMessage.value = ''
    expect(statusText.graphStatusHint.value).toBe('图谱读取失败，请稍后重试。')
    errorMessage.value = 'network down'
    expect(statusText.graphStatusHint.value).toBe('network down')

    graphState.value = 'ready'
    scope.value = 'path'
    expect(statusText.graphStatusHint.value).toBe('仅展示最新学习路径命中的知识点和依赖关系。')
    scope.value = 'project'
    expect(statusText.graphStatusHint.value).toBe('展示领域基线叠加已审核且允许规划的项目扩展候选。')
    scope.value = 'domain'
    expect(statusText.graphStatusHint.value).toBe('展示领域知识包的稳定基线，不依赖 Neo4j 读取链路。')
  })
})
