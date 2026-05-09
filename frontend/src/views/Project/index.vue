<template>
  <PageShell
    title="学习项目"
    eyebrow="项目工作台"
    subtitle="先确认学习目标，再完成画像采集，最后生成可解释的学习路径。"
  >
    <template #actions>
      <el-button plain @click="router.push('/search')">项目资料库</el-button>
      <el-button type="primary" @click="startCreate">新建学习项目</el-button>
    </template>

    <template #summary>
      <PageSummaryBar :items="projectSummaryItems">
        <NextActionCard :title="nextActionTitle" :description="nextActionDescription">
          <el-button size="small" type="primary" :disabled="nextActionDisabled" @click="handlePageNextAction">
            {{ nextActionButtonLabel }}
          </el-button>
        </NextActionCard>
      </PageSummaryBar>
    </template>

    <section class="project-workspace">
      <aside class="project-list-pane lp-scroll-panel">
        <ProjectListPanel
          :projects="projectStore.projects"
          :loading="projectStore.loading"
          :deleting-project-id="deletingProjectId"
          @search="router.push('/search')"
          @create="startCreate"
          @select="handleRowClick"
          @delete="handleDelete"
        />
      </aside>

      <main class="project-detail-pane lp-scroll-panel">
        <ProjectWorkflowPanel
          :step="step"
          :goal-form-mode="goalFormMode"
          :current-project-id="workflowProjectId"
          :current-project="projectStore.currentProject"
          :reconfirm-reason="reconfirmReason"
          :generating-plan="generatingPlan"
          :workflow-state="workflowState"
          :workflow-loading="workflowLoading"
          @project-created="onProjectCreated"
          @goal-resolution-updated="onGoalResolutionUpdated"
          @profile-completed="onProfileCompleted"
          @generate-path="goToPath"
          @start-create="startCreate"
          @continue-profile="continueProfile"
          @open-knowledge="openKnowledge"
          @open-path="openPath"
        />
      </main>
    </section>

    <ProjectCreateWizardDialog
      v-model="createWizardVisible"
      :step="createWizardStep"
      :current-project-id="createWizardProjectId"
      :current-project="createWizardProject"
      :generating-plan="generatingPlan"
      :create-form-dirty="createWizardFormDirty"
      @project-created="onWizardProjectCreated"
      @profile-completed="onWizardProfileCompleted"
      @generate-path="goToPath"
      @start-create="startCreate"
      @create-form-dirty-changed="createWizardFormDirty = $event"
      @continue-later="closeCreateWizardAndContinue"
      @update:model-value="handleCreateWizardVisibilityChange"
    />
  </PageShell>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { useProjectStore } from '@/stores/project'
import { usePlanStore } from '@/stores/plan'
import { useTrackingStore } from '@/stores/tracking'
import { projectApi, type Project, type ProjectWorkflowAction, type ProjectWorkflowState } from '@/api/modules/project'
import PageShell from '@/components/Layout/PageShell.vue'
import PageSummaryBar from '@/components/PageSummaryBar.vue'
import NextActionCard from '@/components/NextActionCard.vue'
import ProjectCreateWizardDialog from './components/ProjectCreateWizardDialog.vue'
import ProjectListPanel from './components/ProjectListPanel.vue'
import ProjectWorkflowPanel from './components/ProjectWorkflowPanel.vue'

const router = useRouter()
const route = useRoute()
const projectStore = useProjectStore()
const planStore = usePlanStore()
const trackingStore = useTrackingStore()

