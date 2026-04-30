<template>
  <div v-if="filterCounts.all" class="overlay-diagnostic-summary">
    <div class="overlay-diagnostic-main">
      <el-tag size="small" :type="diagnosticSummary.tagType">{{ diagnosticSummary.statusLabel }}</el-tag>
      <div>
        <strong>{{ diagnosticSummary.title }}</strong>
        <p>{{ diagnosticSummary.description }}</p>
      </div>
    </div>
    <el-button
      v-if="diagnosticSummary.canOpenRepairTarget"
      size="small"
      type="primary"
      @click="emit('open-first-repairable')"
    >
      {{ diagnosticSummary.primaryActionLabel }}
    </el-button>
    <el-button
      v-else
      size="small"
      plain
      @click="candidateFilterModel = diagnosticSummary.primaryFilter"
    >
      {{ diagnosticSummary.primaryActionLabel }}
    </el-button>
  </div>

  <div v-if="diagnostics.length" class="overlay-diagnostic-list">
    <article v-for="diagnostic in diagnostics" :key="diagnostic.key" class="overlay-diagnostic-item">
      <div class="overlay-diagnostic-item-header">
        <el-tag size="small" :type="diagnostic.tagType">{{ diagnostic.statusLabel }} {{ diagnostic.count }}</el-tag>
        <el-button size="small" text type="primary" @click="candidateFilterModel = diagnostic.filter">
          {{ diagnostic.actionLabel }}
        </el-button>
      </div>
      <strong>{{ diagnostic.title }}</strong>
      <p>{{ diagnostic.description }}</p>
      <p v-if="diagnostic.firstTargetTitle" class="overlay-diagnostic-target">
        首个目标：{{ diagnostic.firstTargetTitle }}<span v-if="diagnostic.firstError"> · {{ validationErrorMessage(diagnostic.firstError) }}</span>
      </p>
    </article>
  </div>

  <div v-if="filterCounts.all" class="overlay-candidate-toolbar">
    <div class="overlay-candidate-toolbar-title">
      <strong>候选处理队列</strong>
      <p>建议顺序：先修复失败候选，再处理重复复核，最后确认可规划候选。</p>
    </div>
    <el-radio-group v-model="candidateFilterModel" size="small">
      <el-radio-button
        v-for="option in filterOptions"
        :key="option.value"
        :value="option.value"
      >
        {{ option.label }} {{ filterCounts[option.value] }}
      </el-radio-button>
    </el-radio-group>
    <el-button size="small" type="primary" plain :disabled="!hasRepairTarget" @click="emit('open-first-repairable')">
      {{ repairTargetLabel }}
    </el-button>
  </div>

  <p v-if="filterCounts.all && !filteredCandidateCount" class="overlay-empty-filter">
    当前筛选下暂无候选，切换到“全部”可查看完整草稿。
  </p>

  <section v-if="nodes.length || edges.length" class="overlay-subsection">
    <h4>候选校验明细</h4>
    <div class="candidate-card-list compact">
      <article v-for="node in nodes" :key="node.node_id" class="preview-candidate-card">
        <div class="candidate-card-header">
          <strong>{{ node.name || node.node_id }}</strong>
          <el-button size="small" text type="primary" @click="emit('edit-node', node)">编辑修复</el-button>
        </div>
        <p>{{ node.summary || node.legality_rationale || '暂无摘要' }}</p>
        <el-tag size="small" :type="validationStatusMeta(node.validation_status).tagType">{{ validationStatusMeta(node.validation_status).label }}</el-tag>
        <ul v-if="node.validation_errors?.length" class="validation-errors">
          <li v-for="error in node.validation_errors" :key="`${node.node_id}-${error}`">{{ validationErrorMessage(error) }}</li>
        </ul>
      </article>
      <article v-for="edge in edges" :key="edge.edge_id" class="preview-candidate-card">
        <div class="candidate-card-header">
          <strong>{{ edge.source_node_id || edge.source_name_or_id }} → {{ edge.target_node_id || edge.target_name_or_id }}</strong>
          <el-button size="small" text type="primary" @click="emit('edit-edge', edge)">编辑修复</el-button>
        </div>
        <p>{{ edge.legality_rationale || '暂无合法性说明' }}</p>
        <el-tag size="small" :type="validationStatusMeta(edge.validation_status).tagType">{{ validationStatusMeta(edge.validation_status).label }}</el-tag>
        <el-tag size="small" type="info">{{ edge.relation_type }}</el-tag>
        <ul v-if="edge.validation_errors?.length" class="validation-errors">
          <li v-for="error in edge.validation_errors" :key="`${edge.edge_id}-${error}`">{{ validationErrorMessage(error) }}</li>
        </ul>
      </article>
    </div>
  </section>

  <section v-if="resources.length" class="overlay-subsection">
    <h4>资源候选</h4>
    <article v-for="resource in resources" :key="resource.resource_id" class="resource-candidate">
      <div class="candidate-card-header">
        <div class="resource-title">{{ resource.title }}</div>
        <el-button size="small" text type="primary" @click="emit('edit-resource', resource)">编辑修复</el-button>
      </div>
      <p>{{ resource.summary || '暂无摘要' }}</p>
      <el-tag size="small" :type="resourceTypeMeta(resource.resource_type || 'resource').tagType" :title="resource.resource_type || 'resource'">
        {{ resourceTypeMeta(resource.resource_type || 'resource').label }}
      </el-tag>
      <el-tag size="small" :type="validationStatusMeta(resource.validation_status).tagType">{{ validationStatusMeta(resource.validation_status).label }}</el-tag>
      <el-tag size="small" type="success">绑定 {{ resource.binding_summary?.count || 0 }}</el-tag>
      <ul v-if="resource.validation_errors?.length" class="validation-errors">
        <li v-for="error in resource.validation_errors" :key="`${resource.resource_id}-${error}`">{{ validationErrorMessage(error) }}</li>
      </ul>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type {
  OverlayEdgeCandidate,
  OverlayNodeCandidate,
  OverlayResourceCandidate,
} from '@/api/modules/graph'
import { resourceTypeMeta, validationStatusMeta } from '@/utils/displayLabels'
import type { CandidateIssueFilter } from './composables/useOverlayCandidateWorkflow'
import type {
  OverlayCandidateDiagnosticItem,
  OverlayCandidateDiagnosticSummary,
} from './overlaySessionPanelTypes'

