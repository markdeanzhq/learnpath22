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
        @zoom-in="onZoomIn"
        @zoom-out="onZoomOut"
        @fit-view="onFitView"
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
        <GraphLegendPanel
          :category-legend="categoryLegend"
          :relation-legend="relationLegend"
        />
        <GraphStatusPanel
          :scope-label="graphScopeLabel"
          :status-hint="graphStatusHint"
          :node-count="graphNodeCount"
          :edge-count="graphEdgeCount"
          :overlay-preflight="overlayPreflight"
          :overlay-preflight-tag-type="overlayPreflightTagType"
          :show-graph-cache-diagnostics="showGraphCacheDiagnostics"
          :graph-cache-diagnostic-items="graphCacheDiagnosticItems"
          :graph-cache-stats-loading="graphCacheStatsLoading"
          :graph-cache-stats-error="graphCacheStatsError"
        />
        <el-alert
          v-if="projectionStatus && projectionStatus.status !== 'empty'"
          class="graph-alert"
          :type="projectionAlertType"
          :closable="false"
          show-icon
          :title="projectionStatusTitle"
        />
        <OverlayPreflightPanel
          v-if="overlayPreflight"
          :preflight="overlayPreflight"
          :tag-type="overlayPreflightTagType"
          :status-label="overlayPreflightStatusLabel"
          :guidance="overlayPreflightGuidance"
          :issues="overlayPreflightIssues"
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

        <div v-else-if="graphState === 'loading'" class="graph-state-wrap graph-loading-state" data-testid="graph-loading-skeleton">
          <div class="graph-skeleton-panel">
            <div class="graph-skeleton-header"></div>
            <div class="graph-skeleton-body">
              <span v-for="index in 8" :key="index" class="graph-skeleton-node"></span>
            </div>
            <p>正在整理知识节点、审核状态与扩展候选，请稍候。</p>
          </div>
        </div>

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
      v-if="selectedNode"
      :node="selectedNode"
      @review-edge="onReviewEdge"
      @set-overlay-planning="onSetOverlayPlanning"
    />
    <EntityMetadataDrawer
      v-if="entityDrawerVisible || entityLoading || entityMetadata"
      v-model="entityDrawerVisible"
      :loading="entityLoading"
      :metadata="entityMetadata"
    />

    <KnowledgeOverlayDrawer
      v-model:visible="overlayDrawerVisible"
      v-model:display-mode="displayMode"
      v-model:overlay-draft-mode="overlayDraftMode"
      v-model:overlay-candidate-filter="overlayCandidateFilter"
      :overlay-submitting="overlaySubmitting"
      :overlay-extraction-preview-loading="overlayExtractionPreviewLoading"
      :active-goal-draft-resolution-session-id="activeGoalDraftResolutionSessionId"
      :manual-goal-draft-loading="manualGoalDraftLoading"
      :goal-draft-proposal-loading="goalDraftProposalLoading"
      :goal-draft-inbox-proposal="goalDraftInboxProposal"
      :goal-draft-proposal-dismissed="goalDraftProposalDismissed"
      :goal-draft-inbox-missing-concepts="goalDraftInboxMissingConcepts"
      :goal-draft-inbox-counts="goalDraftInboxCounts"
      :goal-draft-inbox-nodes="goalDraftInboxNodes"
      :goal-draft-inbox-edges="goalDraftInboxEdges"
      :goal-draft-inbox-resources="goalDraftInboxResources"
      :overlay-form="overlayForm"
      :manual-overlay-mode="manualOverlayMode"
      :persisted-search-results="persistedSearchResults"
      :overlay-bridge-message="overlayBridgeMessage"
      :overlay-extraction-preview="overlayExtractionPreview"
      :normalized-preview-payload="normalizedPreviewPayload"
      :selected-preview-counts="selectedPreviewCounts"
      :overlay-candidate-validation="overlayCandidateValidation"
      :is-preview-candidate-selected="isPreviewCandidateSelected"
      :candidate-title="candidateTitle"
      :edge-candidate-summary="edgeCandidateSummary"
      :overlay-error="overlayError"
      :last-overlay-session="lastOverlaySession"
      :show-technical-details="showTechnicalDetails"
      :show-audit-details="showAuditDetails"
      :overlay-session-guide="overlaySessionGuide"
      :overlay-session-stats="overlaySessionStats"
      :overlay-workflow-steps="overlayWorkflowSteps"
      :overlay-workflow-current-step="overlayWorkflowCurrentStep"
      :overlay-candidate-filter-counts="overlayCandidateFilterCounts"
      :filtered-overlay-candidate-count="filteredOverlayCandidateCount"
      :has-overlay-candidate-repair-target="Boolean(overlayCandidateRepairTarget)"
      :overlay-candidate-repair-target-label="overlayCandidateRepairTargetLabel"
      :filtered-overlay-nodes="filteredOverlayNodes"
      :filtered-overlay-edges="filteredOverlayEdges"
      :filtered-overlay-resources="filteredOverlayResources"
      :goal-extension-draft-details="goalExtensionDraftDetails"
      :goal-draft-missing-concepts="goalDraftMissingConcepts"
      :goal-draft-review-notes="goalDraftReviewNotes"
      :goal-draft-review-focus="goalDraftReviewFocus"
      :validation-error-message="validationErrorMessage"
      :resource-binding="resourceBinding"
      :resource-target-options="resourceTargetOptions"
      :promotion-preview="promotionPreview"
      :promotion-result="promotionResult"
      :promotion-secret="promotionSecret"
      :promotion-loading="promotionLoading"
      :promotion-status-message="promotionStatusMessage"
      @update-overlay-form="updateOverlayForm"
      @prepare-goal-draft="prepareGoalDraftFromCurrentProject"
      @load-goal-draft-proposal="loadGoalDraftProposal"
      @dismiss-goal-draft-proposal="dismissGoalDraftProposal"
      @preview-overlay-extraction-payload="previewOverlayExtractionPayload"
      @toggle-preview-candidate="togglePreviewCandidate"
      @open-first-repairable="openFirstRepairableCandidate"
      @edit-node="openNodeCandidateEditor"
      @edit-edge="openEdgeCandidateEditor"
      @edit-resource="openResourceCandidateEditor"
      @update-resource-binding="updateResourceBindingField"
      @update:promotion-secret="promotionSecret = $event"
      @bind-resource="bindOverlayResource"
      @preview-promotion="previewPromotion"
      @commit-promotion="commitPromotion"
      @submit-overlay-draft="submitOverlayDraft"
    />

    <OverlayCandidateEditorDialog
      v-model:visible="candidateEditor.visible"
      :candidate-editor="candidateEditor"
      :candidate-editor-issue-summary="candidateEditorIssueSummary"
      :candidate-editor-quick-fix-errors="candidateEditorQuickFixErrors"
      :overlay-endpoint-options="overlayEndpointOptions"
      :candidate-editor-field-issue="candidateEditorFieldIssue"
      :quick-fix-label="quickFixLabel"
      @quick-fix="applyCandidateQuickFix"
      @save="saveCandidateEditor"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import { useDisplayMode } from '@/composables/useDisplayMode'
