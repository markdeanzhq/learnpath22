<template>
  <section class="overlay-workflow" data-testid="overlay-workflow">
    <div class="overlay-workflow-header">
      <strong>草稿处理流程</strong>
      <span v-if="currentStep">当前阶段：{{ currentStep.title }}</span>
    </div>
    <ol class="overlay-workflow-steps">
      <li
        v-for="(step, index) in steps"
        :key="step.key"
        class="overlay-workflow-step"
        :class="`is-${step.state}`"
      >
        <span class="overlay-workflow-index">{{ index + 1 }}</span>
        <div>
          <div class="overlay-workflow-step-title">
            <strong>{{ step.title }}</strong>
            <el-tag size="small" :type="step.tagType" effect="plain">{{ step.statusLabel }}</el-tag>
          </div>
          <p>{{ step.description }}</p>
        </div>
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import type { OverlayWorkflowStep } from './composables/useOverlayCandidateWorkflow'

defineProps<{
  steps: OverlayWorkflowStep[]
  currentStep: OverlayWorkflowStep | null
}>()
</script>

<style scoped>
.overlay-workflow {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid #d9ecff;
  border-radius: 10px;
  background: #f4faff;
}

.overlay-workflow-header,
.overlay-workflow-step-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.overlay-workflow-header span {
  color: #409eff;
  font-size: 12px;
}

.overlay-workflow-steps {
  display: grid;
  gap: 8px;
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.overlay-workflow-step {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 8px;
  padding: 10px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
}

.overlay-workflow-step.is-current {
  border-color: #f3d19e;
  background: #fdf6ec;
}

.overlay-workflow-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  color: #fff;
  font-size: 12px;
  background: #909399;
}

.overlay-workflow-step.is-done .overlay-workflow-index {
  background: #67c23a;
}

.overlay-workflow-step.is-current .overlay-workflow-index {
  background: #e6a23c;
}

.overlay-workflow-step p {
  margin: 4px 0 0;
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
}
</style>
