<template>
  <section
    class="goal-resolution-workspace"
    :class="[
      `goal-resolution-workspace--${resolutionView}`,
      { 'goal-resolution-workspace--wizard': variant === 'wizard' },
    ]"
  >
    <div v-if="resolutionView === 'editing'" class="goal-input-panel">
      <el-form :model="form" :rules="rules" ref="formRef" label-position="top" class="goal-form">
        <section class="goal-form-intro">
          <p class="form-eyebrow">第一步：描述目标</p>
          <h2>{{ mode === 'reconfirm' ? '重新确认学习目标' : '创建新的学习项目' }}</h2>
          <p>用一句自然语言描述想学什么，系统会先判断覆盖情况，再推荐创建、澄清或扩展草稿流程。</p>
        </section>

        <el-form-item label="学习目标" prop="goal_text" class="primary-goal-field">
          <el-input
            v-model="form.goal_text"
            type="textarea"
            :rows="variant === 'wizard' ? 3 : 4"
            placeholder="例如：我想系统学习机器学习基础"
          />
          <div class="goal-field-footer">
            <span>{{ goalQualityLabel }}</span>
            <span>{{ normalizedGoalText.length }} 字</span>
          </div>
          <section class="goal-template-grid" aria-label="学习目标模板">
            <button
              v-for="example in goalExamples"
              :key="example.goal"
              type="button"
              class="goal-template-card"
              @click="applyGoalExample(example)"
            >
              <span>{{ example.label }}</span>
              <strong>{{ example.goal }}</strong>
              <small>{{ example.description }}</small>
            </button>
          </section>
          <div class="form-hint">
            推荐先保持自然表达；系统会根据机器学习基础图谱判断是否可直接规划。
          </div>
        </el-form-item>

        <el-form-item label="项目标题" prop="title">
          <el-input v-model="form.title" placeholder="例如：机器学习基础学习计划" />
          <div class="form-hint">标题用于区分多个学习计划，不影响目标解析结果。</div>
        </el-form-item>

        <details class="advanced-options">
          <summary>高级选项：手动指定目标类型</summary>
          <el-form-item label="目标类型" prop="goal_type">
            <el-radio-group v-model="form.goal_type">
              <el-radio-button value="auto">自动识别</el-radio-button>
              <el-radio-button value="domain">领域型</el-radio-button>
              <el-radio-button value="concept">概念型</el-radio-button>
              <el-radio-button value="problem">问题型</el-radio-button>
            </el-radio-group>
            <div class="type-desc">
              <el-text v-if="form.goal_type === 'auto'" type="info">推荐保持自动识别；需要精确控制时再切换类型。</el-text>
              <el-text v-else-if="form.goal_type === 'domain'" type="info">系统学习整个领域的知识体系。</el-text>
              <el-text v-else-if="form.goal_type === 'concept'" type="info">深入理解某个具体概念。</el-text>
              <el-text v-else type="info">围绕具体问题生成更聚焦的学习路径。</el-text>
            </div>
          </el-form-item>
        </details>

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

        <details class="display-options">
          <summary>显示设置</summary>
          <DisplayModeSwitch v-model="displayMode" />
        </details>

        <div class="actions">
          <el-button type="primary" size="large" @click="handlePreview" :loading="previewLoading" :disabled="!normalizedGoalText || !form.title.trim()">
            {{ previewButtonLabel }}
          </el-button>
        </div>
      </el-form>
    </div>

    <div v-else-if="resolutionView === 'parsing'" class="goal-parsing-panel" aria-live="polite">
      <section class="goal-form-intro goal-form-intro--compact">
        <p class="form-eyebrow">正在解析</p>
        <h2>正在生成目标候选</h2>
        <p>系统会先理解你的自然语言目标，再匹配正式知识图谱，最后判断是否可以安全创建项目。</p>
      </section>

      <div class="goal-parsing-steps" aria-label="目标解析进度">
        <article v-for="item in parsingSteps" :key="item.title">
          <span>{{ item.index }}</span>
          <strong>{{ item.title }}</strong>
          <small>{{ item.description }}</small>
        </article>
      </div>

      <div class="goal-parsing-summary">
        <span>原始目标</span>
        <strong>{{ normalizedGoalText }}</strong>
        <small>项目标题：{{ form.title.trim() || '未填写' }} · 目标类型：{{ goalTypeSelectionLabel(form.goal_type) }}</small>
      </div>
    </div>

    <div v-else-if="previewState" class="goal-review-panel">
      <section class="goal-review-hero">
        <header>
          <div>
            <p class="form-eyebrow">解析结果确认</p>
            <h2>{{ reviewTitle }}</h2>
            <p>{{ reviewDescription }}</p>
          </div>
          <el-tag :type="reviewTagType" size="large">{{ reviewTagLabel }}</el-tag>
        </header>

        <div class="goal-review-summary-grid">
          <article>
            <span>已解析目标</span>
            <strong>{{ previewGoalText || normalizedGoalText }}</strong>
          </article>
          <article>
            <span>项目标题</span>
            <strong>{{ form.title.trim() || '未填写' }}</strong>
          </article>
          <article>
            <span>目标类型</span>
            <strong>{{ goalTypeSelectionLabel(form.goal_type) }}</strong>
          </article>
        </div>

        <div class="goal-review-actions">
          <el-button plain @click="returnToEditing">修改目标</el-button>
          <el-button type="primary" plain :loading="previewLoading" @click="handlePreview">
            {{ previewButtonLabel }}
          </el-button>
        </div>

        <details class="display-options goal-review-display-options">
          <summary>显示设置</summary>
          <DisplayModeSwitch v-model="displayMode" />
        </details>
      </section>

      <GoalPreviewPanel
        v-model:selected-candidate-id="selectedCandidateId"
        v-model:accept-partial="acceptPartial"
        v-model:show-all-candidates="showAllCandidates"
        :preview-state="previewState"
        :unsafe-state-message="unsafeStateMessage"
        :preview-dirty="previewDirty"
        :mode="mode"
        :display-mode="displayMode"
        :hashes-agree="hashesAgree"
        :hash-status-label="hashStatusLabel"
        :can-open-extension-draft="canOpenExtensionDraft"
        :can-show-confirm-button="canShowConfirmButton"
        :can-confirm="canCreate"
        :confirm-loading="createLoading"
        :confirm-label="submitButtonLabel"
        :confirm-hint="confirmHint"
        :clarification-loading="clarificationLoading"
        :clarification-answers="clarificationAnswers"
        @select-clarification-option="selectClarificationOption"
        @update-clarification-free-text="updateClarificationFreeText"
        @submit-clarification="handleClarificationAnswer"
        @confirm="handleCreate"
        @create-extension-project="handleCreateExtensionProject"
        @rewrite="applyRewriteSuggestion"
        @open-extension-draft="goToExtensionDraftEntry"
      />
    </div>

    <el-alert
      v-if="operationErrorMessage"
      title="操作未完成"
      type="error"
      :closable="false"
      show-icon
      class="operation-error-alert"
    >
      <template #default>{{ operationErrorMessage }}</template>
    </el-alert>
  </section>
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
  type GoalResolutionPreviewResponse,
  type GoalType,
  type GoalTypeSelection,
  type Project,
  type ReviewExtensionDraftCoverageResponse,
  type SelectCandidateCoverageResponse,
} from '@/api/modules/project'
import DisplayModeSwitch from '@/components/DisplayModeSwitch.vue'
import { useDisplayMode } from '@/composables/useDisplayMode'
import { useProjectStore } from '@/stores/project'
import { formatErrorCode } from '@/utils/displayLabels'
import GoalPreviewPanel from './GoalPreviewPanel.vue'

