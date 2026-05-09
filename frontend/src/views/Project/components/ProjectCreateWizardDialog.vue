<template>
  <el-dialog
    :model-value="modelValue"
    title="创建学习项目"
    width="min(1240px, 98vw)"
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
        <span v-for="item in wizardSteps" :key="item.key" :class="{ active: step === item.index, done: step > item.index }">
          {{ item.label }}
        </span>
      </div>
    </section>

    <section class="wizard-body-shell">
      <aside class="wizard-step-rail" aria-label="创建步骤说明">
        <button
          v-for="item in wizardSteps"
          :key="item.key"
          type="button"
          class="wizard-step-card"
          :class="{ active: step === item.index, done: step > item.index }"
        >
          <span>{{ item.label }}</span>
          <strong>{{ item.title }}</strong>
          <small>{{ item.description }}</small>
        </button>
      </aside>

      <main class="wizard-main-panel">
        <ProjectWorkflowPanel
          :step="step"
          goal-form-mode="create"
          :current-project-id="currentProjectId"
          :current-project="currentProject"
          reconfirm-reason=""
          :generating-plan="generatingPlan"
          variant="wizard"
          hide-steps
          @project-created="$emit('projectCreated', $event)"
          @profile-completed="$emit('profileCompleted')"
          @generate-path="$emit('generatePath')"
          @start-create="$emit('startCreate')"
          @create-form-dirty-changed="$emit('createFormDirtyChanged', $event)"
        />
      </main>

      <aside class="wizard-helper-panel" aria-label="当前步骤提示">
        <p class="wizard-eyebrow">当前重点</p>
        <h3>{{ currentStepGuide.title }}</h3>
        <p>{{ currentStepGuide.description }}</p>
        <div class="wizard-helper-list">
          <article v-for="hint in currentStepGuide.hints" :key="hint">
            {{ hint }}
          </article>
        </div>
      </aside>
    </section>

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

const wizardSteps = [
  {
    key: 'goal',
    index: 0,
    label: '目标解析',
    title: '先让系统理解目标',
    description: '输入自然语言目标，确认系统理解和可规划范围。',
    hints: ['先写真实学习意图，不必套模板。', '解析后会切换到结果确认页。', '确认候选、澄清或扩展草稿都不会绕过正式图谱边界。'],
  },
  {
    key: 'profile',
    index: 1,
    label: '画像采集',
    title: '补充学习者画像',
    description: '确认数学、编程、机器学习基础、偏好和时间预算。',
    hints: ['画像影响排序、补强和预算提示。', '项目已创建，稍后继续也不会丢失。', '不需要一次填出完美答案。'],
  },
  {
    key: 'path',
    index: 2,
    label: '生成路径',
    title: '生成可解释路径',
    description: '根据目标、画像和知识图谱生成阶段化学习路径。',
    hints: ['正式路径只使用可审查图谱内容。', '生成后可查看解释和进度页。', '之后仍可重规划。'],
  },
]
const currentStepGuide = computed(() => wizardSteps.find((item) => item.index === props.step) ?? wizardSteps[0])

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
  display: flex;
  max-height: min(86vh, 840px);
  flex-direction: column;
  border-radius: 18px;
  overflow: hidden;
}

:deep(.project-create-wizard-dialog .el-dialog__body) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
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

.wizard-body-shell {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr) 240px;
  gap: 14px;
  min-height: 0;
  height: calc(min(86vh, 840px) - 196px);
}

.wizard-step-rail,
.wizard-main-panel,
.wizard-helper-panel {
  min-height: 0;
  overflow: auto;
}

.wizard-step-rail {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.wizard-step-card {
  display: grid;
  gap: 5px;
  width: 100%;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
  text-align: left;
  cursor: default;
}

.wizard-step-card.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  box-shadow: 0 8px 18px rgb(64 158 255 / 10%);
}

.wizard-step-card.done {
  border-color: var(--el-color-success-light-5);
}

.wizard-step-card span,
.wizard-step-card small {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.wizard-step-card strong {
  color: var(--el-text-color-primary);
  font-size: 14px;
}

.wizard-main-panel {
  padding-right: 2px;
}

.wizard-helper-panel {
  padding: 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 14px;
  background: linear-gradient(135deg, var(--el-fill-color-light), var(--el-fill-color-blank));
}

.wizard-helper-panel h3 {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 17px;
}

.wizard-helper-panel p:not(.wizard-eyebrow) {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.wizard-helper-list {
  display: grid;
  gap: 8px;
  margin-top: 14px;
}

.wizard-helper-list article {
  padding: 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.6;
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
    overflow: auto;
  }

  .wizard-body-shell {
    grid-template-columns: 1fr;
    height: auto;
  }

  .wizard-step-rail {
    display: none;
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
