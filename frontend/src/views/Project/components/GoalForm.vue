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
        用一句自然语言描述想学什么即可；系统会先判断是否属于机器学习基础范围，再给出下一步建议。
      </div>
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

    <div class="actions">
      <el-button type="primary" @click="handlePreview" :loading="previewLoading">
        {{ previewButtonLabel }}
      </el-button>
    </div>
  </el-form>

  <GoalPreviewPanel
    v-if="previewState"
    v-model:selected-candidate-id="selectedCandidateId"
    v-model:accept-partial="acceptPartial"
    v-model:show-all-candidates="showAllCandidates"
    :preview-state="previewState"
    :unsafe-state-message="unsafeStateMessage"
    :preview-dirty="previewDirty"
    :mode="mode"
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
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { FormInstance, FormRules } from 'element-plus'
import {
  projectApi,
  type AnswerClarificationCoverageResponse,
  type ClarificationQuestion,
  type ConfirmPartialCoverageResponse,
  type GoalResolutionPreviewResponse,
  type GoalType,
  type GoalTypeSelection,
  type Project,
  type ReviewExtensionDraftCoverageResponse,
  type SelectCandidateCoverageResponse,
} from '@/api/modules/project'
import { useProjectStore } from '@/stores/project'
import GoalPreviewPanel from './GoalPreviewPanel.vue'

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
  showAllCandidates.value = false
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

async function handleCreateExtensionProject() {
  if (createLoading.value || !isExtensionDraftResponse(previewState.value) || !previewState.value.session_id) {
    return
  }
  createLoading.value = true
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

.advanced-options,
.debug-details {
  margin: 12px 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.advanced-options summary,
.debug-details summary {
  cursor: pointer;
  user-select: none;
}

.advanced-options :deep(.el-form-item) {
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

.actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

</style>
