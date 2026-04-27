<template>
  <el-form :model="form" :rules="rules" ref="formRef" label-position="top">
    <el-form-item label="项目标题" prop="title">
      <el-input v-model="form.title" placeholder="例如：机器学习基础学习计划" />
    </el-form-item>

    <el-form-item label="学习目标" prop="goal_text">
      <el-input
        v-model="form.goal_text"
        type="textarea"
        :rows="3"
        placeholder="描述你想学什么，例如：我想系统学习机器学习基础"
      />
      <div class="form-hint">
        当前原型面向机器学习基础单领域；若没有可确认候选，系统会显示结构化原因，包含 reason_code 与 reason_text，帮助您改写目标。
      </div>
    </el-form-item>

    <el-form-item label="目标类型" prop="goal_type">
      <el-radio-group v-model="form.goal_type">
        <el-radio-button value="auto">自动识别</el-radio-button>
        <el-radio-button value="domain">领域型</el-radio-button>
        <el-radio-button value="concept">概念型</el-radio-button>
        <el-radio-button value="problem">问题型</el-radio-button>
      </el-radio-group>
      <div class="type-desc">
        <el-text v-if="form.goal_type === 'auto'" type="info">先自动识别目标类型，之后您仍可改类型并重新预览候选。</el-text>
        <el-text v-else-if="form.goal_type === 'domain'" type="info">系统学习整个领域的知识体系。</el-text>
        <el-text v-else-if="form.goal_type === 'concept'" type="info">深入理解某个具体概念。</el-text>
        <el-text v-else type="info">围绕具体问题生成更聚焦的学习路径。</el-text>
      </div>
    </el-form-item>

    <el-alert
      v-if="mode === 'reconfirm' && reasonMessage"
      :title="projectTitle ? `重新确认：${projectTitle}` : '请重新确认学习目标'"
      type="warning"
      :closable="false"
      show-icon
      class="reconfirm-alert"
    >
      <template #default>{{ reasonMessage }}</template>
    </el-alert>

    <div class="actions">
      <el-button type="primary" @click="handlePreview" :loading="previewLoading">
        {{ previewButtonLabel }}
      </el-button>
      <el-button
        v-if="canShowConfirmButton"
        type="success"
        @click="handleCreate"
        :loading="createLoading"
        :disabled="!canCreate"
      >
        {{ submitButtonLabel }}
      </el-button>
    </div>
  </el-form>

  <div v-if="previewState" class="preview-panel">
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

    <section class="state-card goal-understanding-panel">
      <div class="section-header">
        <div>
          <h3>目标理解</h3>
          <p>GoalFrame 只辅助理解目标，正式路径仍以已确认候选和图谱规则为准。</p>
        </div>
        <el-tag :type="coverageTagType">{{ coverageLabel(previewState.coverage_status) }}</el-tag>
      </div>

      <div class="preview-meta">
        <el-tag type="info">响应类型：{{ resultTypeLabel(previewState.result_type) }}</el-tag>
        <el-tag v-if="autoDetectedGoalType" type="info">自动识别：{{ goalTypeLabel(autoDetectedGoalType) }}</el-tag>
        <el-tag type="success">目标类型：{{ goalTypeLabel(effectiveGoalType) }}</el-tag>
        <el-tag v-if="previewExpiresAt" type="warning">会话有效期至：{{ formatExpiresAt(previewExpiresAt) }}</el-tag>
      </div>

      <div v-if="previewState.goal_understanding" class="goal-understanding-summary">
        <div class="semantic-tags">
          <el-tag :type="domainDecisionTagType(previewState.goal_understanding.domain_decision)">
            边界判断：{{ domainDecisionLabel(previewState.goal_understanding.domain_decision) }}
          </el-tag>
          <el-tag type="info">主领域：{{ previewState.goal_understanding.primary_domain }}</el-tag>
          <el-tag type="info">机器学习相关性：{{ mlRelevanceLabel(previewState.goal_understanding.ml_relevance) }}</el-tag>
          <el-tag type="warning">置信度：{{ formatConfidence(previewState.goal_understanding.confidence) }}</el-tag>
        </div>
        <div v-if="previewState.goal_understanding.target_concepts.length">
          <span class="summary-label">LLM 识别概念：</span>{{ previewState.goal_understanding.target_concepts.join('、') }}
        </div>
        <div v-if="previewState.goal_understanding.uncertainties.length">
          <span class="summary-label">LLM 不确定项：</span>{{ previewState.goal_understanding.uncertainties.join('、') }}
        </div>
        <div v-if="previewState.goal_understanding.clarification_question">
          <span class="summary-label">建议澄清：</span>{{ previewState.goal_understanding.clarification_question }}
        </div>
        <ul v-if="previewState.goal_understanding.evidence.length" class="understanding-evidence-list">
          <li v-for="item in previewState.goal_understanding.evidence" :key="`${item.label}:${item.span}:${item.reason}`">
            <strong>{{ item.span }}</strong>：{{ item.reason }}
          </li>
        </ul>
      </div>

      <div v-if="previewState.goal_frame" class="goal-frame-summary">
        <div><span class="summary-label">原始目标：</span>{{ previewState.goal_frame.raw_text }}</div>
        <div v-if="previewState.goal_frame.target_concepts.length">
          <span class="summary-label">识别概念：</span>{{ previewState.goal_frame.target_concepts.join('、') }}
        </div>
        <div v-if="previewState.goal_frame.uncertainties.length">
          <span class="summary-label">不确定项：</span>{{ previewState.goal_frame.uncertainties.join('、') }}
        </div>
      </div>

      <div class="trace-meta">
        <el-tag v-if="previewState.pack_hash" effect="plain">pack_hash：{{ shortHash(previewState.pack_hash) }}</el-tag>
        <el-tag v-if="previewState.project_graph_hash" effect="plain">project_graph_hash：{{ shortHash(previewState.project_graph_hash) }}</el-tag>
        <el-tag v-else-if="mode === 'create'" type="info" effect="plain">project_graph_hash：新建项目暂不适用</el-tag>
        <el-tag v-if="hashesAgree" type="success" effect="plain">{{ hashStatusLabel }}</el-tag>
        <el-tag v-else type="danger" effect="plain">哈希不一致</el-tag>
      </div>
    </section>

    <section v-if="candidateResponses.length" class="state-card candidate-selection-panel">
      <div class="section-header">
        <div>
          <h3>{{ isPartialResponse(previewState) ? '部分覆盖候选' : '候选选择' }}</h3>
          <p>{{ isPartialResponse(previewState) ? '只会规划已覆盖节点，缺失概念会写入审计。' : '请选择一个候选作为正式路径目标。' }}</p>
        </div>
        <el-tag v-if="recommendedCandidateId" type="success">推荐候选</el-tag>
      </div>

      <div class="candidate-list">
        <el-card
          v-for="candidate in candidateResponses"
          :key="candidate.candidate_id"
          shadow="never"
          class="candidate-card"
          :class="{ selected: selectedCandidateId === candidate.candidate_id }"
          @click="selectCandidate(candidate.candidate_id)"
        >
          <div class="candidate-header">
            <div class="candidate-title-row">
              <el-radio-group v-model="selectedCandidateId">
                <el-radio :value="candidate.candidate_id">{{ candidate.description }}</el-radio>
              </el-radio-group>
              <el-tag v-if="candidate.candidate_id === recommendedCandidateId" type="success">推荐候选</el-tag>
            </div>
            <div class="candidate-meta">
              <el-tag>{{ goalTypeLabel(candidate.goal_type) }}</el-tag>
              <el-tag type="info" :title="resolveSourceMeta(candidate.resolve_source).detail || candidate.resolve_source">
                {{ resolveSourceMeta(candidate.resolve_source).label }}
              </el-tag>
              <el-tag type="warning">评分 {{ formatScore(candidate.score) }}</el-tag>
            </div>
          </div>

          <p class="candidate-explanation">{{ candidate.explanation }}</p>

          <div class="candidate-targets">
            <span class="targets-label">目标知识点：</span>
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
        </el-card>
      </div>
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
        <input v-model="acceptPartial" type="checkbox" />
        我确认接受部分覆盖，并允许缺失概念写入路径审计。
      </label>
    </section>

    <section v-if="isClarificationResponse(previewState)" class="state-card clarification-panel">
      <div class="section-header">
        <div>
          <h3>澄清问题</h3>
          <p>请用受控选项补充目标含义；自由文本会先解析为受控增量。</p>
        </div>
        <el-tag type="warning">{{ previewState.turn_count }}/{{ previewState.max_turns }}</el-tag>
      </div>

      <div v-for="question in previewState.questions" :key="question.question_id" class="clarification-question">
        <div class="question-prompt">{{ question.prompt }}</div>
        <el-radio-group v-model="clarificationAnswers[question.question_id].selected_option_id">
          <el-radio
            v-for="option in question.options"
            :key="option.option_id"
            :value="option.option_id"
          >
            {{ option.label }}
          </el-radio>
        </el-radio-group>
        <el-input
          v-if="question.allow_free_text"
          v-model="clarificationAnswers[question.question_id].free_text"
          type="textarea"
          :rows="2"
          placeholder="可选：补充一句自然语言说明"
        />
      </div>

      <el-button type="primary" :loading="clarificationLoading" @click="handleClarificationAnswer">
        提交澄清答案
      </el-button>
    </section>

    <section v-if="isBoundaryResponse(previewState)" class="state-card boundary-rejection-panel">
      <div class="section-header">
        <div>
          <h3>边界拒绝</h3>
          <p>该目标不能安全写入正式路径，请根据建议改写后重新预览。</p>
        </div>
        <el-tag type="danger">{{ previewState.reason_code }}</el-tag>
      </div>
      <p>{{ previewState.reason_text }}</p>
      <ul class="rewrite-list">
        <li v-for="suggestion in previewState.rewrite_suggestions" :key="suggestion">{{ suggestion }}</li>
      </ul>
    </section>

    <section v-if="isExtensionDraftResponse(previewState)" class="state-card extension-draft-panel">
      <div class="section-header">
        <div>
          <h3>扩展草稿入口</h3>
          <p>这些领域内概念当前未覆盖，只能进入项目 overlay 草稿，经校验、审核和规划开关后才可能参与路径。</p>
        </div>
      </div>
      <div class="missing-concepts">
        <el-tag v-for="concept in previewState.missing_concepts" :key="concept" type="warning">{{ concept }}</el-tag>
      </div>
      <el-button type="primary" plain :disabled="!canOpenExtensionDraft" @click="goToExtensionDraftEntry">
        前往知识图谱扩展草稿入口
      </el-button>
      <p class="form-hint">
        {{ canOpenExtensionDraft ? '跳转只会打开入口，不会自动创建草稿或写入图谱。' : '请在已有项目的目标重新确认流程中打开该入口。' }}
      </p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import {
  projectApi,
  type AnswerClarificationCoverageResponse,
  type BoundaryRejectCoverageResponse,
  type ClarificationQuestion,
  type ConfirmPartialCoverageResponse,
  type GoalResolutionCandidate,
  type GoalResolutionNodeRef,
  type GoalResolutionPreviewResponse,
  type GoalType,
  type GoalTypeSelection,
  type Project,
  type ReviewExtensionDraftCoverageResponse,
  type SelectCandidateCoverageResponse,
} from '@/api/modules/project'
import { useProjectStore } from '@/stores/project'
import { resolveSourceMeta } from '@/utils/displayLabels'