interface GoalFormState {
  title: string
  goal_text: string
  goal_type: GoalTypeSelection
}

interface GoalExample {
  label: string
  goal: string
  title: string
  type: GoalTypeSelection
  description: string
}

interface ClarificationAnswerState {
  selected_option_id: string
  free_text: string
}

type GoalResolutionView = 'editing' | 'parsing' | 'reviewing'

const parsingSteps = [
  { index: '01', title: '识别目标类型', description: '判断是领域型、概念型还是问题型目标。' },
  { index: '02', title: '匹配知识图谱', description: '只从当前可审查图谱中寻找正式候选。' },
  { index: '03', title: '检查规划边界', description: '确认是否可创建、需澄清或进入扩展草稿。' },
]

const STALE_GOAL_ERRORS = new Set([
  'STALE_RESOLUTION_SESSION',
  'STALE_CLARIFICATION_SESSION',
  'PROJECT_GRAPH_DRIFT',
  'PACK_HASH_DRIFT',
])

const goalExamples: GoalExample[] = [
  { label: '领域型目标', goal: '我想系统学习机器学习基础', title: '机器学习基础学习计划', type: 'domain', description: '适合完整学习一块知识体系。' },
  { label: '概念型目标', goal: '我想理解梯度下降', title: '梯度下降学习计划', type: 'concept', description: '适合深入理解一个核心概念。' },
  { label: '问题型目标', goal: '我想搞懂逻辑回归为什么能做分类', title: '逻辑回归分类学习计划', type: 'problem', description: '适合围绕具体问题规划学习路径。' },
]

