<template>
  <div class="page-container">
    <el-row :gutter="20">
      <!-- 左侧：项目列表 -->
      <el-col :span="9">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>我的项目</span>
              <div class="header-actions">
                <el-button size="small" @click="router.push('/search')">搜索资料</el-button>
                <el-button type="primary" size="small" :icon="Plus" @click="startCreate">新建</el-button>
              </div>
            </div>
          </template>
          <el-table
            :data="projectStore.projects"
            v-loading="projectStore.loading || deletingProjectId !== ''"
            empty-text="暂无项目"
            @row-click="handleRowClick"
            highlight-current-row
            style="cursor: pointer"
          >
            <el-table-column prop="title" label="标题" />
            <el-table-column prop="goal_type" label="类型" width="80">
              <template #default="{ row }">
                <el-tag size="small">{{ goalTypeLabel(row.goal_type) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="row.status === 'completed' ? 'success' : 'info'" size="small">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="90" align="center">
              <template #default="{ row }">
                <el-button
                  type="danger"
                  link
                  :loading="deletingProjectId === row.id"
                  @click.stop="handleDelete(row)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- 右侧：创建/问卷流程 -->
      <el-col :span="15">
        <el-card shadow="never">
          <el-steps :active="step" align-center finish-status="success" style="margin-bottom: 30px">
            <el-step title="创建项目" />
            <el-step title="画像采集" />
            <el-step title="完成" />
          </el-steps>

          <!-- Step 0: 创建项目 -->
          <GoalForm v-if="step === 0" @created="onProjectCreated" />

          <!-- Step 1: 画像采集 -->
          <ProfileQuestionnaire
            v-else-if="step === 1 && currentProjectId"
            :project-id="currentProjectId"
            @completed="onProfileCompleted"
          />

          <!-- Step 2: 完成 -->
          <div v-else-if="step === 2" class="complete-section">
            <el-result icon="success" title="项目创建成功" sub-title="画像已采集完毕，可以生成学习路径了">
              <template #extra>
                <el-button type="primary" @click="goToPath" :loading="generatingPlan">
                  生成学习路径
                </el-button>
              </template>
            </el-result>
          </div>

          <!-- 未开始创建时的提示 -->
          <div v-else-if="step === -1" class="welcome-section">
            <el-empty description="选择左侧已有项目或点击「新建」开始">
              <template #image>
                <el-icon :size="60" color="#409EFF"><Document /></el-icon>
              </template>
            </el-empty>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Document } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import { usePlanStore } from '@/stores/plan'
import { useTrackingStore } from '@/stores/tracking'
import type { Project } from '@/api/modules/project'
import GoalForm from './components/GoalForm.vue'
import ProfileQuestionnaire from './components/ProfileQuestionnaire.vue'

const router = useRouter()
const projectStore = useProjectStore()
const planStore = usePlanStore()
const trackingStore = useTrackingStore()

const step = ref(-1)
const currentProjectId = ref('')
const generatingPlan = ref(false)
const deletingProjectId = ref('')

onMounted(() => {
  projectStore.loadList()
})

function startCreate() {
  step.value = 0
  currentProjectId.value = ''
}

function onProjectCreated(project: Project) {
  currentProjectId.value = project.id
  step.value = 1
  projectStore.loadList()
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

function goalTypeLabel(type: string) {
  const map: Record<string, string> = { domain: '领域', concept: '概念', problem: '问题' }
  return map[type] || type
}
</script>

<style scoped>
.page-container { padding: 20px; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.complete-section { text-align: center; padding: 40px 0; }
.welcome-section { padding: 40px 0; }

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

  .card-header {
    gap: 8px;
    flex-wrap: wrap;
  }
}
</style>