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
        :entity-loading="entityLoading"
        @scope-change="onScopeChange"
        @refresh="onRefresh"
        @sync="onSync"
        @layout-change="onLayoutChange"
        @zoom-in="graphRef?.zoomIn()"
        @zoom-out="graphRef?.zoomOut()"
        @fit-view="graphRef?.fitView()"
        @search="onSearch"
        @show-entities="onShowEntities"
        @create-overlay="openOverlayDrawer"
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
          v-if="projectionStatus && projectionStatus.status !== 'empty'"
          class="graph-alert"
          :type="projectionAlertType"
          :closable="false"
          show-icon
          :title="projectionStatusTitle"
        />
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
          :highlight-nodes="selectedNodeId ? [selectedNodeId] : []"
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

    <NodeDetail
      :node="selectedNode"
      @review-edge="onReviewEdge"
      @set-overlay-planning="onSetOverlayPlanning"
    />
    <EntityMetadataDrawer
      v-model="entityDrawerVisible"
      :loading="entityLoading"
      :metadata="entityMetadata"
    />

    <el-drawer v-model="overlayDrawerVisible" title="创建扩展草稿" :size="520" direction="rtl">
      <div class="overlay-drawer" v-loading="overlaySubmitting">
        <el-alert
          class="overlay-alert"
          type="info"
          :closable="false"
          show-icon
          title="扩展草稿会先进入项目扩展区，确认审核与规划开关后才会参与路径规划。"
        />
        <el-alert
          v-if="goalDraftResolutionSessionId"
          class="overlay-alert"
          type="warning"
          :closable="false"
          show-icon
          title="来自目标理解的领域内未覆盖概念。页面打开不会写入；点击“创建目标扩展草稿”后才会生成 overlay 草稿。"
        />

        <el-form label-position="top">
          <el-form-item label="来源类型">
            <el-radio-group v-model="overlayForm.sourceType">
              <el-radio-button value="pasted_text">粘贴文本</el-radio-button>
              <el-radio-button value="search_url">搜索 URL</el-radio-button>
              <el-radio-button value="saved_search">已保存搜索</el-radio-button>
            </el-radio-group>
          </el-form-item>

          <template v-if="overlayForm.sourceType === 'pasted_text'">
            <el-form-item label="资料文本">
              <el-input
                v-model="overlayForm.rawText"
                type="textarea"
                :rows="8"
                maxlength="12000"
                show-word-limit
                placeholder="粘贴希望抽取为项目图谱扩展的资料内容"
              />
            </el-form-item>
            <el-form-item label="摘要（可选）">
              <el-input v-model="overlayForm.summary" placeholder="用于回看来源的简短摘要" />
            </el-form-item>
          </template>

          <template v-else-if="overlayForm.sourceType === 'search_url'">
            <el-form-item label="URL">
              <el-input v-model="overlayForm.url" placeholder="https://example.com/article" />
            </el-form-item>
            <el-form-item label="标题">
              <el-input v-model="overlayForm.title" placeholder="搜索结果标题" />
            </el-form-item>
            <el-form-item label="摘要片段">
              <el-input v-model="overlayForm.snippet" type="textarea" :rows="4" />
            </el-form-item>
          </template>

          <template v-else>
            <el-form-item label="已保存搜索结果">
              <el-select
                v-model="overlayForm.selectedResultIds"
                multiple
                filterable
                placeholder="选择已保存搜索结果"
                style="width: 100%"
              >
                <el-option
                  v-for="item in persistedSearchResults"
                  :key="item.result_id"
                  :label="item.title"
                  :value="item.result_id"
                />
              </el-select>
            </el-form-item>
            <el-alert
              v-if="overlayBridgeMessage"
              class="overlay-alert"
              type="success"
              :closable="false"
              show-icon
              :title="overlayBridgeMessage"
            />
          </template>

          <el-form-item label="抽取模式">
            <el-radio-group v-model="overlayForm.mode">
              <el-radio-button value="default">默认抽取</el-radio-button>
              <el-radio-button value="custom_extension">自定义扩展</el-radio-button>
            </el-radio-group>
          </el-form-item>
        </el-form>

        <el-alert
          v-if="overlayError"
          class="overlay-alert"
          type="warning"
          :closable="false"
          show-icon
          :title="overlayError"
        />

        <section v-if="lastOverlaySession" class="overlay-result">
          <div class="section-header">
            <div>
              <h3>抽取结果</h3>
              <p>追溯编号：{{ lastOverlaySession.session.session_id }}</p>
            </div>
            <el-tag :type="sessionStatusMeta(lastOverlaySession.session.session_status).tagType" :title="lastOverlaySession.session.session_status">
              {{ sessionStatusMeta(lastOverlaySession.session.session_status).label }}
            </el-tag>
          </div>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="节点候选">{{ lastOverlaySession.nodes?.length || 0 }}</el-descriptions-item>
            <el-descriptions-item label="关系候选">{{ lastOverlaySession.edges?.length || 0 }}</el-descriptions-item>
            <el-descriptions-item label="资源候选">{{ lastOverlaySession.resources?.length || 0 }}</el-descriptions-item>
            <el-descriptions-item label="来源数">{{ lastOverlaySession.sources?.length || 0 }}</el-descriptions-item>
          </el-descriptions>

          <section v-if="lastOverlaySession.resources?.length" class="overlay-subsection">
            <h4>资源候选</h4>
            <article v-for="resource in lastOverlaySession.resources || []" :key="resource.resource_id" class="resource-candidate">
              <div class="resource-title">{{ resource.title }}</div>
              <p>{{ resource.summary || '暂无摘要' }}</p>
              <el-tag size="small" :type="resourceTypeMeta(resource.resource_type || 'resource').tagType" :title="resource.resource_type || 'resource'">
                {{ resourceTypeMeta(resource.resource_type || 'resource').label }}
              </el-tag>
              <el-tag size="small" type="success">绑定 {{ resource.binding_summary?.count || 0 }}</el-tag>
            </article>
          </section>

          <section v-if="lastOverlaySession.resources?.length" class="overlay-subsection">
            <h4>资源绑定</h4>
            <el-form label-position="top">
              <el-form-item label="资源">
                <el-select v-model="resourceBinding.resourceId" placeholder="选择资源候选" style="width: 100%">
                  <el-option
                    v-for="resource in lastOverlaySession.resources || []"
                    :key="resource.resource_id"
                    :label="resource.title"
                    :value="resource.resource_id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="绑定目标类型">
                <el-radio-group v-model="resourceBinding.targetType">
                  <el-radio-button value="project_node">项目节点</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="绑定目标">
                <el-select v-model="resourceBinding.targetId" filterable placeholder="选择知识点或阶段" style="width: 100%">
                  <el-option
                    v-for="option in resourceTargetOptions"
                    :key="option.id"
                    :label="option.label"
                    :value="option.id"
                  >
                    <span>{{ option.label }}</span>
                    <span class="option-trace-id">{{ option.id }}</span>
                  </el-option>
                </el-select>
              </el-form-item>
              <el-button size="small" type="primary" plain @click="bindOverlayResource">绑定资源</el-button>
            </el-form>
          </section>

          <section class="overlay-subsection">
            <h4>推广到领域包</h4>
            <el-button size="small" :loading="promotionLoading" @click="previewPromotion">预览推广结果（不写入）</el-button>
            <el-descriptions v-if="promotionPreview" class="promotion-summary" :column="1" border size="small">
              <el-descriptions-item label="状态">
                <el-tag
                  size="small"
                  :type="promotionPreviewStatusMeta(promotionPreview.status).tagType"
                  :title="promotionPreviewStatusMeta(promotionPreview.status).detail || promotionPreview.status"
                >
                  {{ promotionPreviewStatusMeta(promotionPreview.status).label }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="候选数">{{ promotionPreview.candidate_count }}</el-descriptions-item>
              <el-descriptions-item label="原领域包指纹">{{ promotionPreview.baseline_pack_hash }}</el-descriptions-item>
              <el-descriptions-item label="推广后指纹">{{ promotionPreview.resulting_pack_hash }}</el-descriptions-item>
              <el-descriptions-item label="资源明细">{{ promotionPreview.resources?.length || 0 }}</el-descriptions-item>
              <el-descriptions-item label="写入说明">预览只校验，不写入领域包、Neo4j 或候选状态。</el-descriptions-item>
            </el-descriptions>
            <el-alert
              v-if="promotionPreview?.errors?.length"
              class="overlay-alert"
              type="warning"
              :closable="false"
              show-icon
              :title="promotionPreview.errors.join('; ')"
            />
            <el-input
              v-model="promotionSecret"
              class="promotion-secret"
              type="password"
              show-password
              placeholder="输入管理员密钥后确认推广"
            />
            <el-button size="small" type="danger" :loading="promotionLoading" @click="commitPromotion">确认推广</el-button>
            <el-alert
              v-if="promotionResult"
              class="overlay-alert"
              :type="promotionResult.status === 'promoted' || promotionResult.reason === 'promoted' ? 'success' : 'info'"
              :closable="false"
              show-icon
              :title="promotionStatusMessage"
            />
          </section>
        </section>

        <div class="drawer-actions">
          <el-button @click="overlayDrawerVisible = false">关闭</el-button>
          <el-button type="primary" :loading="overlaySubmitting" @click="submitOverlayDraft">
            {{ goalDraftResolutionSessionId ? '创建目标扩展草稿' : '创建草稿' }}
          </el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import {
  buildGraphQuery,
  graphApi,
  normalizeGraphPathId,
  normalizeGraphScope,
  type GraphData,
  type GraphEdgeData,
  type GraphElement,
  type GraphEntityMetadata,
  type GraphNodeData,
  type GraphScope,
  type GoalExtensionDraftResponse,
  type OverlayProjectionStatusResponse,
  type OverlayElementGroup,
  type OverlayExtractionSessionResponse,
  type OverlayReviewStatus,
  type OverlaySourceRequest,
  type ReviewStatus,
} from '@/api/modules/graph'
import GraphCanvas from '@/components/Graph/GraphCanvas.vue'
import EntityMetadataDrawer from '@/components/Graph/EntityMetadataDrawer.vue'
import NodeDetail from '@/components/Graph/NodeDetail.vue'
import GraphToolbar from '@/components/Graph/GraphToolbar.vue'
import { GRAPH_CATEGORY_LEGEND, GRAPH_RELATION_LEGEND } from '@/components/Graph/graphMeta'
import { searchApi, type PersistedSearchResult } from '@/api/modules/search'
import { resourceApi } from '@/api/modules/resource'
import {
  formatServiceReason,
  promotionPreviewStatusMeta,
  resourceTypeMeta,
  sessionStatusMeta,
} from '@/utils/displayLabels'

type GraphState = 'loading' | 'ready' | 'empty' | 'error'
type GraphLayout = 'cose' | 'breadthfirst'
type OverlaySourceType = 'pasted_text' | 'search_url' | 'saved_search'
type OverlayExtractionMode = 'default' | 'custom_extension'

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
const SEARCH_NOT_READY = 'SEARCH_NOT_READY'

function createOverlayForm() {
  return {
    sourceType: 'pasted_text' as OverlaySourceType,
    selectedResultIds: [] as string[],
    rawText: '',
    url: '',
    title: '',
    snippet: '',
    summary: '',
    mode: 'default' as OverlayExtractionMode,
  }
}

function firstQueryValue(value: unknown): unknown {
  return Array.isArray(value) ? value[0] : value
}


function normalizeRouteSessionId(value: unknown): string | null {
  const nextValue = firstQueryValue(value)
  return typeof nextValue === 'string' && nextValue.trim() ? nextValue.trim() : null
}

function normalizeRouteNodeId(value: unknown): string | null {
  const nextValue = firstQueryValue(value)
  return typeof nextValue === 'string' && nextValue.trim() ? nextValue.trim() : null
}

function normalizeGoalDraftFlag(value: unknown): boolean {
  const nextValue = firstQueryValue(value)
  return nextValue === '1' || nextValue === 'true'
}

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const projectId = computed(() => projectStore.currentProject?.id)
const elements = ref<GraphElement[]>([])
const layout = ref<GraphLayout>('cose')
const scope = ref<GraphScope>(normalizeGraphScope(route.query.scope))
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
const entityDrawerVisible = ref(false)
const entityLoading = ref(false)
const entityMetadata = ref<GraphEntityMetadata | null>(null)
const projectionStatus = ref<OverlayProjectionStatusResponse | null>(null)
const overlayDrawerVisible = ref(false)
const overlaySubmitting = ref(false)
const overlayError = ref('')
const overlayBridgeMessage = ref('')
const overlayForm = ref(createOverlayForm())
const persistedSearchResults = ref<PersistedSearchResult[]>([])
const lastOverlaySession = ref<OverlayExtractionSessionResponse | null>(null)
const promotionPreview = ref<any | null>(null)
const promotionResult = ref<any | null>(null)
const promotionSecret = ref('')
const promotionLoading = ref(false)
const resourceBinding = ref({ resourceId: '', targetType: 'project_node', targetId: '' })
const categoryLegend = GRAPH_CATEGORY_LEGEND
const relationLegend = GRAPH_RELATION_LEGEND
const requestedScope = computed<GraphScope>(() => normalizeGraphScope(route.query.scope))
const requestedPathId = computed<string | undefined>(() => normalizeGraphPathId(requestedScope.value, route.query.path_id))
const requestedNodeId = computed<string | null>(() => normalizeRouteNodeId(route.query.nodeId))
const requestedSessionId = computed<string | null>(() => normalizeRouteSessionId(route.query.sessionId))
const goalDraftResolutionSessionId = computed<string | null>(() => (
  normalizeGoalDraftFlag(route.query.goalDraft) ? normalizeRouteSessionId(route.query.resolutionSessionId) : null
))
const emptyDescription = computed(() =>
  emptyReason.value === PROJECT_LATEST_PLAN_MISSING
    ? '当前项目尚未生成学习路径，暂时无法展示路径子图；项目图谱仍可显示领域基线与项目扩展草稿。'
    : '当前范围暂无图谱数据，可刷新或先同步领域知识包到 Neo4j',
)
const promotionStatusMessage = computed(() => {
  if (!promotionResult.value) return ''
  if (promotionResult.value.reason === 'promoted') return '推广成功，候选已归档隐藏。'
  return formatServiceReason(promotionResult.value.reason) || promotionPreviewStatusMeta(promotionResult.value.status).label || '推广状态已更新'
})
const projectionAlertType = computed(() => projectionStatus.value?.status === 'ok' ? 'success' : 'warning')
const projectionStatusTitle = computed(() => {
  if (!projectionStatus.value) return ''
  const status = projectionStatus.value.status === 'ok' ? '项目扩展投影已同步' : '项目扩展投影需关注'
  const reason = formatServiceReason(projectionStatus.value.reason)
  return reason ? `${status}：${reason}` : status
})
const resourceTargetOptions = computed(() => nodes.value.map((node) => ({
  id: node.id,
  label: node.label || node.id,
})))
const graphQuery = computed(() => buildGraphQuery({
  scope: scope.value,
  path_id: requestedPathId.value,
  nodeId: requestedNodeId.value || undefined,
}))

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
  projectionStatus.value = null
}