type OverlayCandidateFilterOption = {
  value: CandidateIssueFilter
  label: string
}

type OverlayCandidateFilterCounts = Record<CandidateIssueFilter, number>

const props = defineProps<{
  diagnostics: OverlayCandidateDiagnosticItem[]
  diagnosticSummary: OverlayCandidateDiagnosticSummary
  filter: CandidateIssueFilter
  filterOptions: OverlayCandidateFilterOption[]
  filterCounts: OverlayCandidateFilterCounts
  filteredCandidateCount: number
  hasRepairTarget: boolean
  repairTargetLabel: string
  nodes: OverlayNodeCandidate[]
  edges: OverlayEdgeCandidate[]
  resources: OverlayResourceCandidate[]
  validationErrorMessage: (error: string) => string
}>()

const emit = defineEmits<{
  'update:filter': [filter: CandidateIssueFilter]
  'open-first-repairable': []
  'edit-node': [node: OverlayNodeCandidate]
  'edit-edge': [edge: OverlayEdgeCandidate]
  'edit-resource': [resource: OverlayResourceCandidate]
}>()

const candidateFilterModel = computed({
  get: () => props.filter,
  set: (filter) => emit('update:filter', filter),
})
</script>

<style scoped>
.overlay-diagnostic-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
  padding: 12px;
  border: 1px solid #d9ecff;
  border-radius: 10px;
  background: #ecf5ff;
}

.overlay-diagnostic-main {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.overlay-diagnostic-summary p,
.overlay-diagnostic-item p {
  margin: 4px 0 0;
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
}

.overlay-diagnostic-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.overlay-diagnostic-item {
  padding: 10px;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  background: #fff;
}

.overlay-diagnostic-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.overlay-diagnostic-target {
  color: #909399;
}

.overlay-candidate-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
  padding: 12px;
  border: 1px solid #f3d19e;
  border-radius: 10px;
  background: #fdf6ec;
}

.overlay-candidate-toolbar-title p,
.overlay-empty-filter {
  margin: 4px 0 0;
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
}

.overlay-empty-filter {
  padding: 10px 12px;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
  background: #fff;
}

.overlay-subsection {
  margin-top: 14px;
}

.overlay-subsection h4 {
  margin: 0 0 8px;
  color: #303133;
  font-size: 14px;
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

.candidate-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.preview-candidate-card,
.resource-candidate {
  padding: 10px;
  border: 1px solid #d9ecff;
  border-radius: 8px;
  background: #fff;
}

.resource-candidate {
  margin-bottom: 8px;
  border-color: #ebeef5;
  border-radius: 10px;
}

.preview-candidate-card p {
  margin: 6px 0;
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
}

.validation-errors {
  margin: 8px 0 0;
  padding-left: 18px;
  color: #b88230;
  font-size: 12px;
  line-height: 1.6;
}

.resource-title {
  color: #303133;
  font-weight: 600;
}
</style>