const props = withDefaults(defineProps<{
  mode?: 'create' | 'reconfirm'
  projectId?: string
  projectTitle?: string
  initialGoalText?: string
  initialGoalType?: GoalTypeSelection
  reconfirmReason?: string
  variant?: 'overview' | 'wizard'
}>(), {
  mode: 'create',
  projectId: '',
  projectTitle: '',
  initialGoalText: '',
  initialGoalType: 'auto',
  reconfirmReason: '',
  variant: 'overview',
})

const emit = defineEmits<{
  created: [project: Project]
  updated: [project: Project]
  dirtyStateChanged: [dirty: boolean]
}>()
const router = useRouter()
const projectStore = useProjectStore()
const { displayMode } = useDisplayMode()
const formRef = ref<FormInstance>()
const previewLoading = ref(false)
const parsingViewActive = ref(false)
const createLoading = ref(false)
const clarificationLoading = ref(false)
const previewState = ref<GoalResolutionPreviewResponse | null>(null)
const selectedCandidateId = ref('')
const previewGoalText = ref('')
const previewRequestedGoalType = ref<GoalType | null>(null)
const previewProjectId = ref('')
const previewMode = ref<'create' | 'reconfirm'>('create')
const unsafeStateMessage = ref('')
const operationErrorMessage = ref('')
const acceptPartial = ref(false)
const showAllCandidates = ref(false)
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
const goalQualityLabel = computed(() => {
  const length = normalizedGoalText.value.length
  if (!length) return '先输入一个真实学习目标'
  if (length < 8) return '目标略短，建议补充想学的范围或问题'
  if (length > 80) return '目标较长，系统会优先识别核心学习意图'
  return '目标描述清晰，可以开始解析'
})
const expectedProjectId = computed(() => (props.mode === 'reconfirm' ? props.projectId : ''))
const createFormDirty = computed(() => (
  props.mode === 'create' && (
    Boolean(form.title.trim()) ||
    Boolean(normalizedGoalText.value) ||
    form.goal_type !== 'auto' ||
    Boolean(previewState.value)
  )
))

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
const previewButtonLabel = computed(() => (previewState.value ? '重新解析学习目标' : '解析学习目标'))
const submitButtonLabel = computed(() => {
  if (isPartialResponse(previewState.value)) {
    return props.mode === 'reconfirm' ? '接受部分覆盖并更新目标' : '接受部分覆盖并创建项目'
  }
  return props.mode === 'reconfirm' ? '确认并更新项目目标' : '确认并创建项目'
})
const confirmHint = computed(() => {
  const state = previewState.value
  if (!state || !canShowConfirmButton.value) {
    return ''
  }
  if (previewDirty.value) {
    return '目标内容已变化，请先重新解析再确认。'
  }
  if (unsafeStateMessage.value) {
    return unsafeStateMessage.value
  }
  if (isPartialResponse(state)) {
    return acceptPartial.value
      ? '确认后将只使用已覆盖部分生成路径，缺失概念会进入审计记录。'
      : '请先勾选接受部分覆盖，系统才会创建或更新项目。'
  }
  if (!selectedCandidateId.value) {
    return '请先选择一个学习方案，再确认创建。'
  }
  return '确认后，系统会把所选学习方案作为正式路径目标。'
})
const reasonMessage = computed(() => {
  if (props.reconfirmReason === 'goal-targets-removed') {
    return '当前项目的已确认目标节点已被图谱审核全部移除，请重新确认学习目标后再继续生成或重规划。'
  }
  return ''
})
const resolutionView = computed<GoalResolutionView>(() => {
  if (parsingViewActive.value) {
    return 'parsing'
  }
  if (previewState.value) {
    return 'reviewing'
  }
  return 'editing'
})
const reviewTitle = computed(() => {
  const state = previewState.value
  if (previewDirty.value) return '目标内容已变化'
  if (unsafeStateMessage.value) return '当前结果需要重新确认'
  if (isSelectCandidateResponse(state)) return '已生成可确认的目标候选'
  if (isPartialResponse(state)) return '当前目标只能部分覆盖'
  if (isClarificationResponse(state)) return '还需要回答一个澄清问题'
  if (isExtensionDraftResponse(state)) return '需要先创建图谱扩展草稿'
  return '当前目标暂不支持直接创建'
})
const reviewDescription = computed(() => {
  const state = previewState.value
  if (previewDirty.value) return '你已修改目标内容或目标类型，请重新解析后再确认，避免使用过期候选。'
  if (unsafeStateMessage.value) return unsafeStateMessage.value
  if (isSelectCandidateResponse(state)) return '输入区已收起，请在下方确认系统推荐的正式图谱候选。'
  if (isPartialResponse(state)) return '正式路径只会使用已覆盖知识点，缺失概念会进入审计记录。'
  if (isClarificationResponse(state)) return '先确认目标边界，系统不会把未澄清内容直接写入项目。'
  if (isExtensionDraftResponse(state)) return '扩展草稿需要进入 Knowledge 审核；审核前不会影响正式路径。'
  return '请按建议改写目标，或回到输入区重新描述学习目标。'
})
const reviewTagLabel = computed(() => {
  const state = previewState.value
  if (previewDirty.value) return '需重新解析'
  if (unsafeStateMessage.value) return '不可写入'
  if (isSelectCandidateResponse(state)) return '可确认'
  if (isPartialResponse(state)) return '部分覆盖'
  if (isClarificationResponse(state)) return '待澄清'
  if (isExtensionDraftResponse(state)) return '需审核'
  return '不可创建'
})
const reviewTagType = computed(() => {
  const state = previewState.value
  if (previewDirty.value || unsafeStateMessage.value) return 'warning'
  if (isSelectCandidateResponse(state)) return 'success'
  if (isBoundaryResponse(state)) return 'danger'
  return 'warning'
})