interface GoalFormState {
  title: string
  goal_text: string
  goal_type: GoalTypeSelection
}

interface ClarificationAnswerState {
  selected_option_id: string
  free_text: string
}

const STALE_GOAL_ERRORS = new Set([
  'STALE_RESOLUTION_SESSION',
  'STALE_CLARIFICATION_SESSION',
  'PROJECT_GRAPH_DRIFT',
  'PACK_HASH_DRIFT',
])

const props = withDefaults(defineProps<{
  mode?: 'create' | 'reconfirm'
  projectId?: string
  projectTitle?: string
  initialGoalText?: string
  initialGoalType?: GoalTypeSelection
  reconfirmReason?: string
}>(), {
  mode: 'create',
  projectId: '',
  projectTitle: '',
  initialGoalText: '',
  initialGoalType: 'auto',
  reconfirmReason: '',
})

const emit = defineEmits<{ created: [project: Project], updated: [project: Project] }>()
const router = useRouter()
const projectStore = useProjectStore()
const formRef = ref<FormInstance>()
const previewLoading = ref(false)
const createLoading = ref(false)
const clarificationLoading = ref(false)
const previewState = ref<GoalResolutionPreviewResponse | null>(null)
const selectedCandidateId = ref('')
const previewGoalText = ref('')
const previewRequestedGoalType = ref<GoalType | null>(null)
const previewProjectId = ref('')
const previewMode = ref<'create' | 'reconfirm'>('create')
const unsafeStateMessage = ref('')
const acceptPartial = ref(false)
const clarificationAnswers = reactive<Record<string, ClarificationAnswerState>>({})