function resetOverlayState() {
  overlayDrawerVisible.value = false
  overlaySubmitting.value = false
  overlayError.value = ''
  overlayBridgeMessage.value = ''
  overlayForm.value = createOverlayForm()
  lastOverlaySession.value = null
  promotionPreview.value = null
  promotionResult.value = null
  promotionSecret.value = ''
  resourceBinding.value = { resourceId: '', targetType: 'project_node', targetId: '' }
}

function graphRouteQuery(nextScope: GraphScope, nodeId?: string | null, sessionId?: string | null) {
  return {
    ...buildGraphQuery({
      scope: nextScope,
      path_id: nextScope === 'path' ? requestedPathId.value : undefined,
      nodeId: nodeId || undefined,
    }),
    ...(sessionId ? { sessionId } : {}),
  }
}

async function replaceGraphRoute(nextScope: GraphScope, nodeId?: string | null, sessionId: string | null = requestedSessionId.value) {
  await router.replace({
    name: 'Knowledge',
    query: Object.fromEntries(
      Object.entries(graphRouteQuery(nextScope, nodeId, sessionId)).filter((entry): entry is [string, string] => typeof entry[1] === 'string'),
    ),
  })
}

async function loadPersistedSearchResults() {
  if (!projectId.value) {
    persistedSearchResults.value = []
    return
  }
  persistedSearchResults.value = await searchApi.listPersistedResults(projectId.value)
}