import { useProjectStore } from '@/stores/project'
import GraphLegendPanel from './GraphLegendPanel.vue'
import GraphStatusPanel from './GraphStatusPanel.vue'
import OverlayPreflightPanel from './OverlayPreflightPanel.vue'
import { useFullscreenToggle } from './composables/useFullscreenToggle'
import { useGraphCacheDiagnostics } from './composables/useGraphCacheDiagnostics'
import { useEntityMetadataDrawer } from './composables/useEntityMetadataDrawer'
import { useGraphRouteSync } from './composables/useGraphRouteSync'
import { useGraphStatusText } from './composables/useGraphStatusText'
import { useGraphToolbarActions, type GraphCanvasActionHandle, type GraphLayout } from './composables/useGraphToolbarActions'
import { useGraphWorkspaceOrchestration } from './composables/useGraphWorkspaceOrchestration'
import { useGraphWorkspaceLoader, type GraphWorkspaceLoadOptions } from './composables/useGraphWorkspaceLoader'
import { useGraphReviewActions } from './composables/useGraphReviewActions'
import { useSelectedNodeContext } from './composables/useSelectedNodeContext'
import { useOverlayCandidateEditor } from './composables/useOverlayCandidateEditor'
import { getOverlayErrorMessage } from './composables/useOverlayErrorMessage'
import { useOverlayPostActions } from './composables/useOverlayPostActions'
import { useOverlayRepairActions } from './composables/useOverlayRepairActions'
import {
  useOverlayCandidateWorkflow,
  type CandidateIssueFilter,
  type OverlaySessionView,
} from './composables/useOverlayCandidateWorkflow'
import { useOverlayDraftInput, type OverlayFormState } from './composables/useOverlayDraftInput'
import {
  graphApi,
  type GraphElement,
} from '@/api/modules/graph'
import { GRAPH_CATEGORY_LEGEND, GRAPH_RELATION_LEGEND } from '@/components/Graph/graphMeta'

