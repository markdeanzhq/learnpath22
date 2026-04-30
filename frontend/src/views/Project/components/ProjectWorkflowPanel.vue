<template>
  <el-card shadow="never">
    <el-steps :active="step" align-center finish-status="success" class="workflow-steps">
      <el-step title="创建项目" />
      <el-step title="画像采集" />
      <el-step title="完成" />
    </el-steps>

    <section v-if="currentProject && workflowState" class="workflow-overview">
      <div class="workflow-overview-header">
        <div>
          <p class="overview-eyebrow">项目工作流总览</p>
          <h3>{{ currentProject.title }}</h3>
          <p>{{ currentProject.goal_text }}</p>
        </div>
        <el-tag :type="statusTagType(recommendedStatus)">
          {{ workflowLoading ? '状态刷新中' : recommendedAction?.label || '等待下一步' }}
        </el-tag>
      </div>

      <div class="workflow-step-grid">
        <article v-for="item in workflowState.steps" :key="item.key" class="workflow-step-card">
          <div class="workflow-step-card-title">
            <strong>{{ item.label }}</strong>
            <el-tag size="small" :type="statusTagType(item.status)">{{ statusLabel(item.status) }}</el-tag>
          </div>
          <p>{{ item.summary }}</p>
        </article>
      </div>

      <div class="workflow-metrics">
        <span>扩展候选 <strong>{{ overlayCandidateCount }}</strong></span>
        <span>路径节点 <strong>{{ pathNodeCount }}</strong></span>
        <span>学习进度 <strong>{{ trackingCompletionLabel }}</strong></span>
      </div>

      <div v-if="recommendedAction" class="workflow-next-action">
        <div>
          <strong>{{ recommendedAction.label }}</strong>
          <p>{{ recommendedAction.description }}</p>
        </div>
        <el-button type="primary" :disabled="recommendedAction.enabled === false" @click="handleRecommendedAction">
          {{ recommendedAction.label }}
        </el-button>
      </div>
    </section>

    <GoalForm
      v-if="step === 0"
      :mode="goalFormMode"
      :project-id="currentProjectId"
      :project-title="currentProject?.title ?? ''"
      :initial-goal-text="currentProject?.goal_text ?? ''"
      :initial-goal-type="goalFormMode === 'reconfirm' ? currentProjectGoalType : 'auto'"
      :reconfirm-reason="reconfirmReason"
      @created="$emit('projectCreated', $event)"
      @updated="$emit('goalResolutionUpdated', $event)"
      @dirty-state-changed="$emit('createFormDirtyChanged', $event)"
    />

    <ProfileQuestionnaire
      v-else-if="step === 1 && currentProjectId"
      :project-id="currentProjectId"
      @completed="$emit('profileCompleted')"
    />

    <div v-else-if="step === 2" class="complete-section">
      <div class="complete-card">
        <el-result icon="success" title="项目已准备好" sub-title="目标和画像都已确认，可以生成可解释学习路径了" />
        <div class="complete-summary">
          <div class="complete-summary-item">
            <span>已确认目标</span>
            <strong>{{ currentProject?.goal_text || '当前学习目标' }}</strong>
          </div>
          <div class="complete-summary-item">
            <span>画像摘要</span>
            <strong>已采集基础、偏好和时间预算</strong>
          </div>
          <div class="complete-summary-item">
            <span>下一步</span>
            <strong>生成阶段化学习路径</strong>
          </div>
        </div>
        <div class="complete-actions">
          <el-button type="primary" size="large" :loading="generatingPlan" @click="$emit('generatePath')">
            生成学习路径
          </el-button>
        </div>
      </div>
    </div>

    <div v-else-if="step === -1" class="welcome-section">
      <div class="welcome-card">
        <el-icon :size="56" color="#409EFF"><Document /></el-icon>
        <p class="welcome-eyebrow">准备开始</p>
        <h2>先描述一个学习目标</h2>
        <p>
          系统会先解析你的目标是否属于机器学习基础范围，再引导你完成画像采集，避免把不确定内容直接写入正式路径。
        </p>
        <div class="welcome-flow">
          <span>目标解析</span>
          <span>画像采集</span>
          <span>路径生成</span>
        </div>
        <el-button type="primary" @click="$emit('startCreate')">开始创建学习项目</el-button>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Document } from '@element-plus/icons-vue'
import type { GoalTypeSelection, Project, ProjectWorkflowState, ProjectWorkflowStepStatus } from '@/api/modules/project'
import GoalForm from './GoalForm.vue'
import ProfileQuestionnaire from './ProfileQuestionnaire.vue'

const props = defineProps<{
  step: number
  goalFormMode: 'create' | 'reconfirm'
  currentProjectId: string
  currentProject: Project | null
  reconfirmReason: string
  generatingPlan: boolean
  workflowState?: ProjectWorkflowState | null
  workflowLoading?: boolean
}>()