async function loadProjectionStatus() {
  if (!projectId.value) {
    projectionStatus.value = null
    return
  }
  try {
    projectionStatus.value = await graphApi.getOverlayProjectionStatus(projectId.value)
  } catch {
    projectionStatus.value = {
      project_id: projectId.value,
      status: 'error',
      ready: false,
      in_sync: false,
      reason: 'projection_status_unavailable',
    }
  }
}

function applyGraphData(data: GraphData) {
  const nextElements = data.elements ?? []

  elements.value = nextElements
  errorMessage.value = ''
  lastRefreshError.value = ''
  emptyReason.value = data.empty_reason
  graphState.value = nextElements.length > 0 ? 'ready' : 'empty'
}

async function loadRequestedOverlaySession() {
  if (!projectId.value || !requestedSessionId.value) {
    return
  }

  try {
    lastOverlaySession.value = await graphApi.getOverlayExtractionSession(
      projectId.value,
      requestedSessionId.value,
    )
    overlayDrawerVisible.value = true
  } catch (error: any) {
    resetOverlayState()
    overlayError.value = error?.response?.data?.error || '扩展抽取会话加载失败'
  }
}

async function focusRequestedNode() {
  const nodeId = requestedNodeId.value
  if (!nodeId || graphState.value !== 'ready') {
    return
  }

  await nextTick()
  const focused = graphRef.value?.focusNode(nodeId)
  if (focused) {
    selectedNodeId.value = nodeId
  }
}

