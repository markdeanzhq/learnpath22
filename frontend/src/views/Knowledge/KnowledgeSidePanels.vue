<template>
  <NodeDetail
    v-if="selectedNode"
    :node="selectedNode"
    @review-edge="(edgeId, status) => emit('review-edge', edgeId, status)"
    @set-overlay-planning="(data, enabled) => emit('set-overlay-planning', data, enabled)"
  />
  <EntityMetadataDrawer
    v-if="entityDrawerVisible || entityLoading || entityMetadata"
    :model-value="entityDrawerVisible"
    :loading="entityLoading"
    :metadata="entityMetadata"
    @update:model-value="emit('update:entityDrawerVisible', $event)"
  />

  <KnowledgeOverlayDrawer
    v-bind="overlayDrawerProps"
    @update:visible="emit('update-overlay-drawer-visible', $event)"
    @update:display-mode="emit('update-display-mode', $event)"
    @update:overlay-draft-mode="emit('update-overlay-draft-mode', $event)"
    @update:overlay-candidate-filter="emit('update-overlay-candidate-filter', $event)"
    @update:overlay-search-query="emit('update-overlay-search-query', $event)"
    @update-overlay-form="emit('update-overlay-form', $event)"
    @prepare-goal-draft="emit('prepare-goal-draft')"
    @load-goal-draft-proposal="emit('load-goal-draft-proposal')"
    @dismiss-goal-draft-proposal="emit('dismiss-goal-draft-proposal')"
    @search-overlay-results="emit('search-overlay-results')"
    @add-search-result-to-overlay="(result, index) => emit('add-search-result-to-overlay', result, index)"
    @create-auto-draft="emit('create-auto-draft')"
    @preview-overlay-extraction-payload="emit('preview-overlay-extraction-payload')"
    @toggle-preview-candidate="(group, index, checked) => emit('toggle-preview-candidate', group, index, checked)"
    @open-first-repairable="emit('open-first-repairable')"
    @confirm-valid-candidates="emit('confirm-valid-candidates')"
    @enable-confirmed-planning="emit('enable-confirmed-planning')"
    @edit-node="emit('edit-node', $event)"
    @edit-edge="emit('edit-edge', $event)"
    @edit-resource="emit('edit-resource', $event)"
    @update-resource-binding="(field, value) => emit('update-resource-binding', field, value)"
    @update:promotion-secret="emit('update-promotion-secret', $event)"
    @bind-resource="emit('bind-resource')"
    @preview-promotion="emit('preview-promotion')"
    @commit-promotion="emit('commit-promotion')"
    @submit-overlay-draft="emit('submit-overlay-draft')"
  />

  <OverlayCandidateEditorDialog
    v-bind="candidateEditorDialogProps"
    @update:visible="emit('update-candidate-editor-visible', $event)"
    @quick-fix="emit('quick-fix', $event)"
    @save="emit('save-candidate-editor')"
  />
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import type {
  GraphEdgeData,
  GraphEntityMetadata,
  GraphNodeData,
  OverlayEdgeCandidate,
  OverlayNodeCandidate,
  OverlayResourceCandidate,
  ReviewStatus,
} from '@/api/modules/graph'
import type { SearchResultItem } from '@/api/modules/search'
import type { DisplayMode } from '@/composables/useDisplayMode'
import type { SelectedNodeContext } from './composables/useSelectedNodeContext'
import type { CandidateIssueFilter } from './composables/useOverlayCandidateWorkflow'
import type { OverlayDraftMode, OverlayFormState, OverlayPreviewGroup } from './composables/useOverlayDraftInput'
import type { ResourceBindingForm } from './composables/useOverlayPostActions'
import type KnowledgeOverlayDrawerComponent from './KnowledgeOverlayDrawer.vue'
import type OverlayCandidateEditorDialogComponent from './OverlayCandidateEditorDialog.vue'

const NodeDetail = defineAsyncComponent(() => import('@/components/Graph/NodeDetail.vue'))
const EntityMetadataDrawer = defineAsyncComponent(() => import('@/components/Graph/EntityMetadataDrawer.vue'))
const KnowledgeOverlayDrawer = defineAsyncComponent(() => import('./KnowledgeOverlayDrawer.vue'))
const OverlayCandidateEditorDialog = defineAsyncComponent(() => import('./OverlayCandidateEditorDialog.vue'))

type KnowledgeOverlayDrawerProps = InstanceType<typeof KnowledgeOverlayDrawerComponent>['$props']
type OverlayCandidateEditorDialogProps = InstanceType<typeof OverlayCandidateEditorDialogComponent>['$props']

defineProps<{
  selectedNode: SelectedNodeContext | null
  entityDrawerVisible: boolean
  entityLoading: boolean
  entityMetadata: GraphEntityMetadata | null
  overlayDrawerProps: KnowledgeOverlayDrawerProps
  candidateEditorDialogProps: OverlayCandidateEditorDialogProps
}>()

const emit = defineEmits<{
  'review-edge': [edgeId: string, status: ReviewStatus]
  'set-overlay-planning': [data: GraphNodeData | GraphEdgeData, enabled: boolean]
  'update:entityDrawerVisible': [visible: boolean]
  'update-overlay-drawer-visible': [visible: boolean]
  'update-display-mode': [mode: DisplayMode]
  'update-overlay-draft-mode': [mode: OverlayDraftMode]
  'update-overlay-candidate-filter': [filter: CandidateIssueFilter]
  'update-overlay-search-query': [query: string]
  'update-overlay-form': [form: OverlayFormState]
  'prepare-goal-draft': []
  'load-goal-draft-proposal': []
  'dismiss-goal-draft-proposal': []
  'search-overlay-results': []
  'add-search-result-to-overlay': [result: SearchResultItem, index: number]
  'create-auto-draft': []
  'preview-overlay-extraction-payload': []
  'toggle-preview-candidate': [group: OverlayPreviewGroup, index: number, checked: boolean]
  'open-first-repairable': []
  'confirm-valid-candidates': []
  'enable-confirmed-planning': []
  'edit-node': [node: OverlayNodeCandidate]
  'edit-edge': [edge: OverlayEdgeCandidate]
  'edit-resource': [resource: OverlayResourceCandidate]
  'update-resource-binding': [field: keyof ResourceBindingForm, value: string]
  'update-promotion-secret': [secret: string]
  'bind-resource': []
  'preview-promotion': []
  'commit-promotion': []
  'submit-overlay-draft': []
  'update-candidate-editor-visible': [visible: boolean]
  'quick-fix': [error: string]
  'save-candidate-editor': []
}>()
</script>