const form = reactive<GoalFormState>({
  title: '',
  goal_text: '',
  goal_type: 'auto',
})

watch(
  () => [props.mode, props.projectId, props.projectTitle, props.initialGoalText, props.initialGoalType] as const,
  ([mode, projectId, projectTitle, initialGoalText, initialGoalType], previousValues) => {
    const previousMode = previousValues?.[0]
    const previousProjectId = previousValues?.[1]
    if (mode === 'reconfirm') {
      form.title = projectTitle
      form.goal_text = initialGoalText
      form.goal_type = initialGoalType
    }

    if (mode !== previousMode || projectId !== previousProjectId) {
      clearPreviewState('项目或确认上下文已变化，请重新预览目标。')
    }
  },
  { immediate: true },
)

const rules: FormRules = {
  title: [{ required: true, message: '请输入项目标题', trigger: 'blur' }],
  goal_text: [{ required: true, message: '请描述学习目标', trigger: 'blur' }],
  goal_type: [{ required: true, message: '请选择目标类型', trigger: 'change' }],
}

const requestedGoalType = computed<GoalType | undefined>(() =>
  form.goal_type === 'auto' ? undefined : form.goal_type,
)
const normalizedGoalText = computed(() => form.goal_text.trim())
const expectedProjectId = computed(() => (props.mode === 'reconfirm' ? props.projectId : ''))