const GraphToolbar = defineAsyncComponent(() => import('@/components/Graph/GraphToolbar.vue'))
const GraphCanvas = defineAsyncComponent(() => import('@/components/Graph/GraphCanvas.vue'))
const NodeDetail = defineAsyncComponent(() => import('@/components/Graph/NodeDetail.vue'))
const EntityMetadataDrawer = defineAsyncComponent(() => import('@/components/Graph/EntityMetadataDrawer.vue'))
const KnowledgeOverlayDrawer = defineAsyncComponent(() => import('./KnowledgeOverlayDrawer.vue'))
const OverlayCandidateEditorDialog = defineAsyncComponent(() => import('./OverlayCandidateEditorDialog.vue'))

type GraphCanvasHandle = GraphCanvasActionHandle & {
  focusNode: (nodeId: string) => boolean
  setNodeReviewStatus: (nodeId: string, status: string) => void
  setEdgeReviewStatus: (edgeId: string, status: string) => void
}

const projectStore = useProjectStore()
const { displayMode, showAuditDetails, showTechnicalDetails } = useDisplayMode()
const projectId = computed(() => projectStore.currentProject?.id)
const currentProject = computed(() => projectStore.currentProject)
const layout = ref<GraphLayout>('cose')
const {
  scope,
  requestedScope,
  requestedPathId,
  requestedNodeId,
  requestedSessionId,
  goalDraftResolutionSessionId,
  graphQuery,
  replaceGraphRoute,
} = useGraphRouteSync()
const syncing = ref(false)
const selectedNodeId = ref<string | null>(null)
const graphRef = ref<GraphCanvasHandle>()
const { pageRef, toggleFullscreen } = useFullscreenToggle<HTMLDivElement>()
const {
  graphCacheStatsLoading,
  graphCacheStatsError,
  graphCacheDiagnosticItems,
  showGraphCacheDiagnostics,
  refreshGraphCacheStats,
} = useGraphCacheDiagnostics(() => graphApi.getGraphCacheStats())
const reviewMode = ref(false)
const {
  entityDrawerVisible,
  entityLoading,
  entityMetadata,
  onShowEntities,
} = useEntityMetadataDrawer(projectId)
const overlayDrawerVisible = ref(false)
const overlayError = ref('')
const lastOverlaySession = ref<OverlaySessionView | null>(null)
const overlayCandidateFilter = ref<CandidateIssueFilter>('all')
let graphWorkspaceLoader: ReturnType<typeof useGraphWorkspaceLoader> | null = null
const categoryLegend = GRAPH_CATEGORY_LEGEND
const relationLegend = GRAPH_RELATION_LEGEND
function isNodeElement(element: GraphElement): element is Extract<GraphElement, { group: 'nodes' }> {
  return element.group === 'nodes'
}

function isEdgeElement(element: GraphElement): element is Extract<GraphElement, { group: 'edges' }> {
  return element.group === 'edges'
}

