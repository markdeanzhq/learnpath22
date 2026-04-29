<template>
  <el-dialog
    :model-value="modelValue"
    title="创建学习项目"
    width="min(920px, 94vw)"
    class="project-create-wizard-dialog"
    :close-on-click-modal="false"
    :before-close="handleBeforeClose"
    destroy-on-close
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <section class="wizard-dialog-intro">
      <div>
        <p class="wizard-eyebrow">创建向导</p>
        <h2>{{ wizardTitle }}</h2>
        <p>{{ wizardDescription }}</p>
      </div>
      <div class="wizard-progress-pills" aria-label="创建向导进度">
        <span :class="{ active: step === 0, done: step > 0 }">目标解析</span>
        <span :class="{ active: step === 1, done: step > 1 }">画像采集</span>
        <span :class="{ active: step === 2 }">生成路径</span>
      </div>
    </section>

    <ProjectWorkflowPanel
      :step="step"
      goal-form-mode="create"
      :current-project-id="currentProjectId"
      :current-project="currentProject"
      reconfirm-reason=""
      :generating-plan="generatingPlan"
      @project-created="$emit('projectCreated', $event)"
      @profile-completed="$emit('profileCompleted')"
      @generate-path="$emit('generatePath')"
      @start-create="$emit('startCreate')"
      @create-form-dirty-changed="$emit('createFormDirtyChanged', $event)"
    />

    <template #footer>
      <div class="wizard-dialog-footer">
        <span>{{ wizardFooterHint }}</span>
        <el-button v-if="step === 0" @click="requestClose">取消创建</el-button>
        <el-button v-else-if="step === 1" @click="$emit('continueLater')">稍后在项目页继续</el-button>
        <el-button v-else @click="requestClose">关闭向导</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import type { Project } from '@/api/modules/project'
import ProjectWorkflowPanel from './ProjectWorkflowPanel.vue'

const props = defineProps<{
  modelValue: boolean
  step: number
  currentProjectId: string
  currentProject: Project | null
  generatingPlan: boolean
  createFormDirty: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [visible: boolean]
  projectCreated: [project: Project]
  profileCompleted: []
  generatePath: []
  startCreate: []
  createFormDirtyChanged: [dirty: boolean]
  continueLater: []
}>()

const wizardTitle = computed(() => {
  if (props.step === 1) return '继续完成画像采集'
  if (props.step === 2) return '项目已准备好'
  return '先确认学习目标是否可规划'
})

const wizardDescription = computed(() => {
  if (props.step === 1) return '项目已经创建，继续补充基础、偏好和时间预算后，就可以生成个性化学习路径。'
  if (props.step === 2) return '目标和画像都已确认，可以生成阶段化学习路径，也可以关闭向导稍后继续。'
  return '系统会先解析目标覆盖情况；如果需要扩展图谱，会引导你创建待扩展项目并进入 Knowledge 草稿收件箱。'
})

const wizardFooterHint = computed(() => {
  if (props.step === 1) return '画像可以稍后继续，当前项目不会丢失。'
  if (props.step === 2) return '关闭后仍可从项目列表继续生成或查看学习路径。'
  return '创建前不会写入项目；扩展草稿审核仍会跳转到 Knowledge。'
})

const shouldConfirmClose = computed(() => props.step === 1 || (props.step === 0 && props.createFormDirty))
const closeConfirmMessage = computed(() => {
  if (props.step === 1) return '当前项目已创建但画像尚未完成，关闭后仍可在项目页继续填写。是否关闭创建向导？'
  return '当前创建信息尚未提交，关闭后已填写内容和解析结果不会保存。是否关闭创建向导？'
})
const closeConfirmTitle = computed(() => (props.step === 1 ? '关闭创建向导' : '放弃本次创建'))
const closeConfirmButtonText = computed(() => (props.step === 1 ? '关闭向导' : '放弃创建'))

async function confirmCloseIfNeeded() {
  if (!shouldConfirmClose.value) {
    return true
  }

  try {
    await ElMessageBox.confirm(closeConfirmMessage.value, closeConfirmTitle.value, {
      type: 'warning',
      confirmButtonText: closeConfirmButtonText.value,
      cancelButtonText: '继续编辑',
    })
    return true
  } catch {
    return false
  }
}

async function requestClose() {
  if (await confirmCloseIfNeeded()) {
    emit('update:modelValue', false)
  }
}

async function handleBeforeClose(done: () => void) {
  if (await confirmCloseIfNeeded()) {
    done()
  }
}
</script>

<style scoped>
:deep(.project-create-wizard-dialog) {
  border-radius: 18px;
  overflow: hidden;
}

:deep(.project-create-wizard-dialog .el-dialog__body) {
  max-height: 72vh;
  overflow: auto;
  padding-top: 0;
}

.wizard-dialog-intro {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
  margin-bottom: 16px;
  padding: 18px;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 14px;
  background: linear-gradient(135deg, var(--el-color-primary-light-9), var(--el-fill-color-blank));
}

.wizard-eyebrow {
  margin: 0 0 6px;
  color: var(--el-color-primary);
  font-size: 13px;
  font-weight: 700;
}

.wizard-dialog-intro h2 {
  margin: 0;
  font-size: 20px;
}

.wizard-dialog-intro p:last-child {
  max-width: 560px;
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}

.wizard-progress-pills {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.wizard-progress-pills span {
  padding: 7px 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 999px;
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.wizard-progress-pills span.active {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
  font-weight: 700;
}

.wizard-progress-pills span.done {
  border-color: var(--el-color-success-light-5);
  color: var(--el-color-success);
}

.wizard-dialog-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.wizard-dialog-footer span {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

@media (max-width: 768px) {
  :deep(.project-create-wizard-dialog) {
    width: 100vw !important;
    min-height: 100vh;
    margin: 0 !important;
    border-radius: 0;
  }

  :deep(.project-create-wizard-dialog .el-dialog__body) {
    max-height: calc(100vh - 150px);
  }

  .wizard-dialog-intro,
  .wizard-dialog-footer {
    flex-direction: column;
    align-items: flex-start;
  }

  .wizard-progress-pills {
    justify-content: flex-start;
  }
}
</style>