const previewDirty = computed(() => {
  if (!previewState.value) {
    return false
  }

  return (
    previewGoalText.value !== normalizedGoalText.value ||
    previewRequestedGoalType.value !== (requestedGoalType.value ?? null)
  )
})
const contextMatches = computed(() => previewMode.value === props.mode && previewProjectId.value === expectedProjectId.value)
const hashesAgree = computed(() => {
  const state = previewState.value
  if (!state) {
    return true
  }

  const trace = state.audit_trace
  const packHashAgrees = Boolean(state.pack_hash) && (!trace || (trace.pack_hash ?? null) === (state.pack_hash ?? null))
  if (previewMode.value === 'create') {
    return packHashAgrees
  }

  return (
    packHashAgrees &&
    Boolean(state.project_graph_hash) &&
    (!trace || (trace.project_graph_hash ?? null) === (state.project_graph_hash ?? null))
  )
})
const hashStatusLabel = computed(() => (previewMode.value === 'create' ? '知识包哈希一致' : '哈希一致'))
const candidateResponses = computed(() => {
  const state = previewState.value
  if (!state || (!isSelectCandidateResponse(state) && !isPartialResponse(state))) {
    return []
  }
  return state.candidates
})
const recommendedCandidateId = computed(() => isSelectCandidateResponse(previewState.value) ? previewState.value.recommended_candidate_id : '')
const canShowConfirmButton = computed(() => isSelectCandidateResponse(previewState.value) || isPartialResponse(previewState.value))
const canCreate = computed(() => {
  const state = previewState.value
  if (!state || !canShowConfirmButton.value) {
    return false
  }
  if (!selectedCandidateId.value || previewDirty.value || unsafeStateMessage.value || !contextMatches.value || !hashesAgree.value) {
    return false
  }
  return !isPartialResponse(state) || acceptPartial.value
})
const canOpenExtensionDraft = computed(() => (
  props.mode === 'reconfirm' &&
  Boolean(props.projectId) &&
  isExtensionDraftResponse(previewState.value) &&
  Boolean(previewState.value.session_id) &&
  !previewDirty.value &&
  !unsafeStateMessage.value &&
  contextMatches.value &&
  hashesAgree.value
))
const previewButtonLabel = computed(() => (previewState.value && previewDirty.value ? '重新预览候选' : '解析目标候选'))
const submitButtonLabel = computed(() => {
  if (isPartialResponse(previewState.value)) {
    return props.mode === 'reconfirm' ? '接受部分覆盖并更新目标' : '接受部分覆盖并创建项目'
  }
  return props.mode === 'reconfirm' ? '确认并更新项目目标' : '确认并创建项目'
})
const reasonMessage = computed(() => {
  if (props.reconfirmReason === 'goal-targets-removed') {
    return '当前项目的已确认目标节点已被图谱审核全部移除，请重新确认学习目标后再继续生成或重规划。'
  }
  return ''
})
const statePanelTitle = computed(() => {
  const state = previewState.value
  if (!state) return ''
  const map: Record<string, string> = {
    select_candidate: '已生成目标候选',
    confirm_partial: '需要确认部分覆盖',
    answer_clarification: '需要补充澄清答案',
    review_extension_draft: '需要进入项目扩展草稿',
    boundary_reject: '目标超出安全边界',
  }
  return map[state.result_type] || '目标理解结果'
})
const statePanelDescription = computed(() => {
  const state = previewState.value
  if (!state) return ''
  if (isSelectCandidateResponse(state)) return '系统会优先推荐最匹配的候选；请先选择候选，再创建项目或重新确认目标。'
  if (isPartialResponse(state)) return '当前目标只有一部分可由知识图谱覆盖，必须显式接受后才能写入。'
  if (isClarificationResponse(state) && state.coverage_status === 'cross_domain') return '当前目标包含外部应用领域，请先确认是否只按机器学习基础部分创建路径。'
  if (isClarificationResponse(state)) return '当前目标存在歧义，请先完成受控澄清，不会直接写入项目。'
  if (isExtensionDraftResponse(state)) return '当前概念属于领域内未覆盖内容，只能作为项目扩展草稿入口处理。'
  return '当前目标不能安全映射到正式路径，请改写后重新预览。'
})
const stateAlertType = computed(() => {
  if (isBoundaryResponse(previewState.value)) return 'error'
  if (isPartialResponse(previewState.value) || isClarificationResponse(previewState.value) || isExtensionDraftResponse(previewState.value)) return 'warning'
  return 'success'
})
const coverageTagType = computed(() => {
  const status = previewState.value?.coverage_status
  if (status === 'covered') return 'success'
  if (status === 'out_of_domain') return 'danger'
  return 'warning'
})
const autoDetectedGoalType = computed(() => isSelectCandidateResponse(previewState.value) ? previewState.value.auto_detected_goal_type : null)
const effectiveGoalType = computed(() => {
  const state = previewState.value
  if (isSelectCandidateResponse(state)) return state.effective_goal_type
  return state?.goal_frame?.goal_type || 'auto'
})
const previewExpiresAt = computed(() => {
  const state = previewState.value
  if (!state || !('expires_at' in state)) return ''
  return state.expires_at || ''
})