function getElementGroup(data: GraphNodeData | GraphEdgeData): OverlayElementGroup {
  return 'source' in data && 'target' in data ? 'edges' : 'nodes'
}

function normalizeOverlayReviewStatus(status: string): OverlayReviewStatus {
  return status === 'rejected' ? 'rejected' : status as OverlayReviewStatus
}

function patchElementLifecycle(
  elementId: string,
  lifecycle: {
    review_status?: string
    planning_enabled?: boolean
    validation_status?: string
    promotion_status?: string
  },
) {
  elements.value = elements.value.map((element) => {
    if (element.data.id !== elementId) {
      return element
    }

    return {
      ...element,
      data: {
        ...element.data,
        ...lifecycle,
      },
    } as GraphElement
  })
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
    const data = await graphApi.getGraph(projectId.value, graphQuery.value)
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
      resetOverlayState()
      return
    }

    if (nextProjectId !== previousProjectId) {
      resetGraphState()
      resetOverlayState()
    }

    scope.value = requestedScope.value
    await loadGraph()
    await loadProjectionStatus()
    await loadPersistedSearchResults()
    await loadRequestedOverlaySession()
    await openGoalDraftEntry()
    await focusRequestedNode()
  },
  { immediate: true },
)

watch([requestedScope, requestedPathId], async ([nextScope, nextPathId], [previousScope, previousPathId]) => {
  if (!projectId.value || (scope.value === nextScope && nextScope === previousScope && nextPathId === previousPathId)) {
    return
  }

  scope.value = nextScope
  selectedNodeId.value = null
  resetOverlayState()
  await loadGraph()
  await loadProjectionStatus()
  await focusRequestedNode()
})