const {
  overlaySubmitting,
  overlayExtractionPreviewLoading,
  overlayBridgeMessage,
  overlayForm,
  overlayDraftMode,
  overlayExtractionPreview,
  overlayCandidateValidation,
  goalDraftProposalLoading,
  manualGoalDraftLoading,
  manualGoalDraftResolutionSessionId,
  goalDraftProposalDismissed,
  activeGoalDraftResolutionSessionId,
  goalExtensionDraftDetails,
  goalDraftMissingConcepts,
  goalDraftReviewNotes,
  goalDraftReviewFocus,
  manualOverlayMode,
  goalDraftInboxProposal,
  goalDraftInboxCounts,
  goalDraftInboxMissingConcepts,
  goalDraftInboxNodes,
  goalDraftInboxEdges,
  goalDraftInboxResources,
  normalizedPreviewPayload,
  selectedPreviewCounts,
  openOverlayDrawer,
  prepareGoalDraftFromCurrentProject,
  openGoalDraftEntry,
  loadGoalDraftProposal,
  dismissGoalDraftProposal,
  togglePreviewCandidate,
  isPreviewCandidateSelected,
  previewOverlayExtractionPayload,
  submitOverlayDraft,
  resetOverlayDraftInput,
  applyWorkspaceGoalDraftProposal,
  prepareWorkspaceGoalDraftLoading,
  candidateTitle,
  edgeCandidateSummary,
} = useOverlayDraftInput({
  projectId,
  currentProject,
  routeGoalDraftResolutionSessionId: goalDraftResolutionSessionId,
  overlayDrawerVisible,
  overlayError,
  lastOverlaySession,
  loadPersistedSearchResults,
  onDraftCreated: async (session) => {
    scope.value = 'project'
    await replaceGraphRoute('project', null, session.session.session_id)
    await loadGraphWorkspace()
  },
  getErrorMessage: getOverlayErrorMessage,
  notifySuccess: (message) => ElMessage.success(message),
})
const workspaceLoader = useGraphWorkspaceLoader({
  projectId,
  graphQuery,
  requestedSessionId,
  activeGoalDraftResolutionSessionId,
  overlayDrawerVisible,
  overlayError,
  lastOverlaySession,
  selectedNodeId,
  goalDraftProposalLoading,
  resetOverlayState,
  prepareWorkspaceGoalDraftLoading,
  applyWorkspaceGoalDraftProposal,
  refreshGraphCacheStats,
  focusRequestedNode,
  notifyError: (message) => ElMessage.error(message),
})
graphWorkspaceLoader = workspaceLoader
const {
  elements,
  graphState,
  loading,
  errorMessage,
  lastRefreshError,
  emptyReason,
  projectionStatus,
  overlayPreflight,
  persistedSearchResults,
} = workspaceLoader
const {
  onLayoutChange,
  onNodeClick,
  onSearch,
  onZoomIn,
  onZoomOut,
  onFitView,
  onScopeChange,
  onRefresh,
  onSync,
} = useGraphToolbarActions({
  projectId,
  scope,
  layout,
  elements,
  selectedNodeId,
  syncing,
  errorMessage,
  lastRefreshError,
  emptyReason,
  graphState,
  graphRef,
  resetOverlayState,
  replaceGraphRoute,
  loadGraphWorkspace,
  notifySuccess: (message) => ElMessage.success(message),
  notifyError: (message) => ElMessage.error(message),
})
const nodes = computed(() => elements.value.filter(isNodeElement).map((element) => element.data))
const edges = computed(() => elements.value.filter(isEdgeElement).map((element) => element.data))
const {
  overlaySessionGuide,
  overlaySessionStats,
  overlayWorkflowSteps,
  overlayWorkflowCurrentStep,
  overlayPreflightTagType,
  overlayPreflightStatusLabel,
  overlayPreflightIssues,
  overlayPreflightGuidance,
  filteredOverlayNodes,
  filteredOverlayEdges,
  filteredOverlayResources,
  overlayCandidateFilterCounts,
  filteredOverlayCandidateCount,
  overlayCandidateRepairTarget,
  overlayCandidateRepairTargetLabel,
  overlayEndpointOptions,
} = useOverlayCandidateWorkflow({
  lastOverlaySession,
  overlayPreflight,
  nodes,
  overlayCandidateFilter,
})
const {
  candidateEditor,
  candidateEditorIssueSummary,
  candidateEditorQuickFixErrors,
  candidateEditorFieldIssue,
  openNodeCandidateEditor,
  openEdgeCandidateEditor,
  openResourceCandidateEditor,
  saveCandidateEditor,
  resetCandidateEditor,
  validationErrorMessage,
  quickFixLabel,
  applyCandidateQuickFix,
} = useOverlayCandidateEditor({
  projectId,
  lastOverlaySession,
  overlayError,
  refreshAfterSave: async () => {
    await Promise.all([loadOverlayPreflight(), loadGraphWorkspace({ includeRequestedOverlaySession: true })])
  },
  getErrorMessage: getOverlayErrorMessage,
  notifySuccess: (message) => ElMessage.success(message),
})
const { openFirstRepairableCandidate } = useOverlayRepairActions({
  overlayCandidateRepairTarget,
  openNodeCandidateEditor,
  openEdgeCandidateEditor,
  openResourceCandidateEditor,
})
const {
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
} = useOverlayPostActions({
  projectId,
  nodes,
  lastOverlaySession,
  overlayError,
  refreshProjectionStatus: loadProjectionStatus,
  refreshGraphWorkspace: async () => { await loadGraphWorkspace() },
  notifySuccess: (message) => ElMessage.success(message),
})
function updateOverlayForm(nextOverlayForm: OverlayFormState) {
  overlayForm.value = nextOverlayForm
}