function isSelectCandidateResponse(value: GoalResolutionPreviewResponse | null): value is SelectCandidateCoverageResponse {
  return value?.result_type === 'select_candidate'
}

function isPartialResponse(value: GoalResolutionPreviewResponse | null): value is ConfirmPartialCoverageResponse {
  return value?.result_type === 'confirm_partial'
}

function isClarificationResponse(value: GoalResolutionPreviewResponse | null): value is AnswerClarificationCoverageResponse {
  return value?.result_type === 'answer_clarification'
}

function isExtensionDraftResponse(value: GoalResolutionPreviewResponse | null): value is ReviewExtensionDraftCoverageResponse {
  return value?.result_type === 'review_extension_draft'
}

function isBoundaryResponse(value: GoalResolutionPreviewResponse | null): value is BoundaryRejectCoverageResponse {
  return value?.result_type === 'boundary_reject'
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

function formatConfidence(value: number) {
  return `${Math.round(value * 100)}%`
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

function formatScore(score: number) {
  return score.toFixed(2)
}

function shortHash(value: string) {
  return value.length > 12 ? `${value.slice(0, 12)}…` : value
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

function formatExpiresAt(expiresAt: string) {
  const date = new Date(expiresAt)
  if (Number.isNaN(date.getTime())) {
    return expiresAt
  }
  return date.toLocaleString('zh-CN', { hour12: false })
}

function selectCandidate(candidateId: string) {
  if (!previewDirty.value && !unsafeStateMessage.value) {
    selectedCandidateId.value = candidateId
  }
}

function resetClarificationAnswers(questions: ClarificationQuestion[]) {
  Object.keys(clarificationAnswers).forEach((key) => delete clarificationAnswers[key])
  questions.forEach((question) => {
    clarificationAnswers[question.question_id] = {
      selected_option_id: '',
      free_text: '',
    }
  })
}

function clearPreviewState(message = '') {
  previewState.value = null
  selectedCandidateId.value = ''
  previewGoalText.value = ''
  previewRequestedGoalType.value = null
  previewProjectId.value = ''
  previewMode.value = props.mode
  unsafeStateMessage.value = message
  acceptPartial.value = false
  resetClarificationAnswers([])
}

function isStaleGoalError(error: any) {
  const data = error?.response?.data
  return STALE_GOAL_ERRORS.has(data?.error) || STALE_GOAL_ERRORS.has(data?.reason_code) || STALE_GOAL_ERRORS.has(data?.details?.reason_code)
}

function handleUnsafeError(error: any) {
  if (!isStaleGoalError(error)) {
    return false
  }
  clearPreviewState('后端会话已过期或图谱/知识包哈希已变化，请重新预览目标。')
  return true
}

function applyPreview(preview: GoalResolutionPreviewResponse) {
  if (preview.goal_frame?.raw_text && preview.goal_frame.raw_text !== normalizedGoalText.value) {
    form.goal_text = preview.goal_frame.raw_text
  }

  previewState.value = preview
  unsafeStateMessage.value = ''
  acceptPartial.value = false
  previewGoalText.value = normalizedGoalText.value
  previewRequestedGoalType.value = requestedGoalType.value ?? null
  previewProjectId.value = expectedProjectId.value
  previewMode.value = props.mode

  if (isSelectCandidateResponse(preview)) {
    selectedCandidateId.value = preview.recommended_candidate_id
  } else if (isPartialResponse(preview)) {
    selectedCandidateId.value = preview.candidates[0]?.candidate_id || ''
  } else {
    selectedCandidateId.value = ''
  }

  if (isClarificationResponse(preview)) {
    resetClarificationAnswers(preview.questions)
  } else {
    resetClarificationAnswers([])
  }

  if (!hashesAgree.value) {
    unsafeStateMessage.value = '预览哈希与审计追溯不一致，请重新预览目标。'
  }
}

async function validateForm() {
  return formRef.value?.validate().catch(() => false)
}

async function handlePreview() {
  if (previewLoading.value) {
    return
  }
  previewLoading.value = true
  try {
    const valid = await validateForm()
    if (!valid) {
      return
    }

    const payload = {
      goal_text: normalizedGoalText.value,
      ...(requestedGoalType.value ? { requested_goal_type: requestedGoalType.value } : {}),
    }
    const preview = props.mode === 'reconfirm' && props.projectId
      ? await projectApi.previewForProject(props.projectId, payload)
      : await projectApi.preview(payload)
    applyPreview(preview)
  } catch (error: any) {
    if (!handleUnsafeError(error)) {
      unsafeStateMessage.value = ''
    }
  } finally {
    previewLoading.value = false
  }
}

async function handleClarificationAnswer() {
  if (clarificationLoading.value || !isClarificationResponse(previewState.value)) {
    return
  }
  const answers = previewState.value.questions
    .map((question) => ({
      question_id: question.question_id,
      selected_option_id: clarificationAnswers[question.question_id]?.selected_option_id || null,
      free_text: clarificationAnswers[question.question_id]?.free_text.trim() || null,
    }))
    .filter((answer) => answer.selected_option_id || answer.free_text)

  if (!answers.length) {
    unsafeStateMessage.value = '请至少选择一个澄清选项或填写自由文本。'
    return
  }

  clarificationLoading.value = true
  unsafeStateMessage.value = ''
  try {
    const response = props.mode === 'reconfirm' && props.projectId
      ? await projectApi.answerProjectClarification(props.projectId, previewState.value.clarification_session_id, { answers })
      : await projectApi.answerClarification(previewState.value.clarification_session_id, { answers })

    if (response.coverage_response) {
      applyPreview(response.coverage_response)
      return
    }

    if (response.status === 'active' && isClarificationResponse(previewState.value)) {
      previewState.value = {
        ...previewState.value,
        expires_at: response.expires_at,
        turn_count: response.turn_count,
        max_turns: response.max_turns,
        questions: response.questions,
      }
      resetClarificationAnswers(response.questions)
      return
    }

    clearPreviewState('澄清会话未返回可继续的目标预览，请重新解析目标。')
  } catch (error: any) {
    handleUnsafeError(error)
  } finally {
    clarificationLoading.value = false
  }
}

async function handleCreate() {
  if (createLoading.value) {
    return
  }
  createLoading.value = true
  try {
    const valid = await validateForm()
    const state = previewState.value
    if (!valid || !state || !selectedCandidateId.value || !canCreate.value) {
      return
    }
    if (!isSelectCandidateResponse(state) && !isPartialResponse(state)) {
      return
    }

    const payload = {
      goal_text: normalizedGoalText.value,
      resolution_session_id: state.session_id,
      selected_candidate_id: selectedCandidateId.value,
      ...(isPartialResponse(state) ? { accept_partial: true } : {}),
    }

    if (props.mode === 'reconfirm' && props.projectId) {
      const project = await projectApi.confirmGoalResolution(props.projectId, payload)
      projectStore.setCurrentProject(project)
      emit('updated', project)
      return
    }

    const project = await projectStore.create({
      title: form.title.trim(),
      ...payload,
    })
    emit('created', project)
  } catch (error: any) {
    handleUnsafeError(error)
  } finally {
    createLoading.value = false
  }
}

function goToExtensionDraftEntry() {
  if (!canOpenExtensionDraft.value || !isExtensionDraftResponse(previewState.value) || !previewState.value.session_id) {
    return
  }
  router.push({
    name: 'Knowledge',
    query: {
      scope: 'project',
      goalDraft: '1',
      resolutionSessionId: previewState.value.session_id,
    },
  })
}
</script>

<style scoped>
.type-desc,
.form-hint {
  margin-top: 8px;
}

.form-hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.reconfirm-alert {
  margin-bottom: 16px;
}

.actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

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

.preview-meta,
.trace-meta,
.candidate-meta,
.missing-concepts {
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

.summary-label,
.targets-label {
  font-weight: 600;
}

.trace-meta {
  margin-top: 12px;
}

.candidate-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.candidate-card {
  cursor: pointer;
  border: 1px solid var(--el-border-color);
}

.candidate-card.selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-5);
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
  margin: 12px 0;
  color: var(--el-text-color-regular);
}

.candidate-targets,
.partial-acceptance {
  font-size: 13px;
  color: var(--el-text-color-secondary);
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

.rewrite-list {
  margin: 8px 0 0;
  padding-left: 20px;
  color: var(--el-text-color-secondary);
}
</style>