watch([requestedPathId, requestedNodeId, graphState], async () => {
  await focusRequestedNode()
})

async function syncRequestedOverlaySession(nextSessionId: string | null) {
  if (!nextSessionId) {
    resetOverlayState()
    return
  }
  await loadRequestedOverlaySession()
}

watch(requestedSessionId, syncRequestedOverlaySession)
watch(goalDraftResolutionSessionId, async (nextSessionId) => {
  if (!nextSessionId) return
  resetOverlayState()
  await openGoalDraftEntry()
})

function onLayoutChange(newLayout: string) {
  layout.value = newLayout as GraphLayout
}

function onNodeClick(data: GraphNodeData) {
  selectedNodeId.value = data.id
  void replaceGraphRoute(scope.value, data.id)
}

function onSearch(keyword: string) {
  graphRef.value?.highlightBySearch(keyword)
}

async function onScopeChange(nextScope: GraphScope) {
  if (scope.value === nextScope) return
  scope.value = nextScope
  selectedNodeId.value = null
  resetOverlayState()
  await replaceGraphRoute(nextScope)
  await loadGraph()
  await loadProjectionStatus()
  await focusRequestedNode()
}

async function onRefresh() {
  await loadGraph()
  await loadProjectionStatus()
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
    await loadProjectionStatus()
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
  const node = nodes.value.find((item) => item.id === nodeId)
  try {
    if (node?.origin === 'overlay') {
      const result = await graphApi.reviewOverlayElement(
        projectId.value,
        'nodes',
        nodeId,
        normalizeOverlayReviewStatus(status),
      )
      selectedNodeId.value = nodeId
      patchElementLifecycle(nodeId, result)
      graphRef.value?.setNodeReviewStatus(nodeId, result.review_status)
    } else {
      const nextStatus = status as ReviewStatus
      await graphApi.reviewNode(projectId.value, nodeId, nextStatus)
      selectedNodeId.value = nodeId
      updateNodeReviewStatus(nodeId, nextStatus)
      graphRef.value?.setNodeReviewStatus(nodeId, nextStatus)
    }
    ElMessage.success('节点审核状态已更新')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '节点审核失败')
  }
}

