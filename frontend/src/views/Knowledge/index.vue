<template>
  <div class="page-container" ref="pageRef">
    <el-card
      shadow="never"
      class="graph-card"
      :body-style="{ padding: 0, display: 'flex', flexDirection: 'column', height: 'calc(100vh - 160px)' }"
    >
      <GraphStatePanel v-if="!projectId" state="no-project" />

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

        <GraphStatePanel
          v-else
          :state="graphState"
          :empty-description="emptyDescription"
          :error-message="errorMessage"
          :syncing="syncing"
          @refresh="onRefresh"
          @sync="onSync"
        />
      </div>
    </el-card>

    <KnowledgeSidePanels
      :selected-node="selectedNode"
      :entity-drawer-visible="entityDrawerVisible"
      :entity-loading="entityLoading"
      :entity-metadata="entityMetadata"
      :overlay-drawer-props="overlayDrawerProps"
      :candidate-editor-dialog-props="candidateEditorDialogProps"
      @review-edge="onReviewEdge"
      @set-overlay-planning="onSetOverlayPlanning"
      @update:entity-drawer-visible="entityDrawerVisible = $event"
      @update-overlay-drawer-visible="overlayDrawerVisible = $event"
      @update-display-mode="displayMode = $event"
      @update-overlay-draft-mode="overlayDraftMode = $event"
      @update-overlay-candidate-filter="overlayCandidateFilter = $event"
      @update-overlay-search-query="overlaySearchQuery = $event"
      @update-overlay-form="updateOverlayForm"
      @prepare-goal-draft="prepareGoalDraftFromCurrentProject"
      @load-goal-draft-proposal="loadGoalDraftProposal"
      @dismiss-goal-draft-proposal="dismissGoalDraftProposal"
      @search-overlay-results="searchOverlayResults"
      @add-search-result-to-overlay="addSearchResultToOverlay"
      @create-auto-draft="createAutoOverlayDraft"
      @preview-overlay-extraction-payload="previewOverlayExtractionPayload"
      @toggle-preview-candidate="togglePreviewCandidate"
      @open-first-repairable="openFirstRepairableCandidate"
      @edit-node="openNodeCandidateEditor"
      @edit-edge="openEdgeCandidateEditor"
      @edit-resource="openResourceCandidateEditor"
      @update-resource-binding="updateResourceBindingField"
      @update-promotion-secret="promotionSecret = $event"
      @bind-resource="bindOverlayResource"
      @preview-promotion="previewPromotion"
      @commit-promotion="commitPromotion"
      @submit-overlay-draft="submitOverlayDraft"
      @update-candidate-editor-visible="candidateEditor.visible = $event"
      @quick-fix="applyCandidateQuickFix"
      @save-candidate-editor="saveCandidateEditor"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import { useDisplayMode } from '@/composables/useDisplayMode'
