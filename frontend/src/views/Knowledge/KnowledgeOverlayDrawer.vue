<template>
  <el-drawer v-model="visibleModel" title="创建扩展草稿" :size="520" direction="rtl">
    <div class="overlay-drawer" v-loading="overlaySubmitting || overlayExtractionPreviewLoading">
      <DisplayModeSwitch v-model="displayModeModel" />
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
        <el-button size="small" type="primary" plain :loading="manualGoalDraftLoading" @click="emit('prepare-goal-draft')">
          分析当前目标并生成推荐草稿
        </el-button>
      </section>

      <section v-if="activeGoalDraftResolutionSessionId" class="overlay-subsection goal-draft-entry" v-loading="goalDraftProposalLoading">
        <h4>系统推荐草稿收件箱</h4>
        <p>系统已根据目标理解准备推荐草稿图谱；您也可以忽略推荐，继续使用粘贴文本、搜索 URL 或已保存搜索结果手动补充。</p>
        <el-radio-group v-model="overlayDraftModeModel" class="draft-mode-switch">
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
          <el-button size="small" plain :loading="goalDraftProposalLoading" @click="emit('load-goal-draft-proposal')">刷新推荐草稿</el-button>
          <el-button size="small" plain @click="emit('dismiss-goal-draft-proposal')">忽略推荐，手动补充</el-button>
        </div>
      </section>

      <el-form v-if="manualOverlayMode" label-position="top">
        <el-form-item label="来源类型">
          <el-radio-group :model-value="overlayForm.sourceType" @update:model-value="updateSourceType">
            <el-radio-button value="pasted_text">粘贴文本</el-radio-button>
            <el-radio-button value="search_url">搜索 URL</el-radio-button>
            <el-radio-button value="saved_search">已保存搜索</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <template v-if="overlayForm.sourceType === 'pasted_text'">
          <el-form-item label="资料文本">
            <el-input
              :model-value="overlayForm.rawText"
              type="textarea"
              :rows="8"
              maxlength="12000"
              show-word-limit
              placeholder="粘贴希望抽取为项目图谱扩展的资料内容"
              @update:model-value="updateTextField('rawText', $event)"
            />
          </el-form-item>
          <el-form-item label="摘要（可选）">
            <el-input :model-value="overlayForm.summary" placeholder="用于回看来源的简短摘要" @update:model-value="updateTextField('summary', $event)" />
          </el-form-item>
        </template>

        <template v-else-if="overlayForm.sourceType === 'search_url'">
          <el-form-item label="URL">
            <el-input :model-value="overlayForm.url" placeholder="https://example.com/article" @update:model-value="updateTextField('url', $event)" />
          </el-form-item>
          <el-form-item label="标题">
            <el-input :model-value="overlayForm.title" placeholder="搜索结果标题" @update:model-value="updateTextField('title', $event)" />
          </el-form-item>
          <el-form-item label="摘要片段">
            <el-input :model-value="overlayForm.snippet" type="textarea" :rows="4" @update:model-value="updateTextField('snippet', $event)" />
          </el-form-item>
        </template>

        <template v-else>
          <el-form-item label="已保存搜索结果">
            <el-select
              :model-value="overlayForm.selectedResultIds"
              multiple
              filterable
              placeholder="选择已保存搜索结果"
              style="width: 100%"
              @update:model-value="updateSelectedResultIds"
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
          <el-radio-group :model-value="overlayForm.mode" @update:model-value="updateExtractionMode">
            <el-radio-button value="default">默认抽取</el-radio-button>
            <el-radio-button value="custom_extension">自定义扩展</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="AI 抽取预览">
          <el-button plain :loading="overlayExtractionPreviewLoading" @click="emit('preview-overlay-extraction-payload')">
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
        @toggle-candidate="(...args) => emit('toggle-preview-candidate', ...args)"
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
        v-model:overlay-candidate-filter="candidateFilterModel"
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
        :has-overlay-candidate-repair-target="hasOverlayCandidateRepairTarget"
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
        @open-first-repairable="emit('open-first-repairable')"
        @edit-node="emit('edit-node', $event)"
        @edit-edge="emit('edit-edge', $event)"
        @edit-resource="emit('edit-resource', $event)"
        @update-resource-binding="(field, value) => emit('update-resource-binding', field, value)"
        @update:promotion-secret="emit('update:promotionSecret', $event)"
        @bind-resource="emit('bind-resource')"
        @preview-promotion="emit('preview-promotion')"
        @commit-promotion="emit('commit-promotion')"
      />

      <div class="drawer-actions">
        <el-button @click="visibleModel = false">关闭</el-button>
        <el-button type="primary" :loading="overlaySubmitting" @click="emit('submit-overlay-draft')">
          {{ activeGoalDraftResolutionSessionId && overlayDraftMode === 'goal_draft' ? '创建推荐草稿' : '创建手动草稿' }}
        </el-button>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import DisplayModeSwitch from '@/components/DisplayModeSwitch.vue'