async function onReviewEdge(edgeId: string, status: string) {
  if (!projectId.value) return
  const edge = edges.value.find((item) => item.id === edgeId)
  try {
    if (edge?.origin === 'overlay') {
      const result = await graphApi.reviewOverlayElement(
        projectId.value,
        'edges',
        edgeId,
        normalizeOverlayReviewStatus(status),
      )
      patchElementLifecycle(edgeId, result)
      graphRef.value?.setEdgeReviewStatus(edgeId, result.review_status)
    } else {
      const nextStatus = status as ReviewStatus
      await graphApi.reviewEdge(projectId.value, edgeId, nextStatus)
      updateEdgeReviewStatus(edgeId, nextStatus)
      graphRef.value?.setEdgeReviewStatus(edgeId, nextStatus)
    }
    ElMessage.success('边审核状态已更新')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '边审核失败')
  }
}

async function onSetOverlayPlanning(data: GraphNodeData | GraphEdgeData, enabled: boolean) {
  if (!projectId.value || data.origin !== 'overlay') return
  try {
    const result = await graphApi.setOverlayPlanning(
      projectId.value,
      getElementGroup(data),
      data.id,
      enabled,
    )
    patchElementLifecycle(data.id, result)
    ElMessage.success(enabled ? '已允许参与规划' : '已从规划中排除')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '规划开关更新失败')
  }
}

async function openOverlayDrawer() {
  overlayDrawerVisible.value = true
  overlayError.value = ''
  overlayBridgeMessage.value = ''
  await loadPersistedSearchResults()
}

async function openGoalDraftEntry() {
  if (!goalDraftResolutionSessionId.value) return
  overlayDrawerVisible.value = true
  overlayError.value = ''
  overlayBridgeMessage.value = ''
  overlayForm.value = createOverlayForm()
  await loadPersistedSearchResults()
}

function buildOverlaySourcePayload(): OverlaySourceRequest | null {
  const form = overlayForm.value
  if (form.sourceType === 'pasted_text') {
    const rawText = form.rawText.trim()
    if (!rawText) {
      overlayError.value = '请先粘贴资料文本'
      return null
    }
    return {
      source_type: 'pasted_text',
      raw_text: rawText,
      raw_text_excerpt: rawText.slice(0, 500),
      summary: form.summary.trim() || null,
    }
  }

  if (form.sourceType === 'search_url') {
    const url = form.url.trim()
    if (!url) {
      overlayError.value = '请填写搜索结果 URL'
      return null
    }

    return {
      source_type: 'search_url',
      url,
      title: form.title.trim() || url,
      snippet: form.snippet.trim() || null,
      summary: form.summary.trim() || null,
      provider: 'manual',
    }
  }

  return null
}

async function resolveOverlaySourceIds() {
  const form = overlayForm.value
  if (form.sourceType === 'saved_search') {
    if (!projectId.value || !form.selectedResultIds.length) {
      overlayError.value = '请选择已保存搜索结果'
      return null
    }
    const bridged = await searchApi.bridgeOverlaySources(projectId.value, form.selectedResultIds)
    overlayBridgeMessage.value = `已解析 ${bridged.source_ids.length} 个项目扩展来源，${bridged.results.filter((item) => item.reused).length} 个复用。`
    return bridged.source_ids
  }

  const sourcePayload = buildOverlaySourcePayload()
  if (!sourcePayload || !projectId.value) return null
  const source = await graphApi.createOverlaySource(projectId.value, sourcePayload)
  return [source.source_id]
}

