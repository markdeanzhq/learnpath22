<template>
  <div class="page-container">
    <el-row :gutter="20">
      <!-- 左侧：项目列表 -->
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

      <!-- 右侧：创建/问卷流程 -->
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
        />
      </el-col>
    </el-row>
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

onMounted(() => {
  projectStore.loadList()
})

watch(
  () => [route.query.mode, route.query.projectId, route.query.reason] as const,
  ([mode, projectId, reason]) => {
    if (mode !== 'reconfirm' || typeof projectId !== 'string') {
      return
    }
    currentProjectId.value = projectId
    goalFormMode.value = 'reconfirm'
    reconfirmReason.value = typeof reason === 'string' ? reason : ''
    step.value = 0
  },
  { immediate: true },
)

function startCreate() {
  step.value = 0
  currentProjectId.value = ''
  goalFormMode.value = 'create'
  reconfirmReason.value = ''
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
.page-container { padding: 20px; }

@media (max-width: 768px) {
  .page-container {
    padding: 12px;
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