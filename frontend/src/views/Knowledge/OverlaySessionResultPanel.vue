<template>
  <section class="overlay-result">
    <div class="section-header">
      <div>
        <h3>抽取结果</h3>
        <p v-if="showTechnicalDetails">追溯编号：{{ session.session.session_id }}</p>
        <p v-else>{{ overlaySessionGuide }}</p>
      </div>
      <el-tag :type="sessionStatusMeta(session.session.session_status).tagType" :title="session.session.session_status">
        {{ sessionStatusMeta(session.session.session_status).label }}
      </el-tag>
    </div>
    <el-descriptions :column="1" border size="small">
      <el-descriptions-item label="节点候选">{{ session.nodes?.length || 0 }}</el-descriptions-item>
      <el-descriptions-item label="关系候选">{{ session.edges?.length || 0 }}</el-descriptions-item>
      <el-descriptions-item label="资源候选">{{ session.resources?.length || 0 }}</el-descriptions-item>
      <el-descriptions-item label="校验概览">
        通过 {{ overlaySessionStats.valid }}，失败 {{ overlaySessionStats.invalid }}，待复核 {{ overlaySessionStats.needsReview }}，待审核 {{ overlaySessionStats.pendingReview }}
      </el-descriptions-item>
      <el-descriptions-item label="来源数">{{ session.sources?.length || 0 }}</el-descriptions-item>
    </el-descriptions>
    <el-alert
      class="overlay-alert"
      :type="overlaySessionStats.invalid ? 'warning' : 'info'"
      :closable="false"
      show-icon
      :title="overlaySessionGuide"
    />

    <section class="overlay-workflow" data-testid="overlay-workflow">
      <div class="overlay-workflow-header">
        <strong>草稿处理流程</strong>
        <span v-if="overlayWorkflowCurrentStep">当前阶段：{{ overlayWorkflowCurrentStep.title }}</span>
      </div>
      <ol class="overlay-workflow-steps">
        <li
          v-for="(step, index) in overlayWorkflowSteps"
          :key="step.key"
          class="overlay-workflow-step"
          :class="`is-${step.state}`"
        >
          <span class="overlay-workflow-index">{{ index + 1 }}</span>
          <div>
            <div class="overlay-workflow-step-title">
              <strong>{{ step.title }}</strong>
              <el-tag size="small" :type="step.tagType" effect="plain">{{ step.statusLabel }}</el-tag>
            </div>
            <p>{{ step.description }}</p>
          </div>
        </li>
      </ol>
    </section>

    <div v-if="overlayCandidateFilterCounts.all" class="overlay-candidate-toolbar">
      <div class="overlay-candidate-toolbar-title">
        <strong>候选处理队列</strong>
        <p>建议顺序：先修复失败候选，再处理重复复核，最后确认可规划候选。</p>
      </div>
      <el-radio-group v-model="candidateFilterModel" size="small">
        <el-radio-button
          v-for="option in overlayCandidateFilterOptions"
          :key="option.value"
          :value="option.value"
        >
          {{ option.label }} {{ overlayCandidateFilterCounts[option.value] }}
        </el-radio-button>
      </el-radio-group>
      <el-button size="small" type="primary" plain :disabled="!hasOverlayCandidateRepairTarget" @click="emit('open-first-repairable')">
        {{ overlayCandidateRepairTargetLabel }}
      </el-button>
    </div>

    <p v-if="overlayCandidateFilterCounts.all && !filteredOverlayCandidateCount" class="overlay-empty-filter">
      当前筛选下暂无候选，切换到“全部”可查看完整草稿。
    </p>

    <section v-if="filteredOverlayNodes.length || filteredOverlayEdges.length" class="overlay-subsection">
      <h4>候选校验明细</h4>
      <div class="candidate-card-list compact">
        <article v-for="node in filteredOverlayNodes" :key="node.node_id" class="preview-candidate-card">
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
        <article v-for="edge in filteredOverlayEdges" :key="edge.edge_id" class="preview-candidate-card">
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

    <section v-if="goalExtensionDraftDetails" class="overlay-subsection goal-draft-summary">
      <h4>目标缺口分析</h4>
      <el-alert
        class="overlay-alert"
        type="warning"
        :closable="false"
        show-icon
        title="扩展草稿只作为审核候选；未确认审核并开启规划前，不会进入正式路径。"
      />
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item v-if="goalExtensionDraftDetails.gap_analysis?.user_goal" label="用户目标">
          {{ goalExtensionDraftDetails.gap_analysis.user_goal }}
        </el-descriptions-item>
        <el-descriptions-item label="缺失概念">
          {{ goalDraftMissingConcepts.join('、') || '暂无' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="goalExtensionDraftDetails.gap_analysis?.why_current_graph_is_insufficient" label="缺口原因">
          {{ goalExtensionDraftDetails.gap_analysis.why_current_graph_is_insufficient }}
        </el-descriptions-item>
        <el-descriptions-item v-if="showAuditDetails" label="草稿来源">
          {{ goalExtensionDraftDetails.draft_metadata?.draft_engine || 'rules' }} / {{ goalExtensionDraftDetails.draft_metadata?.prompt_version || 'unknown' }}
        </el-descriptions-item>
        <el-descriptions-item v-if="showAuditDetails" label="安全边界">
          需人工审核：{{ goalExtensionDraftDetails.draft_metadata?.requires_user_review ? '是' : '否' }}；可直接规划：{{ goalExtensionDraftDetails.draft_metadata?.can_directly_plan ? '是' : '否' }}
        </el-descriptions-item>
      </el-descriptions>
      <ul v-if="goalDraftReviewNotes.length" class="review-notes">
        <li v-for="note in goalDraftReviewNotes" :key="note">{{ note }}</li>
      </ul>
      <div v-if="showAuditDetails && goalDraftReviewFocus.length" class="review-focus-list">
        <el-tag v-for="item in goalDraftReviewFocus" :key="item" type="info" effect="plain">{{ item }}</el-tag>
      </div>
    </section>

    <section v-if="filteredOverlayResources.length" class="overlay-subsection">
      <h4>资源候选</h4>
      <article v-for="resource in filteredOverlayResources" :key="resource.resource_id" class="resource-candidate">
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

    <section v-if="showAuditDetails && session.resources?.length" class="overlay-subsection">
      <h4>资源绑定</h4>
      <el-form label-position="top">
        <el-form-item label="资源">
          <el-select :model-value="resourceBinding.resourceId" placeholder="选择资源候选" style="width: 100%" @update:model-value="updateResourceBinding('resourceId', $event)">
            <el-option
              v-for="resource in session.resources || []"
              :key="resource.resource_id"
              :label="resource.title"
              :value="resource.resource_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="绑定目标类型">
          <el-radio-group :model-value="resourceBinding.targetType" @update:model-value="updateResourceBinding('targetType', $event)">
            <el-radio-button value="project_node">项目节点</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="绑定目标">
          <el-select :model-value="resourceBinding.targetId" filterable placeholder="选择知识点或阶段" style="width: 100%" @update:model-value="updateResourceBinding('targetId', $event)">
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
        <el-button size="small" type="primary" plain @click="emit('bind-resource')">绑定资源</el-button>
      </el-form>
    </section>

    <section v-if="showTechnicalDetails" class="overlay-subsection">
      <h4>高级操作：推广到领域包</h4>
      <el-button size="small" :loading="promotionLoading" @click="emit('preview-promotion')">预览推广结果（不写入）</el-button>
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
        :model-value="promotionSecret"
        class="promotion-secret"
        type="password"
        show-password
        placeholder="输入管理员密钥后确认推广"
        @update:model-value="emit('update:promotionSecret', String($event))"
      />
      <el-button size="small" type="danger" :loading="promotionLoading" @click="emit('commit-promotion')">确认推广</el-button>
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
import {
  promotionPreviewStatusMeta,
  resourceTypeMeta,
  sessionStatusMeta,
  validationStatusMeta,
} from '@/utils/displayLabels'
import type {
  CandidateIssueFilter,
  OverlaySessionView,
  OverlayWorkflowStep,
} from './composables/useOverlayCandidateWorkflow'
import type { ResourceBindingForm } from './composables/useOverlayPostActions'

type OverlaySessionStats = {
  invalid: number
  needsReview: number
  valid: number
  pendingReview: number
}

type OverlayCandidateFilterOption = {
  value: CandidateIssueFilter
  label: string
}

type OverlayCandidateFilterCounts = Record<CandidateIssueFilter, number>

type ResourceTargetOption = {
  id: string
  label: string
}

const props = defineProps<{
  session: OverlaySessionView
  showTechnicalDetails: boolean
  showAuditDetails: boolean
  overlaySessionGuide: string
  overlaySessionStats: OverlaySessionStats
  overlayWorkflowSteps: OverlayWorkflowStep[]
  overlayWorkflowCurrentStep: OverlayWorkflowStep | null
  overlayCandidateFilter: CandidateIssueFilter
  overlayCandidateFilterOptions: OverlayCandidateFilterOption[]
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
  'update:overlayCandidateFilter': [filter: CandidateIssueFilter]
  'open-first-repairable': []
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

function updateResourceBinding(field: keyof ResourceBindingForm, value: unknown) {
  emit('update-resource-binding', field, typeof value === 'string' ? value : String(value ?? ''))
}
</script>

<style scoped>
.overlay-result {
  padding: 14px;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  background: #fafafa;
}

.section-header,
.overlay-workflow-header,
.overlay-workflow-step-title,
.candidate-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
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

.overlay-alert {
  margin-bottom: 4px;
}

.overlay-workflow {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid #d9ecff;
  border-radius: 10px;
  background: #f4faff;
}

.overlay-workflow-header span {
  color: #409eff;
  font-size: 12px;
}

.overlay-workflow-steps {
  display: grid;
  gap: 8px;
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.overlay-workflow-step {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 8px;
  padding: 10px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
}

.overlay-workflow-step.is-current {
  border-color: #f3d19e;
  background: #fdf6ec;
}

.overlay-workflow-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  color: #fff;
  font-size: 12px;
  background: #909399;
}

.overlay-workflow-step.is-done .overlay-workflow-index {
  background: #67c23a;
}

.overlay-workflow-step.is-current .overlay-workflow-index {
  background: #e6a23c;
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
.overlay-workflow-step p,
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
  font-size: 14px;
  color: #303133;
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

.goal-draft-summary {
  padding: 12px;
  border: 1px solid #f3d19e;
  border-radius: 10px;
  background: #fdf6ec;
}

.review-notes {
  margin: 10px 0 0;
  padding-left: 18px;
  color: #606266;
  font-size: 12px;
  line-height: 1.7;
}

.review-focus-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
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
</style>
