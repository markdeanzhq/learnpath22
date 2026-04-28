<template>
  <div class="preview-panel">
    <el-alert
      v-if="unsafeStateMessage"
      title="当前预览不可继续写入"
      type="warning"
      :closable="false"
      show-icon
    >
      <template #default>{{ unsafeStateMessage }}</template>
    </el-alert>

    <el-alert
      v-else-if="previewDirty"
      title="请重新预览候选"
      type="warning"
      :closable="false"
      show-icon
    >
      <template #default>
        您修改了目标描述或目标类型，当前候选已经过期，请点击“重新预览候选”。
      </template>
    </el-alert>

    <el-alert
      v-else
      :title="statePanelTitle"
      :type="stateAlertType"
      :closable="false"
      show-icon
    >
      <template #default>{{ statePanelDescription }}</template>
    </el-alert>

    <GoalUnderstandingCard
      :preview-state="previewState"
      :mode="mode"
      :display-mode="displayMode"
      :hashes-agree="hashesAgree"
      :hash-status-label="hashStatusLabel"
    />

    <section class="state-card decision-summary-panel">
      <div class="section-header">
        <div>
          <h3>推荐下一步</h3>
          <p>{{ decisionSummary.description }}</p>
        </div>
        <el-tag :type="decisionSummaryTagType">{{ decisionSummary.badge }}</el-tag>
      </div>
      <div class="decision-grid">
        <div class="decision-item">
          <span class="decision-label">系统理解</span>
          <strong>{{ decisionSummary.goal }}</strong>
        </div>
        <div class="decision-item">
          <span class="decision-label">当前支持情况</span>
          <strong>{{ decisionSummary.coverage }}</strong>
        </div>
        <div class="decision-item decision-item-wide">
          <span class="decision-label">建议操作</span>
          <strong>{{ decisionSummary.action }}</strong>
        </div>
      </div>
    </section>

    <section v-if="coverageActions.length" class="state-card coverage-action-panel">
      <div class="section-header">
        <div>
          <h3>你可以怎么继续</h3>
          <p>系统把当前选择拆成保守路径、扩展草稿和改写目标，避免把未审核内容直接写入正式路径。</p>
        </div>
      </div>
      <div class="coverage-action-grid">
        <article v-for="action in coverageActions" :key="action.action" class="coverage-action-card" :class="{ disabled: !action.enabled }">
          <div class="coverage-action-header">
            <strong>{{ action.label }}</strong>
            <el-tag :type="coverageActionRiskTagType(action.risk_level)">{{ coverageActionRiskLabel(action.risk_level) }}</el-tag>
          </div>
          <p>{{ action.description }}</p>
          <p v-if="action.requires_review" class="form-hint">需要先审核草稿；审核前不会进入正式路径。</p>
          <p v-if="!action.enabled && action.disabled_reason" class="form-hint">{{ action.disabled_reason }}</p>
          <el-button
            v-if="action.action === 'use_existing_graph' && isPartialResponse(previewState)"
            plain
            type="primary"
            @click="$emit('update:acceptPartial', true)"
          >
            选择已有图谱方案
          </el-button>
          <el-button
            v-else-if="action.action === 'create_extension_draft' && isExtensionDraftResponse(previewState) && canOpenExtensionDraft"
            plain
            type="primary"
            :disabled="!action.enabled"
            @click="$emit('openExtensionDraft')"
          >
            预览扩展草稿
          </el-button>
          <el-button
            v-else-if="action.action === 'create_extension_draft' && isExtensionDraftResponse(previewState) && mode === 'create' && previewState.session_id"
            plain
            type="primary"
            :loading="confirmLoading"
            :disabled="!action.enabled || previewDirty || Boolean(unsafeStateMessage)"
            @click="$emit('createExtensionProject')"
          >
            创建待扩展项目
          </el-button>
        </article>
      </div>
    </section>

    <section v-if="candidateResponses.length" class="state-card candidate-selection-panel">
      <div class="section-header">
        <div>
          <h3>{{ candidateSectionTitle }}</h3>
          <p>{{ candidateSectionDescription }}</p>
        </div>
        <el-tag v-if="topCandidate" :type="confidenceTagType(topCandidate.confidence_level)">{{ confidenceLabel(topCandidate.confidence_level) }}</el-tag>
      </div>

      <div class="candidate-list">
        <el-card
          v-for="candidate in visibleCandidates"
          :key="candidate.candidate_id"
          shadow="never"
          class="candidate-card"
          :class="{ selected: selectedCandidateId === candidate.candidate_id }"
          @click="selectCandidate(candidate.candidate_id)"
        >
          <div class="candidate-header">
            <div class="candidate-title-row">
              <el-radio-group :model-value="selectedCandidateId" @update:model-value="selectCandidate">
                <el-radio :value="candidate.candidate_id">{{ candidateTitle(candidate) }}</el-radio>
              </el-radio-group>
              <el-tag v-if="candidate.candidate_id === recommendedCandidateId && candidate.is_recommended !== false" type="success">建议确认</el-tag>
            </div>
            <div class="candidate-meta">
              <el-tag>{{ goalTypeLabel(candidate.goal_type) }}</el-tag>
              <el-tag :type="confidenceTagType(candidate.confidence_level)">{{ confidenceLabel(candidate.confidence_level) }}</el-tag>
              <el-tag v-if="showAuditDetails" type="info" :title="resolveSourceMeta(candidate.resolve_source).detail || candidate.resolve_source">
                {{ resolveSourceMeta(candidate.resolve_source).label }}
              </el-tag>
              <el-tag :type="recommendedActionTagType(candidate.recommended_action)">{{ recommendedActionLabel(candidate.recommended_action) }}</el-tag>
            </div>
          </div>

          <p class="candidate-explanation">{{ candidate.user_explanation || candidate.explanation }}</p>
          <p v-if="showAuditDetails && candidate.confidence_reason" class="candidate-confidence-reason">{{ candidate.confidence_reason }}</p>

          <div v-if="showAuditDetails && candidate.match_signals?.length" class="candidate-signals">
            <el-tag
              v-for="signal in candidate.match_signals"
              :key="`${candidate.candidate_id}:${signal.type}:${signal.label}`"
              size="small"
              effect="plain"
              :title="signal.detail"
            >
              {{ signal.label }}：{{ signalStrengthLabel(signal.strength) }}
            </el-tag>
          </div>

          <div class="candidate-targets">
            <span class="targets-label">路径将围绕这些内容展开：</span>
            <el-tag
              v-for="target in candidateTargetRefs(candidate)"
              :key="target.node_id"
              size="small"
              effect="plain"
              :title="`节点 ID：${target.node_id}`"
            >
              {{ target.node_name }}
            </el-tag>
          </div>

          <details v-if="showTechnicalDetails" class="candidate-debug-details">
            <summary>技术评分详情</summary>
            <div class="candidate-debug-content">
              <el-tag type="info">评分 {{ formatScore(candidate.score) }}</el-tag>
              <span>{{ candidate.debug_explanation || candidate.explanation }}</span>
            </div>
          </details>
        </el-card>
      </div>
      <el-button
        v-if="hiddenCandidateCount > 0"
        class="show-alternatives-button"
        plain
        @click="$emit('update:showAllCandidates', !showAllCandidates)"
      >
        {{ showAllCandidates ? '收起其他学习方案' : `查看 ${hiddenCandidateCount} 个其他学习方案` }}
      </el-button>
    </section>

    <section v-if="isPartialResponse(previewState)" class="state-card partial-coverage-panel">
      <div class="section-header">
        <div>
          <h3>部分覆盖确认</h3>
          <p>下列概念暂未进入当前机器学习知识图谱，正式路径只会包含已覆盖目标。</p>
        </div>
      </div>
      <div class="missing-concepts">
        <el-tag v-for="concept in previewState.missing_concepts" :key="concept" type="warning">{{ concept }}</el-tag>
      </div>
      <label class="partial-acceptance">
        <input :checked="acceptPartial" type="checkbox" @change="$emit('update:acceptPartial', ($event.target as HTMLInputElement).checked)" />
        我确认接受部分覆盖，并允许缺失概念写入路径审计。
      </label>
    </section>

    <section v-if="canShowConfirmButton" class="state-card confirm-action-panel">
      <div class="section-header">
        <div>
          <h3>确认这个选择</h3>
          <p>{{ confirmHint }}</p>
        </div>
      </div>
      <el-button type="success" :loading="confirmLoading" :disabled="!canConfirm" @click="$emit('confirm')">
        {{ confirmLabel }}
      </el-button>
    </section>

    <section v-if="isClarificationResponse(previewState)" class="state-card clarification-panel">
      <div class="section-header">
        <div>
          <h3>请选择继续方式</h3>
          <p>你的选择会先经过后端校验，不会直接写入项目。</p>
        </div>
        <el-tag type="warning">{{ previewState.turn_count }}/{{ previewState.max_turns }}</el-tag>
      </div>

      <div v-for="question in previewState.questions" :key="question.question_id" class="clarification-question">
        <div class="question-prompt">{{ question.prompt }}</div>
        <div class="clarification-options">
          <button
            v-for="option in question.options"
            :key="option.option_id"
            type="button"
            class="clarification-option-card"
            :class="{ selected: clarificationAnswers[question.question_id].selected_option_id === option.option_id }"
            @click="$emit('selectClarificationOption', question.question_id, option.option_id)"
          >
            {{ option.label }}
          </button>
        </div>
        <el-input
          v-if="question.allow_free_text"
          :model-value="clarificationAnswers[question.question_id].free_text"
          type="textarea"
          :rows="2"
          placeholder="可选：补充一句自然语言说明"
          @update:model-value="$emit('updateClarificationFreeText', question.question_id, String($event))"
        />
      </div>

      <el-button type="primary" :loading="clarificationLoading" @click="$emit('submitClarification')">
        提交澄清答案
      </el-button>
    </section>

    <section v-if="isBoundaryResponse(previewState)" class="state-card boundary-rejection-panel">
      <div class="section-header">
        <div>
          <h3>暂时不能创建这个目标</h3>
          <p>当前系统只支持机器学习基础范围，请选择下面建议重新描述目标。</p>
        </div>
      </div>
      <p>{{ previewState.reason_text }}</p>
      <div class="rewrite-actions">
        <el-button
          v-for="suggestion in previewState.rewrite_suggestions"
          :key="suggestion"
          plain
          @click="$emit('rewrite', suggestion)"
        >
          {{ suggestion }}
        </el-button>
      </div>
      <details v-if="showTechnicalDetails" class="debug-details">
        <summary>技术详情</summary>
        <el-tag type="danger">{{ previewState.reason_code }}</el-tag>
      </details>
    </section>

    <section v-if="isExtensionDraftResponse(previewState)" class="state-card extension-draft-panel">
      <div class="section-header">
        <div>
          <h3>生成可审核的扩展草稿</h3>
          <p>当前知识图谱还没有完整覆盖这些概念。你可以先生成草稿，审核通过后再考虑用于学习路径。</p>
        </div>
      </div>
      <div class="missing-concepts">
        <span class="targets-label">待补充概念：</span>
        <el-tag v-for="concept in previewState.missing_concepts" :key="concept" type="warning">{{ concept }}</el-tag>
      </div>
      <el-alert
        class="extension-draft-explain"
        title="为什么不能直接生成路径？"
        type="info"
        :closable="false"
        show-icon
      >
        <template #default>
          学习路径依赖知识图谱中的前置关系。概念未覆盖时，系统需要先生成并审核扩展草稿，避免生成顺序不可靠的路径。
        </template>
      </el-alert>
      <el-button type="primary" plain :disabled="!canOpenExtensionDraft" @click="$emit('openExtensionDraft')">
        预览扩展草稿
      </el-button>
      <p class="form-hint">
        {{ canOpenExtensionDraft ? '只会打开草稿预览，不会自动写入正式图谱或直接生成路径。' : '新建流程会先创建待扩展项目，再进入草稿审核；审核前不会生成正式路径。' }}
      </p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DisplayMode } from '@/composables/useDisplayMode'
