<template>
  <div class="page-container" ref="pageRef">
    <el-card
      shadow="never"
      class="graph-card"
      :body-style="{ padding: 0, display: 'flex', flexDirection: 'column', height: 'calc(100vh - 160px)' }"
    >
      <template v-if="!projectId">
        <div class="empty-project-wrap">
          <el-empty description="请先在项目页选择一个项目后再查看知识图谱" />
        </div>
      </template>

      <GraphToolbar
        v-if="projectId"
        :scope="scope"
        :current-layout="layout"
        :review-mode="reviewMode"
        :loading="loading"
        :syncing="syncing"
        @scope-change="onScopeChange"
        @refresh="onRefresh"
        @sync="onSync"
        @layout-change="onLayoutChange"
        @zoom-in="graphRef?.zoomIn()"
        @zoom-out="graphRef?.zoomOut()"
        @fit-view="graphRef?.fitView()"
        @search="onSearch"
        @toggle-fullscreen="toggleFullscreen"
        @toggle-review="reviewMode = $event"
      />

      <div
        v-if="projectId"
        class="graph-wrapper"
        v-loading="loading || syncing"
        :element-loading-text="syncing ? '正在同步知识图谱...' : '正在加载知识图谱...'"
      >
        <div class="graph-legend-wrap">
          <div class="legend-section">
            <span class="legend-title">节点颜色</span>
            <div class="legend-items">
              <span v-for="item in categoryLegend" :key="item.key" class="legend-chip">
                <span class="legend-dot" :style="{ backgroundColor: item.color }"></span>
                <span>{{ item.label }}</span>
              </span>
            </div>
          </div>

          <div class="legend-section">
            <span class="legend-title">关系说明</span>
            <div class="legend-items">
              <span v-for="item in relationLegend" :key="item.type" class="legend-chip legend-chip-edge">
                <span class="legend-line" :class="[
                  item.lineStyle === 'dashed' ? 'legend-line-dashed' : 'legend-line-solid',
                  item.hasArrow ? 'legend-line-arrow' : '',
                ]"></span>
                <span>{{ item.label }}：{{ item.description }}</span>
              </span>
            </div>
          </div>
        </div>
        <el-alert
          v-if="graphState === 'ready' && lastRefreshError"
          class="graph-alert"
          type="warning"
          :closable="false"
          show-icon
          :title="lastRefreshError"
        />

        <GraphCanvas
          v-if="graphState === 'ready'"
          ref="graphRef"
          :elements="elements"
          :layout="layout"
          :review-mode="reviewMode"
          @node-click="onNodeClick"
          @review-node="onReviewNode"
          @review-edge="onReviewEdge"
        />

        <div v-else-if="graphState === 'loading'" class="graph-state-wrap" />

        <el-empty
          v-else-if="graphState === 'empty'"
          class="graph-state-wrap"
          :description="emptyDescription"
        >
          <el-button type="primary" @click="onRefresh">刷新</el-button>
          <el-button :loading="syncing" @click="onSync">同步图谱</el-button>
        </el-empty>

        <div v-else class="graph-state-wrap">
          <el-result
            icon="error"
            title="知识图谱加载失败"
            :sub-title="errorMessage || '请稍后重试或重新同步图谱'"
          >
            <template #extra>
              <el-space wrap>
                <el-button type="primary" @click="onRefresh">重新加载</el-button>
                <el-button :loading="syncing" @click="onSync">同步图谱</el-button>
              </el-space>
            </template>
          </el-result>
        </div>
      </div>
    </el-card>

    <NodeDetail :node="selectedNode" @review-edge="onReviewEdge" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/stores/project'
import {
  graphApi,
  type GraphData,
  type GraphEdgeData,
  type GraphElement,
  type GraphNodeData,
  type ReviewStatus,
} from '@/api/modules/graph'
import GraphCanvas from '@/components/Graph/GraphCanvas.vue'
import NodeDetail from '@/components/Graph/NodeDetail.vue'
import GraphToolbar from '@/components/Graph/GraphToolbar.vue'
import { GRAPH_CATEGORY_LEGEND, GRAPH_RELATION_LEGEND } from '@/components/Graph/graphMeta'

type GraphState = 'loading' | 'ready' | 'empty' | 'error'
type GraphScope = 'project' | 'domain'
type GraphLayout = 'cose' | 'breadthfirst'

type SelectedAdjacentEdge = GraphEdgeData & {
  direction: 'incoming' | 'outgoing'
  source_label?: string
  target_label?: string
}