const emit = defineEmits<{
  projectCreated: [project: Project]
  goalResolutionUpdated: [project: Project]
  profileCompleted: []
  generatePath: []
  startCreate: []
  createFormDirtyChanged: [dirty: boolean]
  continueProfile: []
  openKnowledge: []
  openPath: []
}>()

const currentProjectGoalType = computed<GoalTypeSelection>(() => {
  const goalType = props.currentProject?.goal_type
  return goalType === 'domain' || goalType === 'concept' || goalType === 'problem' ? goalType : 'auto'
})

const recommendedAction = computed(() => props.workflowState?.recommended_next_action ?? null)
const recommendedStatus = computed<ProjectWorkflowStepStatus>(() => recommendedAction.value?.enabled === false ? 'pending' : 'active')

const overlayCandidateCount = computed(() => {
  const counts = props.workflowState?.overlay?.counts as Record<string, unknown> | undefined
  const activeNodes = Number(counts?.active_nodes || 0)
  const activeEdges = Number(counts?.active_edges || 0)
  return activeNodes + activeEdges
})

const pathNodeCount = computed(() => Number(props.workflowState?.path?.node_count || 0))
const trackingCompletionLabel = computed(() => {
  const rate = Number(props.workflowState?.tracking?.completion_rate || 0)
  return `${Math.round(rate * 100)}%`
})

function statusLabel(status: ProjectWorkflowStepStatus) {
  const labels: Record<ProjectWorkflowStepStatus, string> = {
    pending: '待处理',
    active: '进行中',
    completed: '已完成',
    blocked: '阻塞',
    warning: '需关注',
  }
  return labels[status]
}

function statusTagType(status: ProjectWorkflowStepStatus) {
  if (status === 'completed') return 'success'
  if (status === 'blocked') return 'danger'
  if (status === 'warning') return 'warning'
  if (status === 'active') return 'primary'
  return 'info'
}

function handleRecommendedAction() {
  const action = recommendedAction.value?.action
  if (!action || recommendedAction.value?.enabled === false) return
  if (action === 'complete_profile') {
    emit('continueProfile')
    return
  }
  if (action === 'review_overlay' || action === 'fix_overlay') {
    emit('openKnowledge')
    return
  }
  if (action === 'generate_path') {
    emit('generatePath')
    return
  }
  if (action === 'reconfirm_goal') {
    emit('startCreate')
    return
  }
  emit('openPath')
}
</script>

<style scoped>
.workflow-steps {
  margin-bottom: 30px;
}

.workflow-overview {
  margin-bottom: 24px;
  padding: 18px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 16px;
  background: linear-gradient(135deg, var(--el-fill-color-light), var(--el-fill-color-blank));
}

.workflow-overview-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
}

.overview-eyebrow {
  margin: 0 0 6px;
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
}

.workflow-overview-header h3 {
  margin: 0;
  font-size: 18px;
}

.workflow-overview-header p:last-child {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}

.workflow-step-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}

.workflow-step-card {
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: var(--el-fill-color-blank);
}

.workflow-step-card-title {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}

.workflow-step-card p {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.workflow-metrics {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.workflow-metrics span {
  padding: 7px 10px;
  border-radius: 999px;
  background: var(--el-color-primary-light-9);
  color: var(--el-text-color-regular);
  font-size: 12px;
}

.workflow-next-action {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-top: 14px;
  padding: 12px;
  border-radius: 12px;
  background: var(--el-color-success-light-9);
}

.workflow-next-action p {
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.complete-section {
  padding: 28px 0;
}

.complete-card {
  max-width: 640px;
  margin: 0 auto;
  padding: 8px 24px 28px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 16px;
  background: linear-gradient(135deg, var(--el-color-success-light-9), var(--el-fill-color-blank));
}

.complete-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 0 0 20px;
}

.complete-summary-item {
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: var(--el-fill-color-blank);
  text-align: left;
}

.complete-summary-item span {
  display: block;
  margin-bottom: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.complete-summary-item strong {
  display: -webkit-box;
  color: var(--el-text-color-primary);
  font-size: 14px;
  line-height: 1.5;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.complete-actions {
  text-align: center;
}

.welcome-section {
  padding: 24px 0;
}

.welcome-card {
  max-width: 560px;
  margin: 0 auto;
  padding: 32px 24px;
  text-align: center;
  border: 1px dashed var(--el-border-color);
  border-radius: 16px;
  background: var(--el-fill-color-light);
}

.welcome-eyebrow {
  margin: 12px 0 6px;
  color: var(--el-color-primary);
  font-size: 13px;
  font-weight: 700;
}

.welcome-card h2 {
  margin: 0;
}

.welcome-card p {
  margin: 10px auto 0;
  max-width: 440px;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}

.welcome-flow {
  display: flex;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
  margin: 18px 0;
}

.welcome-flow span {
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-regular);
  font-size: 12px;
}

@media (max-width: 1080px) {
  .workflow-step-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .complete-summary,
  .workflow-step-grid {
    grid-template-columns: 1fr;
  }

  .workflow-overview-header,
  .workflow-next-action {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