function getOverlayErrorMessage(error: any) {
  const code = error?.response?.data?.error
  if (code === SEARCH_NOT_READY) {
    return '搜索服务尚未就绪，自定义扩展暂不可用；领域基线图谱浏览不受影响。'
  }
  return code || error?.message || '扩展草稿创建失败'
}

async function bindOverlayResource() {
  if (!projectId.value || !resourceBinding.value.resourceId || !resourceBinding.value.targetId.trim()) {
    overlayError.value = '请选择资源和绑定目标'
    return
  }
  try {
    await resourceApi.bindProjectResource(projectId.value, {
      resource_id: resourceBinding.value.resourceId,
      target_type: resourceBinding.value.targetType as 'project_node' | 'path_stage',
      target_id: resourceBinding.value.targetId.trim(),
      binding_source: 'overlay',
    })
    if (lastOverlaySession.value) {
      lastOverlaySession.value = await graphApi.getOverlayExtractionSession(projectId.value, lastOverlaySession.value.session.session_id)
    }
    await loadProjectionStatus()
    ElMessage.success('资源绑定已保存')
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
  if (!projectId.value) return
  if (!promotionSecret.value.trim()) {
    overlayError.value = '请输入 admin secret'
    return
  }
  promotionLoading.value = true
  try {
    promotionResult.value = await graphApi.commitOverlayPromotion(projectId.value, {
      admin_secret: promotionSecret.value,
      requested_by: 'frontend',
    })
    promotionSecret.value = ''
    await loadGraph()
    await loadProjectionStatus()
    if (lastOverlaySession.value) {
      lastOverlaySession.value = await graphApi.getOverlayExtractionSession(projectId.value, lastOverlaySession.value.session.session_id)
    }
  } catch (error: any) {
    const code = error?.response?.data?.error
    overlayError.value = formatServiceReason(code) || '确认推广失败'
    promotionResult.value = error?.response?.data?.details?.preview || error?.response?.data?.details || null
  } finally {
    promotionLoading.value = false
  }
}

async function submitOverlayDraft() {
  if (!projectId.value) return

  overlaySubmitting.value = true
  overlayError.value = ''
  overlayBridgeMessage.value = ''

  try {
    if (goalDraftResolutionSessionId.value) {
      lastOverlaySession.value = await graphApi.createGoalExtensionDraft(
        projectId.value,
        goalDraftResolutionSessionId.value,
      ) as GoalExtensionDraftResponse
    } else {
      const sourceIds = await resolveOverlaySourceIds()
      if (!sourceIds) return
      lastOverlaySession.value = await graphApi.createOverlayExtractionSession(projectId.value, {
        source_ids: sourceIds,
        mode: overlayForm.value.mode,
      })
    }
    overlayForm.value = createOverlayForm()
    ElMessage.success('扩展草稿已创建，请在项目图谱中审核候选节点和关系')
    scope.value = 'project'
    await replaceGraphRoute('project', null, lastOverlaySession.value.session.session_id)
    await loadGraph()
    await loadProjectionStatus()
  } catch (error: any) {
    overlayError.value = getOverlayErrorMessage(error)
  } finally {
    overlaySubmitting.value = false
  }
}

async function onShowEntities() {
  if (!projectId.value) return

  entityDrawerVisible.value = true
  entityLoading.value = true

  try {
    entityMetadata.value = await graphApi.getGraphEntities(projectId.value)
  } catch {
    entityDrawerVisible.value = false
  } finally {
    entityLoading.value = false
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

.overlay-drawer {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.overlay-alert {
  margin-bottom: 4px;
}

.overlay-result {
  padding: 14px;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  background: #fafafa;
}

.overlay-result h3 {
  margin: 0;
  font-size: 16px;
  color: #303133;
}

.overlay-result p {
  margin: 4px 0 0;
  font-size: 12px;
  color: #909399;
  word-break: break-all;
}
.overlay-subsection {
  margin-top: 14px;
}
.overlay-subsection h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: #303133;
}
.resource-candidate {
  padding: 10px;
  margin-bottom: 8px;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  background: #fff;
}
.resource-title {
  font-weight: 600;
  color: #303133;
}
.option-trace-id {
  float: right;
  margin-left: 12px;
  color: #c0c4cc;
  font-size: 12px;
}
.promotion-summary,
.promotion-secret {
  margin-top: 10px;
}

.drawer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 8px;
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