import type {
  AnswerClarificationCoverageResponse,
  BoundaryRejectCoverageResponse,
  ConfirmPartialCoverageResponse,
  GoalCoverageAction,
  GoalResolutionCandidate,
  GoalResolutionNodeRef,
  GoalResolutionPreviewResponse,
  ReviewExtensionDraftCoverageResponse,
  SelectCandidateCoverageResponse,
} from '@/api/modules/project'
import { resolveSourceMeta } from '@/utils/displayLabels'
import GoalUnderstandingCard from './GoalUnderstandingCard.vue'

interface ClarificationAnswerState {
  selected_option_id: string
  free_text: string
}

const props = defineProps<{
  previewState: GoalResolutionPreviewResponse
  unsafeStateMessage: string
  previewDirty: boolean
  mode: 'create' | 'reconfirm'
  displayMode: DisplayMode
  hashesAgree: boolean
  hashStatusLabel: string
  selectedCandidateId: string
  acceptPartial: boolean
  showAllCandidates: boolean
  canOpenExtensionDraft: boolean
  canShowConfirmButton: boolean
  canConfirm: boolean
  confirmLoading: boolean
  confirmLabel: string
  confirmHint: string
  clarificationLoading: boolean
  clarificationAnswers: Record<string, ClarificationAnswerState>
}>()