watch(createFormDirty, (dirty) => {
  emit('dirtyStateChanged', dirty)
}, { immediate: true })

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

function goalTypeSelectionLabel(type: GoalTypeSelection) {
  const map: Record<GoalTypeSelection, string> = {
    auto: '自动识别',
    domain: '领域型目标',
    concept: '概念型目标',
    problem: '问题型目标',
  }
  return map[type]
}

function selectClarificationOption(questionId: string, optionId: string) {
  clarificationAnswers[questionId].selected_option_id = optionId
}

function updateClarificationFreeText(questionId: string, value: string) {
  clarificationAnswers[questionId].free_text = value
}

function applyRewriteSuggestion(suggestion: string) {
  const quoted = suggestion.match(/[“\"]([^”\"]+)[”\"]/)?.[1]
  form.goal_text = quoted || suggestion
  clearPreviewState('已替换为建议目标，请重新解析。')
}

function applyGoalExample(example: GoalExample) {
  form.goal_text = example.goal
  form.goal_type = example.type
  if (!form.title.trim()) {
    form.title = example.title
  }
  clearPreviewState('已填入示例目标，请解析学习目标。')
}

function returnToEditing() {
  clearPreviewState()
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
  parsingViewActive.value = false
  previewState.value = null
  selectedCandidateId.value = ''
  previewGoalText.value = ''
  previewRequestedGoalType.value = null
  previewProjectId.value = ''
  previewMode.value = props.mode
  unsafeStateMessage.value = message
  operationErrorMessage.value = ''
  acceptPartial.value = false
  showAllCandidates.value = false
  resetClarificationAnswers([])
}

function errorMessageFromResponse(error: any, fallback: string) {
  const data = error?.response?.data
  const code = data?.error || data?.reason_code || data?.details?.reason_code
  const formatted = formatErrorCode(code)
  if (formatted) {
    return formatted
  }
  if (typeof data?.message === 'string' && data.message.trim()) {
    return data.message.trim()
  }
  if (typeof data?.detail === 'string' && data.detail.trim()) {
    return data.detail.trim()
  }
  return fallback
}

function setOperationError(error: any, fallback: string) {
  operationErrorMessage.value = errorMessageFromResponse(error, fallback)
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
  operationErrorMessage.value = ''
  previewState.value = preview
  unsafeStateMessage.value = ''
  acceptPartial.value = false
  showAllCandidates.value = false
  previewGoalText.value = normalizedGoalText.value
  previewRequestedGoalType.value = requestedGoalType.value ?? null
  previewProjectId.value = expectedProjectId.value
  previewMode.value = props.mode

  if (isSelectCandidateResponse(preview)) {
    const recommendedCandidate = preview.candidates.find((candidate) => candidate.candidate_id === preview.recommended_candidate_id)
    selectedCandidateId.value = recommendedCandidate?.is_recommended === false || recommendedCandidate?.recommended_action === 'clarify'
      ? ''
      : preview.recommended_candidate_id
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
  const valid = await formRef.value?.validate().catch(() => false)
  if (typeof valid === 'boolean') {
    return valid
  }
  return Boolean(form.title.trim() && normalizedGoalText.value && form.goal_type)
}

async function handlePreview() {
  if (previewLoading.value) {
    return
  }
  previewLoading.value = true
  parsingViewActive.value = false
  operationErrorMessage.value = ''
  try {
    const valid = await validateForm()
    if (!valid) {
      return
    }

    parsingViewActive.value = true
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
      setOperationError(error, '目标解析暂时失败，请稍后重试，或检查后端与 LLM 运行时配置。')
    }
  } finally {
    previewLoading.value = false
    parsingViewActive.value = false
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
  operationErrorMessage.value = ''
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
        goal_frame: response.goal_frame || previewState.value.goal_frame,
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
    if (!handleUnsafeError(error)) {
      setOperationError(error, '澄清答案提交失败，请稍后重试。')
    }
  } finally {
    clarificationLoading.value = false
  }
}

async function handleCreate() {
  if (createLoading.value) {
    return
  }
  createLoading.value = true
  operationErrorMessage.value = ''
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
    if (!handleUnsafeError(error)) {
      setOperationError(error, '项目创建失败，请稍后重试。')
    }
  } finally {
    createLoading.value = false
  }
}

async function handleCreateExtensionProject() {
  if (createLoading.value || !isExtensionDraftResponse(previewState.value) || !previewState.value.session_id) {
    return
  }
  createLoading.value = true
  operationErrorMessage.value = ''
  try {
    const valid = await validateForm()
    if (!valid) {
      return
    }
    const project = await projectStore.create({
      title: form.title.trim(),
      goal_text: normalizedGoalText.value,
      resolution_session_id: previewState.value.session_id,
      creation_mode: 'extension_review',
    })
    emit('created', project)
    router.push({
      name: 'Knowledge',
      query: {
        scope: 'project',
        goalDraft: '1',
        resolutionSessionId: previewState.value.session_id,
      },
    })
  } catch (error: any) {
    if (!handleUnsafeError(error)) {
      setOperationError(error, '待扩展项目创建失败，请稍后重试。')
    }
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
.goal-resolution-workspace {
  display: grid;
  gap: var(--lp-space-4);
  min-width: 0;
}

.goal-input-panel,
.goal-parsing-panel,
.goal-review-panel {
  min-width: 0;
}

.goal-resolution-workspace--reviewing.goal-resolution-workspace--wizard {
  max-width: min(860px, 100%);
  margin: 0 auto;
}

.goal-form {
  display: flex;
  flex-direction: column;
}

.goal-form-intro,
.goal-review-hero,
.goal-parsing-panel {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 16px;
  background: var(--el-fill-color-light);
}

.goal-form-intro {
  margin-bottom: 18px;
  padding: 18px;
}

.goal-form-intro--compact {
  margin-bottom: var(--lp-space-4);
}

.form-eyebrow {
  margin: 0 0 6px;
  color: var(--el-color-primary);
  font-size: 13px;
  font-weight: 700;
}

.goal-form-intro h2,
.goal-review-hero h2,
.goal-parsing-panel h2 {
  margin: 0;
  font-size: 22px;
}

.goal-form-intro p,
.goal-review-hero p,
.goal-parsing-panel p {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}

.primary-goal-field :deep(.el-textarea__inner) {
  font-size: 15px;
  line-height: 1.7;
}

.goal-field-footer {
  display: flex;
  justify-content: space-between;
  gap: var(--lp-space-2);
  margin-top: var(--lp-space-2);
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.goal-template-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--lp-space-2);
  margin-top: var(--lp-space-3);
}

.goal-template-card {
  display: grid;
  gap: 5px;
  min-height: 112px;
  padding: var(--lp-space-3);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--lp-radius-md);
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-regular);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s ease, color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.goal-template-card span,
.goal-template-card small {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.goal-template-card strong {
  color: var(--el-text-color-primary);
  font-size: 13px;
  line-height: 1.5;
}

.goal-template-card:hover,
.goal-template-card:focus-visible {
  border-color: var(--el-color-primary);
  box-shadow: 0 8px 18px rgb(64 158 255 / 12%);
  transform: translateY(-1px);
  outline: none;
}

.goal-parsing-panel {
  display: grid;
  gap: var(--lp-space-4);
  padding: var(--lp-space-5);
  background: linear-gradient(135deg, var(--el-color-primary-light-9), var(--el-fill-color-blank));
}

.goal-parsing-steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--lp-space-3);
}

