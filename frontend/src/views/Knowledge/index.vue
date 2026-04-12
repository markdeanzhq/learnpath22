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

    <NodeDetail :node="selectedNode" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/stores/project'
import { graphApi, type GraphData, type GraphElement } from '@/api/modules/graph'
import GraphCanvas from '@/components/Graph/GraphCanvas.vue'
import NodeDetail from '@/components/Graph/NodeDetail.vue'
import GraphToolbar from '@/components/Graph/GraphToolbar.vue'

type GraphState = 'loading' | 'ready' | 'empty' | 'error'
type GraphScope = 'project' | 'domain'

const PROJECT_LATEST_PLAN_MISSING = 'project_latest_plan_missing'

const projectStore = useProjectStore()
const projectId = computed(() => projectStore.currentProject?.id)
const elements = ref<GraphElement[]>([])
const layout = ref<'cose' | 'breadthfirst'>('cose')
const scope = ref<GraphScope>('project')
const graphState = ref<GraphState>('loading')
const loading = ref(false)
const syncing = ref(false)
const errorMessage = ref('')
const lastRefreshError = ref('')
const emptyReason = ref<string | undefined>()
const selectedNode = ref<any>(null)
const graphRef = ref<InstanceType<typeof GraphCanvas>>()
const pageRef = ref<HTMLDivElement>()
const reviewMode = ref(false)
const emptyDescription = computed(() =>
  emptyReason.value === PROJECT_LATEST_PLAN_MISSING
    ? '当前项目尚未生成学习路径，暂时无法展示项目子图'
    : '当前范围暂无图谱数据，可刷新或先同步 Domain Pack 到 Neo4j',
)

function resetGraphState() {
  elements.value = []
  selectedNode.value = null
  errorMessage.value = ''
  lastRefreshError.value = ''
  emptyReason.value = undefined
  graphState.value = 'loading'
}

function applyGraphData(data: GraphData) {
  const nextElements = data.elements ?? []

  elements.value = nextElements
  selectedNode.value = null
  errorMessage.value = ''
  lastRefreshError.value = ''
  emptyReason.value = data.empty_reason
  graphState.value = nextElements.length > 0 ? 'ready' : 'empty'
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
    selectedNode.value = null

    if (hasExistingGraph) {
      lastRefreshError.value = message
      graphState.value = 'ready'
      ElMessage.error(message)
    } else {
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
  layout.value = newLayout as 'cose' | 'breadthfirst'
}

function onNodeClick(data: any) {
  selectedNode.value = data
}

function onSearch(keyword: string) {
  graphRef.value?.highlightBySearch(keyword)
}

async function onScopeChange(nextScope: GraphScope) {
  if (scope.value === nextScope) return
  scope.value = nextScope
  selectedNode.value = null
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
  try {
    await graphApi.reviewNode(projectId.value, nodeId, status)
    ElMessage.success('节点审核状态已更新')
    await loadGraph()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '节点审核失败')
  }
}

async function onReviewEdge(edgeId: string, status: string) {
  if (!projectId.value) return
  try {
    await graphApi.reviewEdge(projectId.value, edgeId, status)
    ElMessage.success('边审核状态已更新')
    await loadGraph()
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
  flex: 1;
  min-height: 0;
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
}
</style>
