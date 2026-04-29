import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProjectCreateWizardDialog from './ProjectCreateWizardDialog.vue'

const { confirmMock } = vi.hoisted(() => ({
  confirmMock: vi.fn(),
}))

vi.mock('element-plus/es/components/message-box/index', () => ({
  ElMessageBox: {
    confirm: confirmMock,
  },
}))

const dialogStub = defineComponent({
  props: {
    modelValue: { type: Boolean, default: false },
  },
  emits: ['update:modelValue'],
  template: '<section v-if="modelValue" data-testid="wizard-dialog"><slot /><footer><slot name="footer" /></footer></section>',
})

const buttonStub = defineComponent({
  emits: ['click'],
  template: '<button @click="$emit(\'click\')"><slot /></button>',
})

const workflowStub = defineComponent({
  name: 'ProjectWorkflowPanel',
  emits: ['createFormDirtyChanged'],
  template: '<div data-testid="workflow-panel">workflow</div>',
})

function mountDialog(props: Record<string, unknown> = {}) {
  return mount(ProjectCreateWizardDialog, {
    props: {
      modelValue: true,
      step: 0,
      currentProjectId: '',
      currentProject: null,
      generatingPlan: false,
      createFormDirty: false,
      ...props,
    },
    global: {
      stubs: {
        ElDialog: dialogStub,
        ElButton: buttonStub,
        ProjectWorkflowPanel: workflowStub,
      },
    },
  })
}

function findButtonByText(wrapper: ReturnType<typeof mountDialog>, text: string) {
  const matched = wrapper.findAll('button').find((button) => button.text().includes(text))
  if (!matched) {
    throw new Error(`Button not found: ${text}`)
  }
  return matched
}

describe('ProjectCreateWizardDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    confirmMock.mockResolvedValue(undefined)
  })

  it('renders create wizard progress and cleanly closes empty draft', async () => {
    const wrapper = mountDialog()

    expect(wrapper.text()).toContain('先确认学习目标是否可规划')
    expect(wrapper.text()).toContain('目标解析')
    expect(wrapper.text()).toContain('创建前不会写入项目')

    await findButtonByText(wrapper, '取消创建').trigger('click')
    await flushPromises()

    expect(confirmMock).not.toHaveBeenCalled()
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
  })

  it('confirms before closing an unsubmitted dirty draft', async () => {
    const wrapper = mountDialog({ createFormDirty: true })

    await findButtonByText(wrapper, '取消创建').trigger('click')
    await flushPromises()

    expect(confirmMock).toHaveBeenCalledWith(
      '当前创建信息尚未提交，关闭后已填写内容和解析结果不会保存。是否关闭创建向导？',
      '放弃本次创建',
      expect.objectContaining({ confirmButtonText: '放弃创建' }),
    )
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
  })

  it('keeps the wizard open when dirty draft close is cancelled', async () => {
    confirmMock.mockRejectedValueOnce(new Error('cancelled'))
    const wrapper = mountDialog({ createFormDirty: true })

    await findButtonByText(wrapper, '取消创建').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('emits continue later after project creation instead of discarding progress', async () => {
    const wrapper = mountDialog({ step: 1, currentProjectId: 'project-001' })

    expect(wrapper.text()).toContain('继续完成画像采集')
    expect(wrapper.text()).toContain('画像可以稍后继续')

    await findButtonByText(wrapper, '稍后在项目页继续').trigger('click')

    expect(confirmMock).not.toHaveBeenCalled()
    expect(wrapper.emitted('continueLater')).toBeTruthy()
  })
})