import { useProjectStore } from '@/stores/project'
import GraphLegendPanel from './GraphLegendPanel.vue'
import GraphStatePanel from './GraphStatePanel.vue'
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
const KnowledgeSidePanels = defineAsyncComponent(() => import('./KnowledgeSidePanels.vue'))

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
  overlayAutoDraftLoading,
  overlayBridgeMessage,
  overlaySearchQuery,
  overlaySearchResults,
  overlaySearchLoading,
  overlaySearchError,
  overlayAddingSearchUrl,
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
  searchOverlayResults,
  addSearchResultToOverlay,
  createAutoOverlayDraft,
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
const overlayDrawerProps = computed(() => ({
  visible: overlayDrawerVisible.value,
  displayMode: displayMode.value,
  overlaySubmitting: overlaySubmitting.value,
  overlayExtractionPreviewLoading: overlayExtractionPreviewLoading.value,
  overlayAutoDraftLoading: overlayAutoDraftLoading.value,
  activeGoalDraftResolutionSessionId: activeGoalDraftResolutionSessionId.value,
  manualGoalDraftLoading: manualGoalDraftLoading.value,
  goalDraftProposalLoading: goalDraftProposalLoading.value,
  goalDraftInboxProposal: goalDraftInboxProposal.value,
  goalDraftProposalDismissed: goalDraftProposalDismissed.value,
  goalDraftInboxMissingConcepts: goalDraftInboxMissingConcepts.value,
  goalDraftInboxCounts: goalDraftInboxCounts.value,
  goalDraftInboxNodes: goalDraftInboxNodes.value,
  goalDraftInboxEdges: goalDraftInboxEdges.value,
  goalDraftInboxResources: goalDraftInboxResources.value,
  overlayDraftMode: overlayDraftMode.value,
  overlayForm: overlayForm.value,
  manualOverlayMode: manualOverlayMode.value,
  overlaySearchQuery: overlaySearchQuery.value,
  overlaySearchResults: overlaySearchResults.value,
  overlaySearchLoading: overlaySearchLoading.value,
  overlaySearchError: overlaySearchError.value,
  overlayAddingSearchUrl: overlayAddingSearchUrl.value,
  persistedSearchResults: persistedSearchResults.value,
  overlayBridgeMessage: overlayBridgeMessage.value,
  overlayExtractionPreview: overlayExtractionPreview.value,
  normalizedPreviewPayload: normalizedPreviewPayload.value,
  selectedPreviewCounts: selectedPreviewCounts.value,
  overlayCandidateValidation: overlayCandidateValidation.value,
  isPreviewCandidateSelected,
  candidateTitle,
  edgeCandidateSummary,
  overlayError: overlayError.value,
  lastOverlaySession: lastOverlaySession.value,
  showTechnicalDetails: showTechnicalDetails.value,
  showAuditDetails: showAuditDetails.value,
  overlaySessionGuide: overlaySessionGuide.value,
  overlaySessionStats: overlaySessionStats.value,
  overlayWorkflowSteps: overlayWorkflowSteps.value,
  overlayWorkflowCurrentStep: overlayWorkflowCurrentStep.value,
  overlayCandidateFilter: overlayCandidateFilter.value,
  overlayCandidateFilterCounts: overlayCandidateFilterCounts.value,
  filteredOverlayCandidateCount: filteredOverlayCandidateCount.value,
  hasOverlayCandidateRepairTarget: Boolean(overlayCandidateRepairTarget.value),
  overlayCandidateRepairTargetLabel: overlayCandidateRepairTargetLabel.value,
  filteredOverlayNodes: filteredOverlayNodes.value,
  filteredOverlayEdges: filteredOverlayEdges.value,
  filteredOverlayResources: filteredOverlayResources.value,
  goalExtensionDraftDetails: goalExtensionDraftDetails.value,
  goalDraftMissingConcepts: goalDraftMissingConcepts.value,
  goalDraftReviewNotes: goalDraftReviewNotes.value,
  goalDraftReviewFocus: goalDraftReviewFocus.value,
  validationErrorMessage,
  resourceBinding: resourceBinding.value,
  resourceTargetOptions: resourceTargetOptions.value,
  promotionPreview: promotionPreview.value,
  promotionResult: promotionResult.value,
  promotionSecret: promotionSecret.value,
  promotionLoading: promotionLoading.value,
  promotionStatusMessage: promotionStatusMessage.value,
}))
const candidateEditorDialogProps = computed(() => ({
  visible: candidateEditor.value.visible,
  candidateEditor: candidateEditor.value,
  candidateEditorIssueSummary: candidateEditorIssueSummary.value,
  candidateEditorQuickFixErrors: candidateEditorQuickFixErrors.value,
  overlayEndpointOptions: overlayEndpointOptions.value,
  candidateEditorFieldIssue,
  quickFixLabel,
}))

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

@media (max-width: 768px) {
  .page-container {
    padding: 12px;
    height: auto;
  }

}
</style>