.goal-parsing-steps article {
  display: grid;
  gap: 6px;
  min-height: 128px;
  padding: var(--lp-space-3);
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: var(--lp-radius-md);
  background: rgb(255 255 255 / 82%);
}

.goal-parsing-steps span {
  width: fit-content;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--el-color-primary-light-8);
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
}

.goal-parsing-steps strong {
  color: var(--el-text-color-primary);
  font-size: 15px;
}

.goal-parsing-steps small,
.goal-parsing-summary small {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.goal-parsing-summary {
  display: grid;
  gap: 6px;
  padding: var(--lp-space-3);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--lp-radius-md);
  background: var(--el-fill-color-blank);
}

.goal-parsing-summary span,
.goal-review-summary-grid span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.goal-parsing-summary strong,
.goal-review-summary-grid strong {
  color: var(--el-text-color-primary);
  font-size: 15px;
  line-height: 1.5;
}

.goal-review-panel {
  display: flex;
  flex-direction: column;
  gap: var(--lp-space-4);
}

.goal-review-hero {
  display: grid;
  gap: var(--lp-space-3);
  padding: var(--lp-space-4);
  background: linear-gradient(135deg, var(--el-color-primary-light-9), var(--el-fill-color-blank));
}

.goal-review-hero header {
  display: flex;
  justify-content: space-between;
  gap: var(--lp-space-3);
  align-items: flex-start;
}

