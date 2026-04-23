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
        v-if="previewState"
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
      v-if="previewDirty"
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
      title="已生成目标候选"
      type="success"
      :closable="false"
      show-icon
    >
      <template #default>
        系统会优先推荐最匹配的候选，您也可以切换到其他候选再创建项目。
      </template>
    </el-alert>

    <div class="preview-meta">
      <el-tag type="info">自动识别：{{ goalTypeLabel(previewState.auto_detected_goal_type) }}</el-tag>
      <el-tag type="success">当前预览：{{ goalTypeLabel(previewState.effective_goal_type) }}</el-tag>
      <el-tag type="warning">会话有效期至：{{ formatExpiresAt(previewState.expires_at) }}</el-tag>
    </div>

    <div class="candidate-list">
      <el-card
        v-for="candidate in previewState.candidates"
        :key="candidate.candidate_id"
        shadow="never"
        class="candidate-card"
        :class="{ selected: selectedCandidateId === candidate.candidate_id }"
        @click="selectedCandidateId = candidate.candidate_id"
      >
        <div class="candidate-header">
          <div class="candidate-title-row">
            <el-radio-group v-model="selectedCandidateId">
              <el-radio :value="candidate.candidate_id">{{ candidate.description }}</el-radio>
            </el-radio-group>
            <el-tag v-if="candidate.candidate_id === previewState.recommended_candidate_id" type="success">推荐候选</el-tag>
          </div>
          <div class="candidate-meta">
            <el-tag>{{ goalTypeLabel(candidate.goal_type) }}</el-tag>
            <el-tag type="info">{{ candidate.resolve_source }}</el-tag>
            <el-tag type="warning">评分 {{ formatScore(candidate.score) }}</el-tag>
          </div>
        </div>

        <p class="candidate-explanation">{{ candidate.explanation }}</p>

        <div class="candidate-targets">
          <span class="targets-label">目标节点：</span>
          <span>{{ candidate.target_node_ids.join('、') }}</span>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { projectApi, type GoalResolutionPreviewResponse, type GoalType, type GoalTypeSelection, type Project } from '@/api/modules/project'
import { useProjectStore } from '@/stores/project'

interface GoalFormState {
  title: string
  goal_text: string
  goal_type: GoalTypeSelection
  domain: 'machine_learning'
}

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
const projectStore = useProjectStore()
const formRef = ref<FormInstance>()
const previewLoading = ref(false)
const createLoading = ref(false)
const previewState = ref<GoalResolutionPreviewResponse | null>(null)
const selectedCandidateId = ref('')
const previewGoalText = ref('')
const previewRequestedGoalType = ref<GoalType | null>(null)

const form = reactive<GoalFormState>({
  title: '',
  goal_text: '',
  goal_type: 'auto',
  domain: 'machine_learning',
})

watch(
  () => [props.mode, props.projectTitle, props.initialGoalText, props.initialGoalType] as const,
  ([mode, projectTitle, initialGoalText, initialGoalType]) => {
    if (mode !== 'reconfirm') {
      return
    }
    form.title = projectTitle
    form.goal_text = initialGoalText
    form.goal_type = initialGoalType
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

const previewDirty = computed(() => {
  if (!previewState.value) {
    return false
  }

  return (
    previewGoalText.value !== normalizedGoalText.value ||
    previewRequestedGoalType.value !== (requestedGoalType.value ?? null)
  )
})

const canCreate = computed(() => Boolean(previewState.value && selectedCandidateId.value && !previewDirty.value))

const previewButtonLabel = computed(() => (previewState.value && previewDirty.value ? '重新预览候选' : '解析目标候选'))
const submitButtonLabel = computed(() => (props.mode === 'reconfirm' ? '确认并更新项目目标' : '确认并创建项目'))
const reasonMessage = computed(() => {
  if (props.reconfirmReason === 'goal-targets-removed') {
    return '当前项目的已确认目标节点已被图谱审核全部移除，请重新确认学习目标后再继续生成或重规划。'
  }
  return ''
})

function goalTypeLabel(type: string) {
  const map: Record<string, string> = {
    auto: '自动识别',
    domain: '领域型',
    concept: '概念型',
    problem: '问题型',
  }
  return map[type] || type
}

function formatScore(score: number) {
  return score.toFixed(2)
}

function formatExpiresAt(expiresAt: string) {
  const date = new Date(expiresAt)
  if (Number.isNaN(date.getTime())) {
    return expiresAt
  }
  return date.toLocaleString('zh-CN', { hour12: false })
}

async function validateForm() {
  return formRef.value?.validate().catch(() => false)
}

async function handlePreview() {
  const valid = await validateForm()
  if (!valid) {
    return
  }

  previewLoading.value = true
  try {
    const payload = {
      goal_text: normalizedGoalText.value,
      domain: form.domain,
      ...(requestedGoalType.value ? { requested_goal_type: requestedGoalType.value } : {}),
    }
    const preview = props.mode === 'reconfirm' && props.projectId
      ? await projectApi.previewForProject(props.projectId, payload)
      : await projectApi.preview(payload)
    previewState.value = preview
    selectedCandidateId.value = preview.recommended_candidate_id
    previewGoalText.value = normalizedGoalText.value
    previewRequestedGoalType.value = requestedGoalType.value ?? null
  } finally {
    previewLoading.value = false
  }
}

async function handleCreate() {
  const valid = await validateForm()
  if (!valid || !previewState.value || !selectedCandidateId.value || previewDirty.value) {
    return
  }

  createLoading.value = true
  try {
    if (props.mode === 'reconfirm' && props.projectId) {
      const project = await projectApi.confirmGoalResolution(props.projectId, {
        goal_text: normalizedGoalText.value,
        domain: form.domain,
        resolution_session_id: previewState.value.session_id,
        selected_candidate_id: selectedCandidateId.value,
      })
      projectStore.setCurrentProject(project)
      emit('updated', project)
      return
    }

    const project = await projectStore.create({
      title: form.title.trim(),
      goal_text: normalizedGoalText.value,
      domain: form.domain,
      resolution_session_id: previewState.value.session_id,
      selected_candidate_id: selectedCandidateId.value,
    })
    emit('created', project)
  } finally {
    createLoading.value = false
  }
}
</script>

<style scoped>
.type-desc {
  margin-top: 8px;
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

.preview-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
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

.candidate-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.candidate-explanation {
  margin: 12px 0;
  color: var(--el-text-color-regular);
}

.candidate-targets {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.targets-label {
  font-weight: 600;
}
</style>
