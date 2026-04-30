<template>
  <section class="overlay-result">
    <OverlaySessionSummary
      :session="session"
      :show-technical-details="showTechnicalDetails"
      :overlay-session-guide="overlaySessionGuide"
      :overlay-session-stats="overlaySessionStats"
    />

    <OverlayWorkflowSteps
      :steps="overlayWorkflowSteps"
      :current-step="overlayWorkflowCurrentStep"
    />

    <OverlayCandidateReviewList
      v-model:filter="candidateFilterModel"
      :diagnostics="overlayCandidateDiagnostics"
      :diagnostic-summary="overlayCandidateDiagnosticSummary"
      :filter-options="overlayCandidateFilterOptions"
      :filter-counts="overlayCandidateFilterCounts"
      :filtered-candidate-count="filteredOverlayCandidateCount"
      :batch-review-loading="overlayBatchReviewLoading"
      :batch-confirmable-count="overlayBatchConfirmableCount"
      :has-repair-target="hasOverlayCandidateRepairTarget"
      :repair-target-label="overlayCandidateRepairTargetLabel"
      :nodes="filteredOverlayNodes"
      :edges="filteredOverlayEdges"
      :resources="filteredOverlayResources"
      :validation-error-message="validationErrorMessage"
      @open-first-repairable="emit('open-first-repairable')"
      @confirm-valid-candidates="emit('confirm-valid-candidates')"
      @edit-node="emit('edit-node', $event)"
      @edit-edge="emit('edit-edge', $event)"
      @edit-resource="emit('edit-resource', $event)"
    />

    <OverlayGoalDraftSummary
      v-if="goalExtensionDraftDetails"
      :details="goalExtensionDraftDetails"
      :missing-concepts="goalDraftMissingConcepts"
      :review-notes="goalDraftReviewNotes"
      :review-focus="goalDraftReviewFocus"
      :show-audit-details="showAuditDetails"
    />

    <OverlayResourceBindingPanel
      v-if="showAuditDetails && session.resources?.length"
      :resources="session.resources || []"
      :resource-binding="resourceBinding"
      :resource-target-options="resourceTargetOptions"
      @update-resource-binding="(field, value) => emit('update-resource-binding', field, value)"
      @bind-resource="emit('bind-resource')"
    />

    <OverlayPromotionPanel
      v-if="showTechnicalDetails"
      :promotion-preview="promotionPreview"
      :promotion-result="promotionResult"
      :promotion-secret="promotionSecret"
      :promotion-loading="promotionLoading"
      :promotion-status-message="promotionStatusMessage"
      @update:promotion-secret="emit('update:promotionSecret', $event)"
      @preview-promotion="emit('preview-promotion')"
      @commit-promotion="emit('commit-promotion')"
    />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type {
  GoalExtensionDraftResponse,
  OverlayEdgeCandidate,
  OverlayNodeCandidate,
  OverlayPromotionResponse,
  OverlayResourceCandidate,
} from '@/api/modules/graph'
import OverlayCandidateReviewList from './OverlayCandidateReviewList.vue'
import OverlayGoalDraftSummary from './OverlayGoalDraftSummary.vue'
import OverlayPromotionPanel from './OverlayPromotionPanel.vue'
import OverlayResourceBindingPanel from './OverlayResourceBindingPanel.vue'
import OverlaySessionSummary from './OverlaySessionSummary.vue'
import OverlayWorkflowSteps from './OverlayWorkflowSteps.vue'
import type {
  CandidateIssueFilter,
  OverlaySessionView,
  OverlayWorkflowStep,
} from './composables/useOverlayCandidateWorkflow'
import type { ResourceBindingForm } from './composables/useOverlayPostActions'
import type {
  OverlayCandidateDiagnosticItem,
  OverlayCandidateDiagnosticSummary,
  OverlayCandidateFilterCounts,
  OverlayCandidateFilterOption,
  OverlaySessionStats,
  ResourceTargetOption,
} from './overlaySessionPanelTypes'

const props = defineProps<{
  session: OverlaySessionView
  showTechnicalDetails: boolean
  showAuditDetails: boolean
  overlaySessionGuide: string
  overlaySessionStats: OverlaySessionStats
  overlayCandidateDiagnostics: OverlayCandidateDiagnosticItem[]
  overlayCandidateDiagnosticSummary: OverlayCandidateDiagnosticSummary
  overlayWorkflowSteps: OverlayWorkflowStep[]
  overlayWorkflowCurrentStep: OverlayWorkflowStep | null
  overlayCandidateFilter: CandidateIssueFilter
  overlayCandidateFilterOptions: OverlayCandidateFilterOption[]
  overlayCandidateFilterCounts: OverlayCandidateFilterCounts
  filteredOverlayCandidateCount: number
  overlayBatchReviewLoading: boolean
  overlayBatchConfirmableCount: number
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
  'update:overlayCandidateFilter': [filter: CandidateIssueFilter]
  'open-first-repairable': []
  'confirm-valid-candidates': []
  'edit-node': [node: OverlayNodeCandidate]
  'edit-edge': [edge: OverlayEdgeCandidate]
  'edit-resource': [resource: OverlayResourceCandidate]
  'update-resource-binding': [field: keyof ResourceBindingForm, value: string]
  'update:promotionSecret': [secret: string]
  'bind-resource': []
  'preview-promotion': []
  'commit-promotion': []
}>()

const candidateFilterModel = computed({
  get: () => props.overlayCandidateFilter,
  set: (filter) => emit('update:overlayCandidateFilter', filter),
})
</script>

<style scoped>
.overlay-result {
  padding: 14px;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  background: #fafafa;
}
</style>