const step = ref(-1)
const currentProjectId = ref('')
const generatingPlan = ref(false)
const deletingProjectId = ref('')
const goalFormMode = ref<'create' | 'reconfirm'>('create')
const reconfirmReason = ref('')
const createWizardVisible = ref(false)
const createWizardStep = ref(0)
const createWizardProjectId = ref('')
const createWizardProject = ref<Project | null>(null)
const createWizardFormDirty = ref(false)
const workflowState = ref<ProjectWorkflowState | null>(null)
const workflowLoading = ref(false)
const workflowProjectId = computed(() => currentProjectId.value || projectStore.currentProject?.id || '')
const recommendedAction = computed(() => workflowState.value?.recommended_next_action ?? null)
const overlayCandidateCount = computed(() => {
  const counts = workflowState.value?.overlay?.counts as Record<string, unknown> | undefined
  return Number(counts?.active_nodes || 0) + Number(counts?.active_edges || 0)
})
const pathNodeCount = computed(() => Number(workflowState.value?.path?.node_count || 0))
const trackingCompletionLabel = computed(() => `${Math.round(Number(workflowState.value?.tracking?.completion_rate || 0) * 100)}%`)
const projectSummaryItems = computed<Array<{ label: string; value: string; detail: string; tone: 'primary' | 'success' | 'warning' | 'danger' | 'info' }>>(() => [
  {
    label: '当前项目',
    value: projectStore.currentProject?.title || '未选择',
    detail: projectStore.currentProject?.goal_text || '选择项目后继续学习流程',
    tone: projectStore.currentProject ? 'primary' : 'info',
  },
  {
    label: '扩展候选',
    value: `${overlayCandidateCount.value} 个`,
    detail: '已进入项目图谱工作流的候选内容',
    tone: overlayCandidateCount.value ? 'warning' : 'info',
  },
  {
    label: '路径节点',
    value: `${pathNodeCount.value} 个`,
    detail: pathNodeCount.value ? '当前正式路径覆盖节点' : '生成路径后展示',
    tone: pathNodeCount.value ? 'success' : 'info',
  },
  {
    label: '学习进度',
    value: trackingCompletionLabel.value,
    detail: '根据已记录学习事件计算',
    tone: trackingCompletionLabel.value === '100%' ? 'success' : 'info',
  },
])
const nextActionTitle = computed(() => recommendedAction.value?.label || (projectStore.currentProject ? '查看学习路径' : '创建学习项目'))
const nextActionDescription = computed(() => recommendedAction.value?.description || (projectStore.currentProject ? '已有项目后，可以继续查看路径、画像或图谱状态。' : '先创建一个学习项目，系统会引导你完成目标确认和画像采集。'))
const nextActionButtonLabel = computed(() => recommendedAction.value?.label || (projectStore.currentProject ? '查看路径' : '开始创建'))
const nextActionDisabled = computed(() => recommendedAction.value?.enabled === false)
let workflowRequestId = 0

onMounted(async () => {
  await projectStore.loadList()
  await loadWorkflowState()
})

async function loadWorkflowState(projectId = workflowProjectId.value) {
  if (!projectId) {
    workflowState.value = null
    return
  }

  const requestId = ++workflowRequestId
  workflowLoading.value = true
  try {
    const state = await projectApi.getWorkflowState(projectId)
    if (requestId === workflowRequestId) {
      workflowState.value = state
    }
  } catch {
    if (requestId === workflowRequestId) {
      workflowState.value = null
    }
  } finally {
    if (requestId === workflowRequestId) {
      workflowLoading.value = false
    }
  }
}

watch(
  () => [route.query.mode, route.query.projectId, route.query.reason, route.query.create] as const,
  ([mode, projectId, reason, create]) => {
    if (mode === 'reconfirm' && typeof projectId === 'string') {
      createWizardVisible.value = false
      createWizardFormDirty.value = false
      if (create !== undefined) {
        clearCreateQuery()
      }
      currentProjectId.value = projectId
      goalFormMode.value = 'reconfirm'
      reconfirmReason.value = typeof reason === 'string' ? reason : ''
      step.value = 0
      void loadWorkflowState(projectId)
      return
    }

    if (create === '1' && !createWizardVisible.value) {
      openCreateWizard()
    }
  },
  { immediate: true },
)

function openCreateWizard() {
  createWizardProjectId.value = ''
  createWizardProject.value = null
  createWizardFormDirty.value = false
  createWizardStep.value = 0
  createWizardVisible.value = true
  goalFormMode.value = 'create'
  reconfirmReason.value = ''
}

function startCreate() {
  openCreateWizard()
  if (route.query.create !== '1') {
    router.replace({
      path: '/project',
      query: {
        ...route.query,
        create: '1',
      },
    })
  }
}

function onProjectCreated(project: Project) {
  currentProjectId.value = project.id
  goalFormMode.value = 'create'
  reconfirmReason.value = ''
  step.value = 1
  projectStore.loadList()
  void loadWorkflowState(project.id)
}

function onGoalResolutionUpdated(project: Project) {
  currentProjectId.value = project.id
  projectStore.setCurrentProject(project)
  goalFormMode.value = 'create'
  reconfirmReason.value = ''
  step.value = -1
  router.replace('/project')
  void loadWorkflowState(project.id)
}

function onProfileCompleted() {
  step.value = 2
  void loadWorkflowState()
}

function onWizardProjectCreated(project: Project) {
  currentProjectId.value = project.id
  createWizardProjectId.value = project.id
  createWizardProject.value = project
  createWizardFormDirty.value = false
  goalFormMode.value = 'create'
  reconfirmReason.value = ''
  createWizardStep.value = 1
  step.value = 1
  projectStore.setCurrentProject(project)
  projectStore.loadList()
  void loadWorkflowState(project.id)
}