import type { DisplayMode } from '@/composables/useDisplayMode'
import type {
  GoalExtensionDraftProposal,
  GoalExtensionDraftResponse,
  OverlayEdgeCandidate,
  OverlayExtractionPayloadPreviewResponse,
  OverlayExtractionPayloadValidationResponse,
  OverlayNodeCandidate,
  OverlayPromotionResponse,
  OverlayResourceCandidate,
} from '@/api/modules/graph'
import type { PersistedSearchResult } from '@/api/modules/search'
import OverlayExtractionPreviewPanel from './OverlayExtractionPreviewPanel.vue'
import OverlaySessionResultPanel from './OverlaySessionResultPanel.vue'
import type {
  OverlayCandidateFilterCounts,
  OverlaySessionStats,
  ResourceTargetOption,
} from './overlaySessionPanelTypes'
import {
  OVERLAY_CANDIDATE_FILTER_OPTIONS,
  type CandidateIssueFilter,
  type OverlaySessionView,
  type OverlayWorkflowStep,
} from './composables/useOverlayCandidateWorkflow'
import type {
  OverlayDraftMode,
  OverlayFormState,
  OverlayPreviewGroup,
  PreviewPayload,
} from './composables/useOverlayDraftInput'
import type { ResourceBindingForm } from './composables/useOverlayPostActions'

type GoalDraftInboxCounts = {
  nodes: number
  edges: number
  resources: number
}

type SelectedPreviewCounts = {
  nodes: number
  edges: number
  resources: number
}

const props = defineProps<{
  visible: boolean
  displayMode: DisplayMode
  overlaySubmitting: boolean
  overlayExtractionPreviewLoading: boolean
  activeGoalDraftResolutionSessionId: string | null
  manualGoalDraftLoading: boolean
  goalDraftProposalLoading: boolean
  goalDraftInboxProposal: GoalExtensionDraftProposal | null
  goalDraftProposalDismissed: boolean
  goalDraftInboxMissingConcepts: string[]
  goalDraftInboxCounts: GoalDraftInboxCounts
  goalDraftInboxNodes: Array<Record<string, any>>
  goalDraftInboxEdges: Array<Record<string, any>>
  goalDraftInboxResources: Array<Record<string, any>>
  overlayDraftMode: OverlayDraftMode
  overlayForm: OverlayFormState
  manualOverlayMode: boolean
  persistedSearchResults: PersistedSearchResult[]
  overlayBridgeMessage: string
  overlayExtractionPreview: OverlayExtractionPayloadPreviewResponse | null
  normalizedPreviewPayload: PreviewPayload
  selectedPreviewCounts: SelectedPreviewCounts
  overlayCandidateValidation: OverlayExtractionPayloadValidationResponse | null
  isPreviewCandidateSelected: (group: OverlayPreviewGroup, index: number) => boolean
  candidateTitle: (candidate: Record<string, any>, fallback: string) => string
  edgeCandidateSummary: (candidate: Record<string, any>) => string
  overlayError: string
  lastOverlaySession: OverlaySessionView | null
  showTechnicalDetails: boolean
  showAuditDetails: boolean
  overlaySessionGuide: string
  overlaySessionStats: OverlaySessionStats
  overlayWorkflowSteps: OverlayWorkflowStep[]
  overlayWorkflowCurrentStep: OverlayWorkflowStep | null
  overlayCandidateFilter: CandidateIssueFilter
  overlayCandidateFilterCounts: OverlayCandidateFilterCounts
  filteredOverlayCandidateCount: number
  hasOverlayCandidateRepairTarget: boolean
  overlayCandidateRepairTargetLabel: string
  filteredOverlayNodes: OverlayNodeCandidate[]
  filteredOverlayEdges: OverlayEdgeCandidate[]
  filteredOverlayResources: OverlayResourceCandidate[]
  goalExtensionDraftDetails: GoalExtensionDraftResponse | null
  goalDraftMissingConcepts: string[]
  goalDraftReviewNotes: string[]
  goalDraftReviewFocus: string[]
  validationErrorMessage: (error: string) => string
  resourceBinding: ResourceBindingForm
  resourceTargetOptions: ResourceTargetOption[]
  promotionPreview: OverlayPromotionResponse | null
  promotionResult: OverlayPromotionResponse | null
  promotionSecret: string
  promotionLoading: boolean
  promotionStatusMessage: string
}>()