.goal-review-summary-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr 0.8fr;
  gap: var(--lp-space-2);
}

.goal-review-summary-grid article {
  display: grid;
  gap: 6px;
  min-width: 0;
  padding: var(--lp-space-3);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--lp-radius-md);
  background: rgb(255 255 255 / 84%);
}

.goal-review-summary-grid strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.goal-review-actions {
  display: flex;
  gap: var(--lp-space-2);
  flex-wrap: wrap;
}

.goal-review-actions :deep(.el-button) {
  min-height: 40px;
}

.goal-review-display-options {
  margin-top: 0;
}

.type-desc,
.form-hint {
  margin-top: 8px;
}

.advanced-options,
.display-options,
.debug-details {
  margin: 12px 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.advanced-options summary,
.display-options summary,
.debug-details summary {
  cursor: pointer;
  user-select: none;
}

.advanced-options :deep(.el-form-item),
.display-options :deep(.display-mode-switch) {
  margin-top: 12px;
  margin-bottom: 0;
}

.form-hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.reconfirm-alert {
  margin-bottom: 16px;
}

.operation-error-alert {
  margin-top: 0;
}

.actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.actions :deep(.el-button) {
  min-height: 44px;
}

@media (max-width: 1180px) {
  .goal-template-grid,
  .goal-parsing-steps,
  .goal-review-summary-grid {
    grid-template-columns: 1fr;
  }

  .goal-resolution-workspace--reviewing.goal-resolution-workspace--wizard {
    max-width: none;
  }

  .goal-review-summary-grid strong {
    white-space: normal;
  }
}

@media (max-width: 768px) {
  .goal-review-hero header {
    flex-direction: column;
  }
}
</style>
