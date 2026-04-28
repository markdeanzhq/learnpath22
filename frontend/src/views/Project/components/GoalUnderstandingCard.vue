<template>
  <section class="state-card goal-understanding-panel">
    <div class="section-header">
      <div>
        <h3>{{ userFacingTitle }}</h3>
        <p>{{ userFacingDescription }}</p>
      </div>
      <el-tag :type="coverageTagType">{{ coverageLabel(previewState.coverage_status) }}</el-tag>
    </div>

    <div v-if="previewState.goal_understanding" class="goal-understanding-summary">
      <div class="understanding-headline">
        <span class="summary-label">系统理解：</span>{{ understandingHeadline }}
      </div>
      <div class="semantic-tags">
        <el-tag :type="domainDecisionTagType(previewState.goal_understanding.domain_decision)">
          边界判断：{{ domainDecisionLabel(previewState.goal_understanding.domain_decision) }}
        </el-tag>
        <el-tag v-if="showAuditDetails" type="info">主领域：{{ previewState.goal_understanding.primary_domain }}</el-tag>
        <el-tag v-if="showAuditDetails" type="info">机器学习相关性：{{ mlRelevanceLabel(previewState.goal_understanding.ml_relevance) }}</el-tag>
        <el-tag v-if="showAuditDetails" type="warning">置信度：{{ formatConfidence(previewState.goal_understanding.confidence) }}</el-tag>
      </div>
      <div v-if="previewState.goal_understanding.target_concepts.length">
        <span class="summary-label">识别概念：</span>{{ previewState.goal_understanding.target_concepts.join('、') }}
      </div>
      <div v-if="previewState.goal_understanding.clarification_question">
        <span class="summary-label">建议澄清：</span>{{ previewState.goal_understanding.clarification_question }}
      </div>
      <ul v-if="showAuditDetails && previewState.goal_understanding.evidence.length" class="understanding-evidence-list">
        <li v-for="item in previewState.goal_understanding.evidence" :key="`${item.label}:${item.span}:${item.reason}`">
          <strong>{{ item.span }}</strong>：{{ item.reason }}
        </li>
      </ul>
    </div>

    <details v-if="showTechnicalDetails" class="debug-details">
      <summary>技术详情</summary>
      <div class="preview-meta">
        <el-tag type="info">响应类型：{{ resultTypeLabel(previewState.result_type) }}</el-tag>
        <el-tag v-if="autoDetectedGoalType" type="info">自动识别：{{ goalTypeLabel(autoDetectedGoalType) }}</el-tag>
        <el-tag type="success">目标类型：{{ goalTypeLabel(effectiveGoalType) }}</el-tag>
        <el-tag v-if="previewExpiresAt" type="warning">会话有效期至：{{ formatExpiresAt(previewExpiresAt) }}</el-tag>
      </div>

      <div v-if="previewState.goal_frame" class="goal-frame-summary">
        <div><span class="summary-label">原始目标：</span>{{ previewState.goal_frame.raw_text }}</div>
        <div v-if="previewState.goal_frame.target_concepts.length">
          <span class="summary-label">GoalFrame 识别概念：</span>{{ previewState.goal_frame.target_concepts.join('、') }}
        </div>
        <div v-if="previewState.goal_frame.uncertainties.length">
          <span class="summary-label">不确定项：</span>{{ previewState.goal_frame.uncertainties.join('、') }}
        </div>
        <div v-if="previewState.goal_understanding?.uncertainties.length">
          <span class="summary-label">LLM 不确定项：</span>{{ previewState.goal_understanding.uncertainties.join('、') }}
        </div>
      </div>

      <div class="trace-meta">
        <el-tag v-if="previewState.pack_hash" effect="plain">pack_hash：{{ shortHash(previewState.pack_hash) }}</el-tag>
        <el-tag v-if="previewState.project_graph_hash" effect="plain">project_graph_hash：{{ shortHash(previewState.project_graph_hash) }}</el-tag>
        <el-tag v-else-if="mode === 'create'" type="info" effect="plain">project_graph_hash：新建项目暂不适用</el-tag>
        <el-tag v-if="hashesAgree" type="success" effect="plain">{{ hashStatusLabel }}</el-tag>
        <el-tag v-else type="danger" effect="plain">哈希不一致</el-tag>
      </div>
    </details>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DisplayMode } from '@/composables/useDisplayMode'
import type {
  AnswerClarificationCoverageResponse,
  ConfirmPartialCoverageResponse,
  GoalResolutionPreviewResponse,
  ReviewExtensionDraftCoverageResponse,
  SelectCandidateCoverageResponse,
} from '@/api/modules/project'

const props = defineProps<{
  previewState: GoalResolutionPreviewResponse
  mode: 'create' | 'reconfirm'
  displayMode: DisplayMode
  hashesAgree: boolean
  hashStatusLabel: string
}>()

const showAuditDetails = computed(() => props.displayMode !== 'simple')
const showTechnicalDetails = computed(() => props.displayMode === 'debug')

const userFacingTitle = computed(() => {
  const state = props.previewState
  if (isSelectCandidateResponse(state)) return '可以创建学习路径'
  if (isPartialResponse(state)) return '可以先创建已覆盖部分'
  if (isClarificationResponse(state)) return '还需要确认目标范围'
  if (isExtensionDraftResponse(state)) return '当前知识图谱还没覆盖这个概念'
  return '当前目标暂不支持'
})

