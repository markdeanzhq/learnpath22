<template>
  <el-card shadow="never">
    <el-steps :active="step" align-center finish-status="success" class="workflow-steps">
      <el-step title="创建项目" />
      <el-step title="画像采集" />
      <el-step title="完成" />
    </el-steps>

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
import type { GoalTypeSelection, Project } from '@/api/modules/project'
import GoalForm from './GoalForm.vue'
import ProfileQuestionnaire from './ProfileQuestionnaire.vue'

const props = defineProps<{
  step: number
  goalFormMode: 'create' | 'reconfirm'
  currentProjectId: string
  currentProject: Project | null
  reconfirmReason: string
  generatingPlan: boolean
}>()

defineEmits<{
  projectCreated: [project: Project]
  goalResolutionUpdated: [project: Project]
  profileCompleted: []
  generatePath: []
  startCreate: []
  createFormDirtyChanged: [dirty: boolean]
}>()

const currentProjectGoalType = computed<GoalTypeSelection>(() => {
  const goalType = props.currentProject?.goal_type
  return goalType === 'domain' || goalType === 'concept' || goalType === 'problem' ? goalType : 'auto'
})
</script>

<style scoped>
.workflow-steps {
  margin-bottom: 30px;
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

@media (max-width: 768px) {
  .complete-summary {
    grid-template-columns: 1fr;
  }
}
</style>
