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
        <section class="graph-status-panel">
          <div>
            <strong>{{ graphScopeLabel }}</strong>
            <p>{{ graphStatusHint }}</p>
          </div>
          <div class="graph-status-meta">
            <div class="graph-status-tags">
              <el-tag size="small" type="info" effect="plain">节点 {{ graphNodeCount }}</el-tag>
              <el-tag size="small" type="info" effect="plain">关系 {{ graphEdgeCount }}</el-tag>
              <el-tag size="small" type="success" effect="plain">本地读模型</el-tag>
              <el-tag v-if="overlayPreflight" size="small" :type="overlayPreflightTagType" effect="plain">
                增强候选 {{ overlayPreflight.counts.visible_overlay_nodes }} / {{ overlayPreflight.counts.visible_overlay_edges }}
              </el-tag>
            </div>
            <div v-if="showGraphCacheDiagnostics" class="graph-cache-diagnostics" data-testid="graph-cache-diagnostics">
              <span class="graph-cache-title">缓存诊断</span>
              <el-tag
                v-for="item in graphCacheDiagnosticItems"
                :key="item.key"
                size="small"
                type="info"
                effect="plain"
              >
                {{ item.label }} {{ item.hitRateLabel }} · {{ item.sizeLabel }}
              </el-tag>
              <el-tag v-if="graphCacheStatsLoading" size="small" type="warning" effect="plain">刷新中</el-tag>
              <el-tag v-if="graphCacheStatsError" size="small" type="danger" effect="plain">{{ graphCacheStatsError }}</el-tag>
            </div>
          </div>
        </section>
        <el-alert
          v-if="projectionStatus && projectionStatus.status !== 'empty'"
          class="graph-alert"
          :type="projectionAlertType"
          :closable="false"
          show-icon
          :title="projectionStatusTitle"
        />
        <section v-if="overlayPreflight" class="overlay-preflight-panel graph-alert">
          <div class="overlay-preflight-header">
            <strong>增强图谱使用状态</strong>
            <el-tag :type="overlayPreflightTagType">{{ overlayPreflightStatusLabel }}</el-tag>
          </div>
          <p>{{ overlayPreflight.summary }}</p>
          <p class="overlay-guidance">{{ overlayPreflightGuidance }}</p>
          <div class="overlay-preflight-tags">
            <el-tag type="info" effect="plain">候选 {{ overlayPreflight.counts.active_nodes }} 节点 / {{ overlayPreflight.counts.active_edges }} 关系</el-tag>
            <el-tag type="success" effect="plain">可进入增强图谱 {{ overlayPreflight.counts.visible_overlay_nodes }} 节点 / {{ overlayPreflight.counts.visible_overlay_edges }} 关系</el-tag>
            <el-tag type="warning" effect="plain">待审核 {{ overlayPreflight.counts.nodes.pending_review + overlayPreflight.counts.edges.pending_review }}</el-tag>
            <el-tag type="danger" effect="plain">校验失败 {{ overlayPreflight.counts.nodes.invalid + overlayPreflight.counts.edges.invalid }}</el-tag>
            <el-tag type="warning" effect="plain">当前路径命中 {{ overlayPreflight.counts.path_overlay_nodes }} 节点 / {{ overlayPreflight.counts.path_overlay_edges }} 关系</el-tag>
            <el-tag v-if="overlayPreflight.counts.ignored_overlay_edges" type="warning" effect="plain">忽略关系 {{ overlayPreflight.counts.ignored_overlay_edges }}</el-tag>
          </div>
          <div v-if="overlayPreflightIssues.length" class="overlay-preflight-issues">
            <span v-for="(item, index) in overlayPreflightIssues" :key="`${item.kind}-${index}`">{{ item.message }}</span>
          </div>
        </section>
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

    <el-drawer v-model="overlayDrawerVisible" title="创建扩展草稿" :size="520" direction="rtl">
      <div class="overlay-drawer" v-loading="overlaySubmitting || overlayExtractionPreviewLoading">
        <DisplayModeSwitch v-model="displayMode" />
        <el-alert
          class="overlay-alert"
          type="info"
          :closable="false"
          show-icon
          title="扩展草稿会先进入项目扩展区，确认审核与规划开关后才会参与路径规划。"
        />
        <el-alert
          v-if="activeGoalDraftResolutionSessionId"
          class="overlay-alert"
          type="warning"
          :closable="false"
          show-icon
          title="来自目标理解的领域内未覆盖概念。页面打开只展示草稿收件箱；点击创建后才会生成 overlay 草稿。"
        />
        <section v-else class="overlay-subsection goal-draft-entry manual-goal-draft-entry">
          <h4>智能草稿建议</h4>
          <p>手动触发当前项目目标的覆盖分析；只有识别为领域内未覆盖概念时，才会生成待审核 overlay 草稿收件箱。</p>
          <el-button size="small" type="primary" plain :loading="manualGoalDraftLoading" @click="prepareGoalDraftFromCurrentProject">
            分析当前目标并生成推荐草稿
          </el-button>
        </section>

        <section v-if="activeGoalDraftResolutionSessionId" class="overlay-subsection goal-draft-entry" v-loading="goalDraftProposalLoading">
          <h4>系统推荐草稿收件箱</h4>
          <p>系统已根据目标理解准备推荐草稿图谱；您也可以忽略推荐，继续使用粘贴文本、搜索 URL 或已保存搜索结果手动补充。</p>
          <el-radio-group v-model="overlayDraftMode" class="draft-mode-switch">
            <el-radio-button value="goal_draft">使用系统推荐草稿</el-radio-button>
            <el-radio-button value="manual">手动补充资料</el-radio-button>
          </el-radio-group>
          <div v-if="goalDraftInboxProposal && !goalDraftProposalDismissed" class="draft-inbox-card">
            <div class="review-focus-list">
              <el-tag v-for="concept in goalDraftInboxMissingConcepts" :key="concept" type="warning" effect="plain">{{ concept }}</el-tag>
            </div>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="推荐节点">{{ goalDraftInboxCounts.nodes }}</el-descriptions-item>
              <el-descriptions-item label="推荐关系">{{ goalDraftInboxCounts.edges }}</el-descriptions-item>
              <el-descriptions-item label="推荐资源">{{ goalDraftInboxCounts.resources }}</el-descriptions-item>
              <el-descriptions-item label="安全边界">不写正式图谱，不写正式路径，需人工审核</el-descriptions-item>
            </el-descriptions>
            <div v-if="goalDraftInboxNodes.length || goalDraftInboxEdges.length || goalDraftInboxResources.length" class="candidate-card-list compact">
              <article v-for="(node, index) in goalDraftInboxNodes.slice(0, 3)" :key="`draft-node-${index}`" class="preview-candidate-card">
                <strong>{{ candidateTitle(node, `节点候选 ${index + 1}`) }}</strong>
                <p>{{ node.summary || node.legality_rationale || '待审核节点候选' }}</p>
              </article>
              <article v-for="(edge, index) in goalDraftInboxEdges.slice(0, 3)" :key="`draft-edge-${index}`" class="preview-candidate-card">
                <strong>{{ edgeCandidateSummary(edge) }}</strong>
                <p>{{ edge.legality_rationale || '待审核关系候选' }}</p>
              </article>
              <article v-for="(resource, index) in goalDraftInboxResources.slice(0, 2)" :key="`draft-resource-${index}`" class="preview-candidate-card">
                <strong>{{ candidateTitle(resource, `资源候选 ${index + 1}`) }}</strong>
                <p>{{ resource.summary || '待审核资源候选' }}</p>
              </article>
            </div>
          </div>
          <el-alert
            v-else-if="goalDraftProposalDismissed"
            class="overlay-alert"
            type="info"
            :closable="false"
            show-icon
            title="已忽略系统推荐草稿，可在下方继续手动补充资料。"
          />
          <div class="draft-inbox-actions">
            <el-button size="small" plain :loading="goalDraftProposalLoading" @click="loadGoalDraftProposal">刷新推荐草稿</el-button>
            <el-button size="small" plain @click="dismissGoalDraftProposal">忽略推荐，手动补充</el-button>
          </div>
        </section>

        <el-form v-if="manualOverlayMode" label-position="top">
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

          <el-form-item label="AI 抽取预览">
            <el-button plain :loading="overlayExtractionPreviewLoading" @click="previewOverlayExtractionPayload">
              生成候选预览
            </el-button>
            <span class="preview-hint">先预览 LLM payload，再勾选候选并复用现有校验创建草稿。</span>
          </el-form-item>
        </el-form>

        <OverlayExtractionPreviewPanel
          v-if="overlayExtractionPreview"
          :preview="overlayExtractionPreview"
          :normalized-preview-payload="normalizedPreviewPayload"
          :selected-preview-counts="selectedPreviewCounts"
          :validation="overlayCandidateValidation"
          :is-preview-candidate-selected="isPreviewCandidateSelected"
          :candidate-title="candidateTitle"
          :edge-candidate-summary="edgeCandidateSummary"
          @toggle-candidate="togglePreviewCandidate"
        />

        <el-alert
          v-if="overlayError"
          class="overlay-alert"
          type="warning"
          :closable="false"
          show-icon
          :title="overlayError"
        />

        <OverlaySessionResultPanel
          v-if="lastOverlaySession"
          v-model:overlay-candidate-filter="overlayCandidateFilter"
          :session="lastOverlaySession"
          :show-technical-details="showTechnicalDetails"
          :show-audit-details="showAuditDetails"
          :overlay-session-guide="overlaySessionGuide"
          :overlay-session-stats="overlaySessionStats"
          :overlay-workflow-steps="overlayWorkflowSteps"
          :overlay-workflow-current-step="overlayWorkflowCurrentStep"
          :overlay-candidate-filter-options="OVERLAY_CANDIDATE_FILTER_OPTIONS"
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
          @open-first-repairable="openFirstRepairableCandidate"
          @edit-node="openNodeCandidateEditor"
          @edit-edge="openEdgeCandidateEditor"
          @edit-resource="openResourceCandidateEditor"
          @update-resource-binding="updateResourceBindingField"
          @update:promotion-secret="promotionSecret = $event"
          @bind-resource="bindOverlayResource"
          @preview-promotion="previewPromotion"
          @commit-promotion="commitPromotion"
        />

        <div class="drawer-actions">
          <el-button @click="overlayDrawerVisible = false">关闭</el-button>
          <el-button type="primary" :loading="overlaySubmitting" @click="submitOverlayDraft">
            {{ activeGoalDraftResolutionSessionId && overlayDraftMode === 'goal_draft' ? '创建推荐草稿' : '创建手动草稿' }}
          </el-button>
        </div>
      </div>
    </el-drawer>

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
import DisplayModeSwitch from '@/components/DisplayModeSwitch.vue'
import { useDisplayMode } from '@/composables/useDisplayMode'
import { useProjectStore } from '@/stores/project'
import OverlayCandidateEditorDialog from './OverlayCandidateEditorDialog.vue'
import OverlayExtractionPreviewPanel from './OverlayExtractionPreviewPanel.vue'
import OverlaySessionResultPanel from './OverlaySessionResultPanel.vue'
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
  OVERLAY_CANDIDATE_FILTER_OPTIONS,
  useOverlayCandidateWorkflow,
  type CandidateIssueFilter,
  type OverlaySessionView,
} from './composables/useOverlayCandidateWorkflow'
import { useOverlayDraftInput } from './composables/useOverlayDraftInput'
import {
  graphApi,
  type GraphElement,
} from '@/api/modules/graph'
import { GRAPH_CATEGORY_LEGEND, GRAPH_RELATION_LEGEND } from '@/components/Graph/graphMeta'