const userFacingDescription = computed(() => {
  const state = props.previewState
  if (isSelectCandidateResponse(state)) return '系统已理解目标，并找到可规划的机器学习基础路径。'
  if (isPartialResponse(state)) return '系统找到了一部分可规划内容，缺失概念会保留在审计记录中。'
  if (isClarificationResponse(state) && state.coverage_status === 'cross_domain') return '这个目标包含外部应用领域，请确认是否只学习机器学习基础部分。'
  if (isClarificationResponse(state)) return '系统还不能安全判断目标范围，请先回答一个澄清问题。'
  if (isExtensionDraftResponse(state)) return '可以在已有项目中把它作为图谱扩展草稿，经审核后再考虑参与路径。'
  return '当前原型只覆盖机器学习基础，暂不能为该目标创建正式路径。'
})

const understandingHeadline = computed(() => {
  const understanding = props.previewState.goal_understanding
  if (!understanding) return '尚未生成目标理解。'
  const concepts = understanding.target_concepts.length ? understanding.target_concepts.join('、') : props.previewState.goal_frame?.raw_text || '当前目标'
  if (understanding.domain_decision === 'in_domain') return `你想学习 ${concepts}。`
  if (understanding.domain_decision === 'cross_domain') return `你想在 ${understanding.primary_domain} 场景中学习 ${concepts}。`
  if (understanding.domain_decision === 'out_of_domain') return `你想学习 ${understanding.primary_domain} 方向，超出当前机器学习基础范围。`
  return '系统还需要更多信息才能确认学习目标。'
})

const coverageTagType = computed(() => {
  const status = props.previewState.coverage_status
  if (status === 'covered') return 'success'
  if (status === 'out_of_domain') return 'danger'
  return 'warning'
})

const autoDetectedGoalType = computed(() => isSelectCandidateResponse(props.previewState) ? props.previewState.auto_detected_goal_type : null)
const effectiveGoalType = computed(() => {
  const state = props.previewState
  if (isSelectCandidateResponse(state)) return state.effective_goal_type
  return state.goal_frame?.goal_type || 'auto'
})
const previewExpiresAt = computed(() => 'expires_at' in props.previewState ? props.previewState.expires_at || '' : '')

function isSelectCandidateResponse(value: GoalResolutionPreviewResponse): value is SelectCandidateCoverageResponse {
  return value.result_type === 'select_candidate'
}

function isPartialResponse(value: GoalResolutionPreviewResponse): value is ConfirmPartialCoverageResponse {
  return value.result_type === 'confirm_partial'
}

function isClarificationResponse(value: GoalResolutionPreviewResponse): value is AnswerClarificationCoverageResponse {
  return value.result_type === 'answer_clarification'
}

function isExtensionDraftResponse(value: GoalResolutionPreviewResponse): value is ReviewExtensionDraftCoverageResponse {
  return value.result_type === 'review_extension_draft'
}

function coverageLabel(status: string) {
  const map: Record<string, string> = {
    covered: '已覆盖',
    partial: '部分覆盖',
    in_domain_uncovered: '领域内未覆盖',
    adjacent_domain: '邻近领域',
    cross_domain: '跨领域目标',
    out_of_domain: '领域外',
    ambiguous: '待澄清',
  }
  return map[status] || status
}

function domainDecisionLabel(value: string) {
  const map: Record<string, string> = {
    in_domain: '领域内',
    cross_domain: '跨领域',
    out_of_domain: '领域外',
    ambiguous: '信息不足',
  }
  return map[value] || value
}

function domainDecisionTagType(value: string) {
  if (value === 'in_domain') return 'success'
  if (value === 'out_of_domain') return 'danger'
  return 'warning'
}

function mlRelevanceLabel(value: string) {
  const map: Record<string, string> = {
    core: '核心相关',
    prerequisite: '前置相关',
    application: '应用相关',
    none: '无直接相关',
    unclear: '不明确',
  }
  return map[value] || value
}

function goalTypeLabel(type: string | null | undefined) {
  const map: Record<string, string> = {
    auto: '自动识别',
    domain: '领域型',
    concept: '概念型',
    problem: '问题型',
  }
  return type ? map[type] || type : '未确定'
}

function resultTypeLabel(type: string) {
  const map: Record<string, string> = {
    select_candidate: '候选选择',
    confirm_partial: '部分确认',
    answer_clarification: '澄清回答',
    review_extension_draft: '扩展草稿',
    boundary_reject: '边界拒绝',
  }
  return map[type] || type
}

function formatConfidence(value: number) {
  return `${Math.round(value * 100)}%`
}

function shortHash(value: string) {
  return value.length > 12 ? `${value.slice(0, 12)}…` : value
}

function formatExpiresAt(expiresAt: string) {
  const date = new Date(expiresAt)
  if (Number.isNaN(date.getTime())) {
    return expiresAt
  }
  return date.toLocaleString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.state-card {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 16px;
  background: var(--el-fill-color-blank);
}

.section-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.section-header h3 {
  margin: 0 0 4px;
}

.section-header p {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.preview-meta,
.trace-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.goal-frame-summary,
.goal-understanding-summary {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.understanding-headline {
  font-size: 15px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
}

.semantic-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.understanding-evidence-list {
  margin: 4px 0 0;
  padding-left: 20px;
  color: var(--el-text-color-secondary);
}

.summary-label {
  font-weight: 600;
}

.trace-meta {
  margin-top: 12px;
}

.debug-details {
  margin: 12px 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.debug-details summary {
  cursor: pointer;
  user-select: none;
}
</style>
