<template>
  <div class="page-container">
    <section class="project-hero">
      <div>
        <p class="hero-eyebrow">学习项目启动台</p>
        <h1>创建并管理你的学习路径项目</h1>
        <p class="hero-description">
          先确认学习目标是否能被当前机器学习图谱覆盖，再采集画像参数，最后生成可解释的个性化学习路径。
        </p>
      </div>
      <div class="hero-flow" aria-label="项目创建流程">
        <span>1 描述目标</span>
        <span>2 完成画像</span>
        <span>3 生成路径</span>
      </div>
    </section>

    <el-row :gutter="20" class="project-layout">
      <el-col :span="9">
        <ProjectListPanel
          :projects="projectStore.projects"
          :loading="projectStore.loading"
          :deleting-project-id="deletingProjectId"
          @search="router.push('/search')"
          @create="startCreate"
          @select="handleRowClick"
          @delete="handleDelete"
        />
      </el-col>

      <el-col :span="15">
        <ProjectWorkflowPanel
          :step="step"
          :goal-form-mode="goalFormMode"
          :current-project-id="currentProjectId"
          :current-project="projectStore.currentProject"
          :reconfirm-reason="reconfirmReason"
          :generating-plan="generatingPlan"
          @project-created="onProjectCreated"
          @goal-resolution-updated="onGoalResolutionUpdated"
          @profile-completed="onProfileCompleted"
          @generate-path="goToPath"
          @start-create="startCreate"
        />
      </el-col>
    </el-row>

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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useProjectStore } from '@/stores/project'
import { usePlanStore } from '@/stores/plan'
import { useTrackingStore } from '@/stores/tracking'
import type { Project } from '@/api/modules/project'
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

onMounted(() => {
  projectStore.loadList()
})

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
}

function onGoalResolutionUpdated(project: Project) {
  currentProjectId.value = project.id
  projectStore.setCurrentProject(project)
  goalFormMode.value = 'create'
  reconfirmReason.value = ''
  step.value = -1
  router.replace('/project')
}

function onProfileCompleted() {
  step.value = 2
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
}

function onWizardProfileCompleted() {
  createWizardStep.value = 2
  step.value = 2
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

async function goToPath() {
  if (!currentProjectId.value) return
  generatingPlan.value = true
  try {
    await planStore.generate(currentProjectId.value)
    router.push('/path')
  } catch (e: any) {
    if (e?.response?.status === 409 && e?.response?.data?.error === 'GOAL_TARGETS_REMOVED') {
      router.push({
        path: '/project',
        query: {
          mode: 'reconfirm',
          projectId: currentProjectId.value,
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
    }

    ElMessage.success('项目已永久删除')
  } finally {
    deletingProjectId.value = ''
  }
}

</script>

<style scoped>
.page-container {
  padding: 20px;
}

.project-hero {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-end;
  margin-bottom: 20px;
  padding: 24px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 16px;
  background: linear-gradient(135deg, var(--el-color-primary-light-9), var(--el-fill-color-blank));
}

.hero-eyebrow {
  margin: 0 0 8px;
  color: var(--el-color-primary);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.project-hero h1 {
  margin: 0;
  font-size: 26px;
  line-height: 1.3;
}

.hero-description {
  max-width: 680px;
  margin: 10px 0 0;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}

.hero-flow {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.hero-flow span {
  padding: 8px 12px;
  border-radius: 999px;
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-regular);
  font-size: 13px;
  box-shadow: 0 1px 2px rgb(0 0 0 / 5%);
}

@media (max-width: 768px) {
  .page-container {
    padding: 12px;
  }

  .project-hero {
    flex-direction: column;
    align-items: flex-start;
    padding: 18px;
  }

  .project-hero h1 {
    font-size: 22px;
  }

  .hero-flow {
    justify-content: flex-start;
  }

  :deep(.el-row) {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  :deep(.el-col) {
    max-width: 100%;
    flex: 0 0 100%;
  }
}
</style>