const showAuditDetails = computed(() => props.displayMode !== 'simple')
const showTechnicalDetails = computed(() => props.displayMode === 'debug')

const emit = defineEmits<{
  'update:selectedCandidateId': [candidateId: string]
  'update:acceptPartial': [accepted: boolean]
  'update:showAllCandidates': [showAll: boolean]
  selectClarificationOption: [questionId: string, optionId: string]
  updateClarificationFreeText: [questionId: string, value: string]
  submitClarification: []
  confirm: []
  createExtensionProject: []
  rewrite: [suggestion: string]
  openExtensionDraft: []
}>()

const candidateResponses = computed(() => {
  const state = props.previewState
  if (!isSelectCandidateResponse(state) && !isPartialResponse(state)) {
    return []
  }
  return state.candidates
})
const recommendedCandidateId = computed(() => isSelectCandidateResponse(props.previewState) ? props.previewState.recommended_candidate_id : '')
const topCandidate = computed(() => candidateResponses.value.find((candidate) => candidate.candidate_id === recommendedCandidateId.value) || candidateResponses.value[0] || null)
const candidateSectionTitle = computed(() => {
  if (isPartialResponse(props.previewState)) return '确认可覆盖部分'
  if (topCandidate.value?.confidence_level === 'high') return '确认学习目标'
  if (topCandidate.value?.confidence_level === 'low') return '请谨慎确认系统理解'
  return '确认系统理解'
})
const candidateSectionDescription = computed(() => {
  if (isPartialResponse(props.previewState)) return '当前知识图谱只能覆盖一部分目标，请确认是否先创建已覆盖部分。'
  if (topCandidate.value?.confidence_level === 'high') return '系统已找到较可靠的图谱候选，请确认这是否符合你的真实学习目标。'
  if (topCandidate.value?.confidence_level === 'low') return '当前候选依据较弱，建议优先澄清或改写目标，不要把它当作强推荐。'
  return '系统找到了一组可能匹配的图谱候选，请检查后再确认。'
})
const visibleCandidates = computed(() => {
  if (props.showAllCandidates || candidateResponses.value.length <= 1) {
    return candidateResponses.value
  }
  const recommended = candidateResponses.value.find((candidate) => candidate.candidate_id === recommendedCandidateId.value)
  return [recommended || candidateResponses.value[0]].filter(Boolean) as GoalResolutionCandidate[]
})
const hiddenCandidateCount = computed(() => Math.max(candidateResponses.value.length - visibleCandidates.value.length, 0))
const coverageActions = computed<GoalCoverageAction[]>(() => {
  const state = props.previewState
  if (isPartialResponse(state) || isExtensionDraftResponse(state)) {
    return state.available_actions || []
  }
  return []
})
const decisionSummary = computed(() => {
  const state = props.previewState
  const goal = state.goal_understanding?.target_concepts.length
    ? state.goal_understanding.target_concepts.join('、')
    : state.goal_frame?.raw_text || '当前学习目标'

  if (isSelectCandidateResponse(state)) {
    const candidate = topCandidate.value
    if (candidate?.confidence_level === 'high') {
      return {
        badge: '可创建',
        goal,
        coverage: '当前知识图谱可以较可靠地支持',
        action: '确认学习方案后创建项目',
        description: '系统已找到可用于正式路径的学习方案，请确认这就是你的真实目标。',
      }
    }
    if (candidate?.confidence_level === 'low') {
      return {
        badge: '建议澄清',
        goal,
        coverage: '当前只找到弱匹配候选',
        action: '优先改写目标或继续澄清',
        description: '系统还不能稳妥判断你的目标，直接创建可能无法覆盖真实需求。',
      }
    }
    return {
      badge: '请确认',
      goal,
      coverage: '当前知识图谱找到可能匹配的方案',
      action: '检查方案内容后再确认',
      description: '系统找到了候选学习方案，但仍需要你判断是否符合预期。',
    }
  }

  if (isPartialResponse(state)) {
    return {
      badge: '部分覆盖',
      goal,
      coverage: '只能覆盖其中一部分内容',
      action: '接受部分覆盖，或改写目标',
      description: '正式路径只会包含已覆盖知识点，缺失概念会写入审计记录。',
    }
  }

  if (isClarificationResponse(state)) {
    return {
      badge: '待澄清',
      goal,
      coverage: state.coverage_status === 'cross_domain' ? '包含机器学习之外的应用领域' : '当前信息不足以安全规划',
      action: '回答澄清问题后重新解析',
      description: '你的回答只会用于确认目标范围，不会直接写入项目。',
    }
  }

  if (isExtensionDraftResponse(state)) {
    return {
      badge: '需扩展',
      goal,
      coverage: '当前知识图谱尚未覆盖该概念',
      action: '生成可审核的扩展草稿',
      description: '系统可以创建扩展草稿，审核通过后再考虑用于路径规划。',
    }
  }

  return {
    badge: '不可创建',
    goal,
    coverage: '超出当前机器学习基础范围',
    action: '按建议改写目标后重新解析',
    description: '当前目标无法安全映射到正式学习路径。',
  }
})
const decisionSummaryTagType = computed(() => {
  if (isBoundaryResponse(props.previewState)) return 'danger'
  if (isSelectCandidateResponse(props.previewState) && topCandidate.value?.confidence_level === 'high') return 'success'
  return 'warning'
})
const statePanelTitle = computed(() => {
  const map: Record<string, string> = {
    select_candidate: '已生成目标候选',
    confirm_partial: '需要确认部分覆盖',
    answer_clarification: '需要补充澄清答案',
    review_extension_draft: '需要进入项目扩展草稿',
    boundary_reject: '目标超出安全边界',
  }
  return map[props.previewState.result_type] || '目标理解结果'
})
const statePanelDescription = computed(() => {
  const state = props.previewState
  if (isSelectCandidateResponse(state)) return '系统会优先推荐最匹配的候选；请先选择候选，再创建项目或重新确认目标。'
  if (isPartialResponse(state)) return '当前目标只有一部分可由知识图谱覆盖，必须显式接受后才能写入。'
  if (isClarificationResponse(state) && state.coverage_status === 'cross_domain') return '当前目标包含外部应用领域，请先确认是否只按机器学习基础部分创建路径。'
  if (isClarificationResponse(state)) return '当前目标存在歧义，请先完成受控澄清，不会直接写入项目。'
  if (isExtensionDraftResponse(state)) return '当前概念属于领域内未覆盖内容，只能作为项目扩展草稿入口处理。'
  return '当前目标不能安全映射到正式路径，请改写后重新预览。'
})
const stateAlertType = computed(() => {
  if (isBoundaryResponse(props.previewState)) return 'error'
  if (isPartialResponse(props.previewState) || isClarificationResponse(props.previewState) || isExtensionDraftResponse(props.previewState)) return 'warning'
  return 'success'
})

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