function updateResourceBindingField(field: 'resourceId' | 'targetType' | 'targetId', value: string) {
  const nextResourceBinding = { ...resourceBinding.value }
  if (field === 'targetType') {
    nextResourceBinding.targetType = value === 'path_stage' ? 'path_stage' : 'project_node'
  } else {
    nextResourceBinding[field] = value
  }
  resourceBinding.value = nextResourceBinding
}
const {
  onReviewNode,
  onReviewEdge,
  onSetOverlayPlanning,
} = useGraphReviewActions({
  projectId,
  nodes,
  edges,
  elements,
  selectedNodeId,
  refreshOverlayPreflight: loadOverlayPreflight,
  setCanvasNodeReviewStatus: (nodeId, status) => graphRef.value?.setNodeReviewStatus(nodeId, status),
  setCanvasEdgeReviewStatus: (edgeId, status) => graphRef.value?.setEdgeReviewStatus(edgeId, status),
  notifySuccess: (message) => ElMessage.success(message),
  notifyError: (message) => ElMessage.error(message),
})
const graphNodeCount = computed(() => nodes.value.length)
const graphEdgeCount = computed(() => edges.value.length)
const {
  emptyDescription,
  projectionAlertType,
  projectionStatusTitle,
  graphScopeLabel,
  graphStatusHint,
} = useGraphStatusText({
  scope,
  graphState,
  errorMessage,
  emptyReason,
  projectionStatus,
})
const { selectedNode } = useSelectedNodeContext({
  nodes,
  edges,
  selectedNodeId,
})

function resetGraphState() {
  requireGraphWorkspaceLoader().resetGraphState()
}

function resetOverlayState() {
  resetOverlayDraftInput(activeGoalDraftResolutionSessionId.value ? 'goal_draft' : 'manual')
  overlayCandidateFilter.value = 'all'
  resetCandidateEditor()
  lastOverlaySession.value = null
  resetOverlayPostActions()
}

function requireGraphWorkspaceLoader() {
  if (!graphWorkspaceLoader) {
    throw new Error('Graph workspace loader is not initialized')
  }
  return graphWorkspaceLoader
}

function abortGraphLoad() {
  requireGraphWorkspaceLoader().abortGraphLoad()
}

async function loadPersistedSearchResults() {
  await requireGraphWorkspaceLoader().loadPersistedSearchResults()
}

async function loadProjectionStatus() {
  await requireGraphWorkspaceLoader().loadProjectionStatus()
}

async function loadOverlayPreflight() {
  await requireGraphWorkspaceLoader().loadOverlayPreflight()
}

async function loadRequestedOverlaySession() {
  await requireGraphWorkspaceLoader().loadRequestedOverlaySession()
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

async function loadGraphWorkspace(options: GraphWorkspaceLoadOptions = {}) {
  await requireGraphWorkspaceLoader().loadGraphWorkspace(options)
}

const graphWorkspaceOrchestration = useGraphWorkspaceOrchestration({
  projectId,
  nodes,
  scope,
  requestedScope,
  requestedPathId,
  requestedNodeId,
  requestedSessionId,
  activeGoalDraftResolutionSessionId,
  manualGoalDraftResolutionSessionId,
  graphState,
  selectedNodeId,
  abortGraphLoad,
  resetGraphState,
  resetOverlayState,
  loadRequestedOverlaySession,
  loadGraphWorkspace,
  focusRequestedNode,
  openGoalDraftEntry,
})

async function syncRequestedOverlaySession(nextSessionId: string | null) {
  await graphWorkspaceOrchestration.syncRequestedOverlaySession(nextSessionId)
}
void syncRequestedOverlaySession
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

.graph-loading-state {
  padding: 24px;
}

.graph-skeleton-panel {
  width: min(520px, 80%);
  padding: 24px;
  border: 1px solid #ebeef5;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(31 45 61 / 8%);
}

.graph-skeleton-header {
  width: 42%;
  height: 14px;
  margin: 0 auto 24px;
  border-radius: 999px;
  background: linear-gradient(90deg, #ebeef5 25%, #f5f7fa 50%, #ebeef5 75%);
}

.graph-skeleton-body {
  position: relative;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  padding: 12px 32px;
}

.graph-skeleton-node {
  width: 42px;
  height: 42px;
  margin: 0 auto;
  border-radius: 50%;
  background: linear-gradient(135deg, #d9ecff, #ecf5ff);
}

.graph-skeleton-panel p {
  margin: 22px 0 0;
  color: #909399;
  font-size: 13px;
  text-align: center;
}

@media (max-width: 768px) {
  .page-container {
    padding: 12px;
    height: auto;
  }

}
</style>
