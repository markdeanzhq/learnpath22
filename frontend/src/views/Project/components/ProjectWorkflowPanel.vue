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
    />

    <ProfileQuestionnaire
      v-else-if="step === 1 && currentProjectId"
      :project-id="currentProjectId"
      @completed="$emit('profileCompleted')"
    />

    <div v-else-if="step === 2" class="complete-section">
      <el-result icon="success" title="项目创建成功" sub-title="画像已采集完毕，可以生成学习路径了">
        <template #extra>
          <el-button type="primary" :loading="generatingPlan" @click="$emit('generatePath')">
            生成学习路径
          </el-button>
        </template>
      </el-result>
    </div>

    <div v-else-if="step === -1" class="welcome-section">
      <el-empty description="选择左侧已有项目或点击「新建」开始">
        <template #image>
          <el-icon :size="60" color="#409EFF"><Document /></el-icon>
        </template>
      </el-empty>
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
  text-align: center;
  padding: 40px 0;
}

.welcome-section {
  padding: 40px 0;
}
</style>