function onWizardProfileCompleted() {
  createWizardStep.value = 2
  step.value = 2
  void loadWorkflowState()
}

function clearCreateQuery() {
  if (route.query.create !== undefined) {
    const { create, ...query } = route.query
    router.replace({ path: '/project', query })
  }
}

function closeCreateWizard() {
  createWizardVisible.value = false
  createWizardFormDirty.value = false
  clearCreateQuery()
}

function closeCreateWizardAndContinue() {
  if (createWizardProjectId.value) {
    currentProjectId.value = createWizardProjectId.value
    step.value = createWizardStep.value
  }
  closeCreateWizard()
}

function handleCreateWizardVisibilityChange(visible: boolean) {
  createWizardVisible.value = visible
  if (!visible) {
    createWizardFormDirty.value = false
    clearCreateQuery()
  }
}

function continueProfile() {
  const projectId = workflowProjectId.value
  if (!projectId) return
  currentProjectId.value = projectId
  createWizardVisible.value = false
  step.value = 1
}

function openKnowledge(action?: ProjectWorkflowAction) {
  router.push({
    path: '/knowledge',
    query: action?.route_query && Object.keys(action.route_query).length ? action.route_query : { scope: 'project' },
  })
}

function openPath(action?: ProjectWorkflowAction) {
  if (action?.route_query && Object.keys(action.route_query).length) {
    router.push({ path: '/path', query: action.route_query })
    return
  }
  router.push('/path')
}

function handlePageNextAction() {
  const actionPayload = recommendedAction.value
  const action = actionPayload?.action
  if (!projectStore.currentProject && !action) {
    startCreate()
    return
  }
  if (!action || !actionPayload || actionPayload.enabled === false) {
    openPath()
    return
  }
  if (action === 'complete_profile') {
    continueProfile()
    return
  }
  if (action === 'review_overlay' || action === 'fix_overlay') {
    openKnowledge(actionPayload)
    return
  }
  if (action === 'generate_path') {
    void goToPath()
    return
  }
  if (action === 'reconfirm_goal') {
    startCreate()
    return
  }
  openPath(actionPayload)
}

async function goToPath() {
  const projectId = workflowProjectId.value
  if (!projectId) return
  currentProjectId.value = projectId
  generatingPlan.value = true
  try {
    await planStore.generate(projectId)
    void loadWorkflowState(projectId)
    router.push('/path')
  } catch (e: any) {
    if (e?.response?.status === 409 && e?.response?.data?.error === 'GOAL_TARGETS_REMOVED') {
      router.push({
        path: '/project',
        query: {
          mode: 'reconfirm',
          projectId,
          reason: 'goal-targets-removed',
        },
      })
      return
    }
    throw e
  } finally {
    generatingPlan.value = false
  }
}

function handleRowClick(row: Project) {
  currentProjectId.value = row.id
  projectStore.setCurrentProject(row)
  router.push('/path')
}

async function handleDelete(row: Project) {
  try {
    await ElMessageBox.confirm(
      `将永久删除项目「${row.title}」，并同时删除其画像、学习路径、学习跟踪等关联数据。此操作不可恢复，是否继续？`,
      '永久删除项目',
      {
        type: 'warning',
        confirmButtonText: '永久删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }

  deletingProjectId.value = row.id
  try {
    const isCurrentProject = projectStore.currentProject?.id === row.id || currentProjectId.value === row.id
    await projectStore.deleteProject(row.id)

    if (isCurrentProject) {
      projectStore.clearCurrentProject()
      planStore.reset()
      trackingStore.reset()
      step.value = -1
      currentProjectId.value = ''
      workflowState.value = null
    }

    ElMessage.success('项目已永久删除')
  } finally {
    deletingProjectId.value = ''
  }
}

</script>

<style scoped>
.project-workspace {
  display: grid;
  grid-template-columns: minmax(280px, 34%) minmax(0, 1fr);
  gap: var(--lp-space-4);
  height: calc(100vh - var(--lp-header-height) - 228px);
  min-height: 460px;
}

.project-list-pane,
.project-detail-pane {
  min-width: 0;
}

.project-list-pane :deep(.el-card),
.project-detail-pane :deep(.el-card) {
  min-height: 100%;
}

.project-detail-pane :deep(.workflow-steps) {
  margin-bottom: var(--lp-space-4);
}

@media (max-width: 960px) {
  .project-workspace {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 0;
  }

  .project-list-pane,
  .project-detail-pane {
    overflow: visible;
  }
}
</style>