type SelectedNodeContext = GraphNodeData & {
  adjacent_edges: SelectedAdjacentEdge[]
  incoming_edges: SelectedAdjacentEdge[]
  outgoing_edges: SelectedAdjacentEdge[]
}

const PROJECT_LATEST_PLAN_MISSING = 'project_latest_plan_missing'

const projectStore = useProjectStore()
const projectId = computed(() => projectStore.currentProject?.id)
const elements = ref<GraphElement[]>([])
const layout = ref<GraphLayout>('cose')
const scope = ref<GraphScope>('project')
const graphState = ref<GraphState>('loading')
const loading = ref(false)
const syncing = ref(false)
const errorMessage = ref('')
const lastRefreshError = ref('')
const emptyReason = ref<string | undefined>()
const selectedNodeId = ref<string | null>(null)
const graphRef = ref<InstanceType<typeof GraphCanvas>>()
const pageRef = ref<HTMLDivElement>()
const reviewMode = ref(false)
const categoryLegend = GRAPH_CATEGORY_LEGEND
const relationLegend = GRAPH_RELATION_LEGEND
const emptyDescription = computed(() =>
  emptyReason.value === PROJECT_LATEST_PLAN_MISSING
    ? '当前项目尚未生成学习路径，暂时无法展示项目子图'
    : '当前范围暂无图谱数据，可刷新或先同步 Domain Pack 到 Neo4j',
)

function isNodeElement(element: GraphElement): element is Extract<GraphElement, { group: 'nodes' }> {
  return element.group === 'nodes'
}

function isEdgeElement(element: GraphElement): element is Extract<GraphElement, { group: 'edges' }> {
  return element.group === 'edges'
}

const nodes = computed(() => elements.value.filter(isNodeElement).map((element) => element.data))
const edges = computed(() => elements.value.filter(isEdgeElement).map((element) => element.data))
const nodeLabelMap = computed(() => new Map(nodes.value.map((node) => [node.id, node.label])))
const selectedNode = computed<SelectedNodeContext | null>(() => {
  const nodeId = selectedNodeId.value
  if (!nodeId) return null

  const node = nodes.value.find((item) => item.id === nodeId)
  if (!node) return null

  const adjacentEdges = edges.value
    .filter((edge) => edge.source === nodeId || edge.target === nodeId)
    .map<SelectedAdjacentEdge>((edge) => ({
      ...edge,
      direction: edge.source === nodeId ? 'outgoing' : 'incoming',
      source_label: nodeLabelMap.value.get(edge.source),
      target_label: nodeLabelMap.value.get(edge.target),
    }))

  return {
    ...node,
    adjacent_edges: adjacentEdges,
    incoming_edges: adjacentEdges.filter((edge) => edge.direction === 'incoming'),
    outgoing_edges: adjacentEdges.filter((edge) => edge.direction === 'outgoing'),
  }
})

watch(nodes, (nextNodes) => {
  if (selectedNodeId.value && !nextNodes.some((node) => node.id === selectedNodeId.value)) {
    selectedNodeId.value = null
  }
})

function resetGraphState() {
  elements.value = []
  selectedNodeId.value = null
  errorMessage.value = ''
  lastRefreshError.value = ''
  emptyReason.value = undefined
  graphState.value = 'loading'
}

function applyGraphData(data: GraphData) {
  const nextElements = data.elements ?? []

  elements.value = nextElements
  errorMessage.value = ''
  lastRefreshError.value = ''
  emptyReason.value = data.empty_reason
  graphState.value = nextElements.length > 0 ? 'ready' : 'empty'
}

function updateNodeReviewStatus(nodeId: string, status: ReviewStatus) {
  elements.value = elements.value.map((element) => {
    if (!isNodeElement(element) || element.data.id !== nodeId) {
      return element
    }

    return {
      ...element,
      data: {
        ...element.data,
        review_status: status,
      },
    }
  })
}

function updateEdgeReviewStatus(edgeId: string, status: ReviewStatus) {
  elements.value = elements.value.map((element) => {
    if (!isEdgeElement(element) || element.data.id !== edgeId) {
      return element
    }

    return {
      ...element,
      data: {
        ...element.data,
        review_status: status,
      },
    }
  })
}