function isBoundaryResponse(value: GoalResolutionPreviewResponse): value is BoundaryRejectCoverageResponse {
  return value.result_type === 'boundary_reject'
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

function candidateTitle(candidate: GoalResolutionCandidate) {
  const prefixMap: Record<string, string> = {
    domain: '学习方案：系统学习',
    concept: '学习方案：聚焦概念',
    problem: '学习方案：解决问题',
  }
  const prefix = prefixMap[candidate.goal_type] || '学习方案'
  return `${prefix}｜${candidate.description}`
}

function formatScore(score: number) {
  return score.toFixed(2)
}

function confidenceLabel(level: GoalResolutionCandidate['confidence_level']) {
  const map: Record<string, string> = {
    high: '高置信',
    medium: '需确认',
    low: '低置信',
  }
  return level ? map[level] || level : '需确认'
}

function confidenceTagType(level: GoalResolutionCandidate['confidence_level']) {
  if (level === 'high') return 'success'
  if (level === 'low') return 'danger'
  return 'warning'
}

function recommendedActionLabel(action: GoalResolutionCandidate['recommended_action']) {
  const map: Record<string, string> = {
    confirm: '可确认',
    review: '请检查',
    clarify: '建议澄清',
    rewrite: '建议改写',
    extension_draft: '扩展草稿',
  }
  return action ? map[action] || action : '请检查'
}

function recommendedActionTagType(action: GoalResolutionCandidate['recommended_action']) {
  if (action === 'confirm') return 'success'
  if (action === 'clarify' || action === 'rewrite') return 'danger'
  return 'warning'
}

function coverageActionRiskLabel(level: GoalCoverageAction['risk_level']) {
  const map: Record<string, string> = {
    low: '低风险',
    medium: '需审核',
    high: '高风险',
  }
  return map[level] || level
}

function coverageActionRiskTagType(level: GoalCoverageAction['risk_level']) {
  if (level === 'low') return 'success'
  if (level === 'high') return 'danger'
  return 'warning'
}

function signalStrengthLabel(strength: string) {
  const map: Record<string, string> = {
    strong: '强',
    medium: '中',
    weak: '弱',
  }
  return map[strength] || strength
}

function candidateTargetRefs(candidate: GoalResolutionCandidate): GoalResolutionNodeRef[] {
  if (candidate.target_nodes?.length) {
    return candidate.target_nodes
  }
  return candidate.target_node_ids.map((nodeId, index) => ({
    node_id: nodeId,
    node_name: candidate.target_node_names?.[index] || `未识别知识点（${nodeId}）`,
  }))
}

function selectCandidate(candidateId: string) {
  if (!props.previewDirty && !props.unsafeStateMessage) {
    emit('update:selectedCandidateId', candidateId)
  }
}
</script>

<style scoped>
.preview-panel {
  margin-top: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

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

.candidate-meta,
.candidate-signals,
.missing-concepts {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.decision-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.decision-item {
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-light);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.decision-item-wide {
  grid-column: 1 / -1;
}

.decision-label {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.coverage-action-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.coverage-action-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px;
  background: var(--el-fill-color-light);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.coverage-action-card.disabled {
  opacity: 0.72;
}

.coverage-action-card p {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.coverage-action-card :deep(.el-button) {
  min-height: 44px;
  align-self: flex-start;
}

.coverage-action-header {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: flex-start;
}

.targets-label {
  font-weight: 600;
}

.candidate-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.show-alternatives-button {
  margin-top: 12px;
}

.candidate-card {
  cursor: pointer;
  border: 1px solid var(--el-border-color);
}

.candidate-card.selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-5);
}

.confirm-action-panel :deep(.el-button) {
  min-height: 44px;
}

.candidate-header {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.candidate-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.candidate-explanation {
  margin: 12px 0 6px;
  color: var(--el-text-color-regular);
}

.candidate-confidence-reason {
  margin: 0 0 10px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.candidate-signals {
  margin-bottom: 10px;
}

.candidate-debug-details {
  margin-top: 10px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.candidate-debug-details summary {
  cursor: pointer;
  user-select: none;
}

.candidate-debug-content {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.candidate-targets,
.partial-acceptance {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.extension-draft-explain {
  margin: 12px 0;
}

.partial-acceptance {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.clarification-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.clarification-question {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
}

.question-prompt {
  font-weight: 600;
}

.clarification-options,
.rewrite-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.clarification-option-card {
  min-height: 44px;
  padding: 10px 14px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-primary);
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.clarification-option-card:hover,
.clarification-option-card.selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-5);
}

.form-hint {
  margin-top: 8px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

@media (max-width: 768px) {
  .decision-grid,
  .coverage-action-grid {
    grid-template-columns: 1fr;
  }

  .decision-item-wide {
    grid-column: auto;
  }
}
</style>