const GraphToolbar = defineAsyncComponent(() => import('@/components/Graph/GraphToolbar.vue'))
const GraphCanvas = defineAsyncComponent(() => import('@/components/Graph/GraphCanvas.vue'))
const NodeDetail = defineAsyncComponent(() => import('@/components/Graph/NodeDetail.vue'))
const EntityMetadataDrawer = defineAsyncComponent(() => import('@/components/Graph/EntityMetadataDrawer.vue'))

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

.graph-status-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 12px 12px 0;
  padding: 12px;
  border: 1px solid #e1f3d8;
  border-radius: 12px;
  background: linear-gradient(135deg, #f0f9eb 0%, #f5f7fa 100%);
}

.graph-status-panel strong {
  display: block;
  margin-bottom: 4px;
  color: #303133;
  font-size: 14px;
}

.graph-status-panel p {
  margin: 0;
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
}

.graph-status-meta,
.graph-status-tags,
.graph-cache-diagnostics {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.graph-status-meta {
  flex-direction: column;
  align-items: flex-end;
}

.graph-cache-diagnostics {
  align-items: center;
  color: #909399;
  font-size: 12px;
}

.graph-cache-title {
  font-weight: 600;
}

.graph-alert {
  margin: 12px 12px 0;
}

.overlay-preflight-panel {
  padding: 12px;
  border: 1px solid #dcdfe6;
  border-radius: 10px;
  background: #fff;
}

.overlay-preflight-header,
.overlay-preflight-tags,
.overlay-preflight-issues {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.overlay-preflight-header {
  justify-content: space-between;
}

.overlay-preflight-panel p {
  margin: 8px 0;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
}

.overlay-preflight-issues {
  margin-top: 8px;
  color: #e6a23c;
  font-size: 12px;
}

.overlay-drawer {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.overlay-alert {
  margin-bottom: 4px;
}

.goal-draft-entry {
  padding: 12px;
  border: 1px solid #f3d19e;
  border-radius: 10px;
  background: #fdf6ec;
}

.goal-draft-entry p {
  margin: 0;
  color: #606266;
  font-size: 13px;
  line-height: 1.7;
}

.draft-mode-switch,
.draft-inbox-actions {
  margin-top: 10px;
}

.draft-inbox-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.draft-inbox-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 10px;
}

.candidate-card-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}

.candidate-card-list.compact {
  gap: 8px;
}

.preview-candidate-card {
  padding: 10px;
  border: 1px solid #d9ecff;
  border-radius: 8px;
  background: #fff;
}

.preview-candidate-card p {
  margin: 6px 0;
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
}

.overlay-guidance {
  margin: 4px 0 0;
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
}

.preview-hint {
  margin-left: 10px;
  color: #909399;
  font-size: 12px;
}

.overlay-subsection {
  margin-top: 14px;
}

.overlay-subsection h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: #303133;
}

.review-focus-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
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

  .graph-legend-wrap,
  .graph-status-panel {
    flex-direction: column;
    align-items: flex-start;
  }

  .graph-status-tags {
    justify-content: flex-start;
  }
}
</style>
