<template>
  <section class="overlay-preview">
    <h4>AI 抽取预览</h4>
    <el-descriptions :column="1" border size="small">
      <el-descriptions-item label="节点候选">{{ selectedPreviewCounts.nodes }} / {{ preview.counts.nodes }}</el-descriptions-item>
      <el-descriptions-item label="关系候选">{{ selectedPreviewCounts.edges }} / {{ preview.counts.edges }}</el-descriptions-item>
      <el-descriptions-item label="资源候选">{{ selectedPreviewCounts.resources }} / {{ preview.counts.resources }}</el-descriptions-item>
      <el-descriptions-item label="来源数">{{ preview.source_ids.length }}</el-descriptions-item>
    </el-descriptions>
    <div class="candidate-card-list">
      <article v-for="(node, index) in normalizedPreviewPayload.nodes" :key="`preview-node-${index}`" class="preview-candidate-card">
        <label class="candidate-checkbox-row">
          <input
            type="checkbox"
            :checked="isPreviewCandidateSelected('nodes', index)"
            @change="onToggleCandidate('nodes', index, $event)"
          />
          <strong>{{ candidateTitle(node, `节点候选 ${index + 1}`) }}</strong>
        </label>
        <p>{{ node.summary || node.legality_rationale || '暂无摘要' }}</p>
        <el-tag v-if="node.confidence !== undefined" size="small" type="info">置信度 {{ node.confidence }}</el-tag>
      </article>
      <article v-for="(edge, index) in normalizedPreviewPayload.edges" :key="`preview-edge-${index}`" class="preview-candidate-card">
        <label class="candidate-checkbox-row">
          <input
            type="checkbox"
            :checked="isPreviewCandidateSelected('edges', index)"
            @change="onToggleCandidate('edges', index, $event)"
          />
          <strong>{{ edgeCandidateSummary(edge) }}</strong>
        </label>
        <p>{{ edge.legality_rationale || '暂无合法性说明' }}</p>
        <el-tag size="small" type="info">{{ edge.relation_type || 'RELATED_TO' }}</el-tag>
      </article>
      <article v-for="(resource, index) in normalizedPreviewPayload.resources" :key="`preview-resource-${index}`" class="preview-candidate-card">
        <label class="candidate-checkbox-row">
          <input
            type="checkbox"
            :checked="isPreviewCandidateSelected('resources', index)"
            @change="onToggleCandidate('resources', index, $event)"
          />
          <strong>{{ candidateTitle(resource, `资源候选 ${index + 1}`) }}</strong>
        </label>
        <p>{{ resource.summary || resource.url || '暂无摘要' }}</p>
        <el-tag v-if="resource.resource_type" size="small" type="success">{{ resource.resource_type }}</el-tag>
      </article>
    </div>
    <el-alert
      v-if="preview.warnings.length"
      class="overlay-alert"
      type="warning"
      :closable="false"
      show-icon
      :title="preview.warnings.join('；')"
    />
    <el-alert
      v-if="validation"
      class="overlay-alert"
      :type="validation.summary.has_blocking_errors ? 'warning' : 'success'"
      :closable="false"
      show-icon
      :title="validationSummaryTitle"
    />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type {
  OverlayExtractionPayloadPreviewResponse,
  OverlayExtractionPayloadValidationResponse,
} from '@/api/modules/graph'
import type { OverlayPreviewGroup } from './composables/useOverlayDraftInput'

type PreviewPayload = {
  nodes: Array<Record<string, any>>
  edges: Array<Record<string, any>>
  resources: Array<Record<string, any>>
}

type SelectedPreviewCounts = Record<OverlayPreviewGroup, number>

const props = defineProps<{
  preview: OverlayExtractionPayloadPreviewResponse
  normalizedPreviewPayload: PreviewPayload
  selectedPreviewCounts: SelectedPreviewCounts
  validation: OverlayExtractionPayloadValidationResponse | null
  isPreviewCandidateSelected: (group: OverlayPreviewGroup, index: number) => boolean
  candidateTitle: (candidate: Record<string, any>, fallback: string) => string
  edgeCandidateSummary: (candidate: Record<string, any>) => string
}>()

const emit = defineEmits<{
  'toggle-candidate': [group: OverlayPreviewGroup, index: number, checked: boolean]
}>()

const validationSummaryTitle = computed(() => {
  const validation = props.validation
  if (!validation) return ''
  const validCount = validation.counts.nodes.valid + validation.counts.edges.valid + validation.counts.resources.valid
  return `预校验：通过 ${validCount}，失败 ${validation.summary.invalid_count}，待复核 ${validation.summary.needs_review_count}`
})

function onToggleCandidate(group: OverlayPreviewGroup, index: number, event: Event) {
  emit('toggle-candidate', group, index, (event.target as HTMLInputElement).checked)
}
</script>

<style scoped>
.overlay-preview {
  padding: 12px;
  border: 1px solid #d9ecff;
  border-radius: 10px;
  background: #f4faff;
}

.overlay-preview h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: #303133;
}

.candidate-card-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
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

.candidate-checkbox-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.overlay-alert {
  margin-bottom: 4px;
}
</style>