async function loadGraph() {
  if (!projectId.value) {
    resetGraphState()
    return
  }

  const hasExistingGraph = elements.value.length > 0

  if (!hasExistingGraph) {
    graphState.value = 'loading'
  }

  loading.value = true
  errorMessage.value = ''

  try {
    const data = await graphApi.getGraph(projectId.value, {
      scope: scope.value,
    })
    applyGraphData(data)
  } catch (e: any) {
    const message = e?.response?.data?.error || e?.message || '知识图谱加载失败，请稍后重试'

    errorMessage.value = message

    if (hasExistingGraph) {
      lastRefreshError.value = message
      graphState.value = 'ready'
      ElMessage.error(message)
    } else {
      selectedNodeId.value = null
      lastRefreshError.value = ''
      emptyReason.value = undefined
      graphState.value = 'error'
    }
  } finally {
    loading.value = false
  }
}

watch(
  projectId,
  async (nextProjectId, previousProjectId) => {
    if (!nextProjectId) {
      resetGraphState()
      return
    }

    if (nextProjectId !== previousProjectId) {
      resetGraphState()
    }

    await loadGraph()
  },
  { immediate: true },
)

function onLayoutChange(newLayout: string) {
  layout.value = newLayout as GraphLayout
}

function onNodeClick(data: GraphNodeData) {
  selectedNodeId.value = data.id
}

function onSearch(keyword: string) {
  graphRef.value?.highlightBySearch(keyword)
}

async function onScopeChange(nextScope: GraphScope) {
  if (scope.value === nextScope) return
  scope.value = nextScope
  selectedNodeId.value = null
  await loadGraph()
}

async function onRefresh() {
  await loadGraph()
}

async function onSync() {
  if (!projectId.value) return

  const hasExistingGraph = elements.value.length > 0

  syncing.value = true
  errorMessage.value = ''

  try {
    await graphApi.syncGraph(projectId.value)
    ElMessage.success('知识图谱同步成功')
    await loadGraph()
  } catch (e: any) {
    const message = e?.response?.data?.error || e?.message || '知识图谱同步失败，请稍后重试'
    errorMessage.value = message

    if (hasExistingGraph) {
      lastRefreshError.value = message
      ElMessage.error(message)
      return
    }

    lastRefreshError.value = ''

    if (graphState.value !== 'empty') {
      emptyReason.value = undefined
      graphState.value = 'error'
    }

    ElMessage.error(message)
  } finally {
    syncing.value = false
  }
}

async function onReviewNode(nodeId: string, status: string) {
  if (!projectId.value) return
  const nextStatus = status as ReviewStatus
  try {
    await graphApi.reviewNode(projectId.value, nodeId, nextStatus)
    selectedNodeId.value = nodeId
    updateNodeReviewStatus(nodeId, nextStatus)
    graphRef.value?.setNodeReviewStatus(nodeId, nextStatus)
    ElMessage.success('节点审核状态已更新')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '节点审核失败')
  }
}

async function onReviewEdge(edgeId: string, status: string) {
  if (!projectId.value) return
  const nextStatus = status as ReviewStatus
  try {
    await graphApi.reviewEdge(projectId.value, edgeId, nextStatus)
    updateEdgeReviewStatus(edgeId, nextStatus)
    graphRef.value?.setEdgeReviewStatus(edgeId, nextStatus)
    ElMessage.success('边审核状态已更新')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '边审核失败')
  }
}

function toggleFullscreen() {
  if (!pageRef.value) return
  if (document.fullscreenElement) {
    document.exitFullscreen()
  } else {
    pageRef.value.requestFullscreen()
  }
}
</script>

<style scoped>
.page-container {
  padding: 20px;
  height: calc(100vh - 100px);
}

.graph-card {
  height: 100%;
}

.graph-wrapper {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

.graph-legend-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px;
  border-bottom: 1px solid #ebeef5;
  background: #fff;
}

.legend-section {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.legend-title {
  font-size: 12px;
  font-weight: 600;
  color: #606266;
}

.legend-items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.legend-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid #ebeef5;
  border-radius: 999px;
  background: #fafafa;
  font-size: 12px;
  color: #606266;
}

.legend-chip-edge {
  max-width: 100%;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex: 0 0 auto;
}

.legend-line {
  position: relative;
  display: inline-block;
  width: 28px;
  height: 0;
  border-top: 2px solid #909399;
  flex: 0 0 auto;
}

.legend-line-dashed {
  border-top-style: dashed;
}

.legend-line-solid {
  border-top-style: solid;
}

.legend-line-arrow::after {
  content: '';
  position: absolute;
  top: -5px;
  right: -2px;
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
  border-left: 7px solid #909399;
}

.graph-alert {
  margin: 12px 12px 0;
}

.graph-state-wrap,
.empty-project-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 360px;
}

@media (max-width: 768px) {
  .page-container {
    padding: 12px;
    height: auto;
  }

  .graph-legend-wrap {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