const emit = defineEmits<{
  'update:visible': [visible: boolean]
  'update:displayMode': [mode: DisplayMode]
  'update:overlayDraftMode': [mode: OverlayDraftMode]
  'update:overlayCandidateFilter': [filter: CandidateIssueFilter]
  'update-overlay-form': [form: OverlayFormState]
  'prepare-goal-draft': []
  'load-goal-draft-proposal': []
  'dismiss-goal-draft-proposal': []
  'preview-overlay-extraction-payload': []
  'toggle-preview-candidate': [group: OverlayPreviewGroup, index: number, checked: boolean]
  'open-first-repairable': []
  'edit-node': [node: OverlayNodeCandidate]
  'edit-edge': [edge: OverlayEdgeCandidate]
  'edit-resource': [resource: OverlayResourceCandidate]
  'update-resource-binding': [field: keyof ResourceBindingForm, value: string]
  'update:promotionSecret': [secret: string]
  'bind-resource': []
  'preview-promotion': []
  'commit-promotion': []
  'submit-overlay-draft': []
}>()

const visibleModel = computed({
  get: () => props.visible,
  set: (visible) => emit('update:visible', visible),
})

const displayModeModel = computed({
  get: () => props.displayMode,
  set: (mode) => emit('update:displayMode', mode),
})

const overlayDraftModeModel = computed({
  get: () => props.overlayDraftMode,
  set: (mode) => emit('update:overlayDraftMode', mode),
})

const candidateFilterModel = computed({
  get: () => props.overlayCandidateFilter,
  set: (filter) => emit('update:overlayCandidateFilter', filter),
})

function updateOverlayFormField<K extends keyof OverlayFormState>(field: K, value: OverlayFormState[K]) {
  emit('update-overlay-form', { ...props.overlayForm, [field]: value })
}

function updateTextField(field: 'rawText' | 'summary' | 'url' | 'title' | 'snippet', value: unknown) {
  updateOverlayFormField(field, typeof value === 'string' ? value : String(value ?? ''))
}

function updateSourceType(value: unknown) {
  const sourceType = value === 'search_url' || value === 'saved_search' ? value : 'pasted_text'
  updateOverlayFormField('sourceType', sourceType)
}

function updateExtractionMode(value: unknown) {
  updateOverlayFormField('mode', value === 'custom_extension' ? 'custom_extension' : 'default')
}

function updateSelectedResultIds(value: unknown) {
  updateOverlayFormField('selectedResultIds', Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [])
}
</script>

<style scoped>
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
  flex-wrap: wrap;
  gap: 8px;
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
  color: #303133;
  font-size: 14px;
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
</style>
