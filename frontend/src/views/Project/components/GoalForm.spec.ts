import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import GoalForm from './GoalForm.vue'

const { createMock, previewMock, previewForProjectMock, confirmGoalResolutionMock, setCurrentProjectMock } = vi.hoisted(() => ({
  createMock: vi.fn(),
  previewMock: vi.fn(),
  previewForProjectMock: vi.fn(),
  confirmGoalResolutionMock: vi.fn(),
  setCurrentProjectMock: vi.fn(),
}))

vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({
    create: createMock,
    setCurrentProject: setCurrentProjectMock,
  }),
}))

vi.mock('@/api/modules/project', async () => {
  const actual = await vi.importActual<any>('@/api/modules/project')
  return {
    ...actual,
    projectApi: {
      ...actual.projectApi,
      preview: previewMock,
      previewForProject: previewForProjectMock,
      confirmGoalResolution: confirmGoalResolutionMock,
    },
  }
})

const formStub = defineComponent({
  setup(_, { slots, expose }) {
    expose({
      validate: vi.fn().mockResolvedValue(true),
    })

    return () => h('form', slots.default?.())
  },
})

const formItemStub = defineComponent({
  props: {
    label: {
      type: String,
      default: '',
    },
  },
  template: '<div><label>{{ label }}</label><slot /></div>',
})

const inputStub = defineComponent({
  props: {
    modelValue: {
      type: String,
      default: '',
    },
    placeholder: {
      type: String,
      default: '',
    },
    type: {
      type: String,
      default: 'text',
    },
  },
  emits: ['update:modelValue'],
  template: `
    <textarea
      v-if="type === 'textarea'"
      :value="modelValue"
      :placeholder="placeholder"
      @input="$emit('update:modelValue', $event.target.value)"
    />
    <input
      v-else
      :value="modelValue"
      :placeholder="placeholder"
      @input="$emit('update:modelValue', $event.target.value)"
    />
  `,
})

const buttonStub = defineComponent({
  props: {
    disabled: {
      type: Boolean,
      default: false,
    },
    loading: {
      type: Boolean,
      default: false,
    },
  },
  emits: ['click'],
  template: '<button :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
})

const alertStub = defineComponent({
  props: {
    title: {
      type: String,
      default: '',
    },
  },
  template: '<div><strong>{{ title }}</strong><slot /></div>',
})

const radioStub = defineComponent({
  template: '<div><slot /></div>',
})

const slotStub = (tag: string) => defineComponent({
  template: `<${tag}><slot /></${tag}>`,
})

function mountGoalForm(props: Record<string, unknown> = {}) {
  return mount(GoalForm, {
    props,
    global: {
      stubs: {
        ElForm: formStub,
        ElFormItem: formItemStub,
        ElInput: inputStub,
        ElRadioGroup: slotStub('div'),
        ElRadioButton: radioStub,
        ElRadio: radioStub,
        ElButton: buttonStub,
        ElText: slotStub('span'),
        ElAlert: alertStub,
        ElTag: slotStub('span'),
        ElCard: slotStub('section'),
        ElDivider: slotStub('hr'),
      },
    },
  })
}

function findButtonByText(wrapper: VueWrapper<any>, text: string) {
  const matched = wrapper
    .findAll('button')
    .find((button) => button.text().includes(text))

  if (!matched) {
    throw new Error(`Button not found: ${text}`)
  }

  return matched
}

const previewResponse = {
  session_id: 'session-001',
  expires_at: '2026-04-23T09:00:00Z',
  auto_detected_goal_type: 'domain',
  effective_goal_type: 'domain',
  recommended_candidate_id: 'cand-001',
  candidates: [
    {
      candidate_id: 'cand-001',
      goal_type: 'domain',
      target_node_ids: ['ml_c09', 'ml_d08'],
      mode: 'steady',
      description: '系统学习机器学习基础',
      template_id: 'domain_ml_full',
      resolve_source: 'template',
      source_breakdown: { template: 0.9, lexical: 0.4, llm: 0 },
      score: 0.86,
      score_breakdown: { final_score: 0.86 },
      explanation: '推荐学习完整机器学习主干。',
      warnings: [],
    },
    {
      candidate_id: 'cand-002',
      goal_type: 'concept',
      target_node_ids: ['ml_c09'],
      mode: 'focus',
      description: '聚焦监督学习基础概念',
      template_id: 'concept_supervised_learning',
      resolve_source: 'lexical',
      source_breakdown: { template: 0.2, lexical: 0.7, llm: 0 },
      score: 0.73,
      score_breakdown: { final_score: 0.73 },
      explanation: '更适合概念聚焦型学习。',
      warnings: [],
    },
  ],
}

afterEach(() => {
  createMock.mockReset()
  previewMock.mockReset()
  previewForProjectMock.mockReset()
  confirmGoalResolutionMock.mockReset()
  setCurrentProjectMock.mockReset()
})

describe('GoalForm', () => {
  it('previews candidates and shows auto-detected type with recommendation explanation', async () => {
    previewMock.mockResolvedValue(previewResponse)
    const wrapper = mountGoalForm()
    const vm = wrapper.vm as any

    vm.form.title = '机器学习基础学习计划'
    vm.form.goal_text = '我想系统学习机器学习基础'
    await nextTick()

    await findButtonByText(wrapper, '解析目标候选').trigger('click')
    await flushPromises()

    expect(previewMock).toHaveBeenCalledWith({
      goal_text: '我想系统学习机器学习基础',
    })
    expect(wrapper.text()).toContain('自动识别')
    expect(wrapper.text()).toContain('推荐学习完整机器学习主干。')
  })

  it('explains single-domain scope and structured empty-candidate errors', () => {
    const wrapper = mountGoalForm()

    expect(wrapper.text()).toContain('当前原型面向机器学习基础单领域')
    expect(wrapper.text()).toContain('reason_code')
    expect(wrapper.text()).toContain('reason_text')
  })

  it('creates project from the selected preview candidate', async () => {
    previewMock.mockResolvedValue(previewResponse)
    createMock.mockResolvedValue({
      id: 'project-001',
      title: '机器学习基础学习计划',
      goal_text: '我想系统学习机器学习基础',
      goal_type: 'domain',
      domain: 'machine_learning',
      status: 'draft',
      created_at: '2026-04-22T09:00:00Z',
    })

    const wrapper = mountGoalForm()
    const vm = wrapper.vm as any

    vm.form.title = '机器学习基础学习计划'
    vm.form.goal_text = '我想系统学习机器学习基础'
    await nextTick()

    await findButtonByText(wrapper, '解析目标候选').trigger('click')
    await flushPromises()
    await findButtonByText(wrapper, '确认并创建项目').trigger('click')
    await flushPromises()

    expect(createMock).toHaveBeenCalledWith({
      title: '机器学习基础学习计划',
      goal_text: '我想系统学习机器学习基础',
      resolution_session_id: 'session-001',
      selected_candidate_id: 'cand-001',
    })
    expect(wrapper.emitted('created')?.[0]?.[0]).toEqual({
      id: 'project-001',
      title: '机器学习基础学习计划',
      goal_text: '我想系统学习机器学习基础',
      goal_type: 'domain',
      domain: 'machine_learning',
      status: 'draft',
      created_at: '2026-04-22T09:00:00Z',
    })
  })

  it('requires re-preview after goal_type changes and reuses the updated goal_type', async () => {
    previewMock.mockResolvedValue(previewResponse)
    const wrapper = mountGoalForm()
    const vm = wrapper.vm as any

    vm.form.title = '机器学习基础学习计划'
    vm.form.goal_text = '我想系统学习机器学习基础'
    await nextTick()

    await findButtonByText(wrapper, '解析目标候选').trigger('click')
    await flushPromises()

    vm.form.goal_type = 'concept'
    await nextTick()

    expect(wrapper.text()).toContain('请重新预览候选')

    await findButtonByText(wrapper, '重新预览候选').trigger('click')
    await flushPromises()

    expect(previewMock).toHaveBeenLastCalledWith({
      goal_text: '我想系统学习机器学习基础',
      requested_goal_type: 'concept',
    })
  })

  it('uses project-level preview in reconfirm mode', async () => {
    previewForProjectMock.mockResolvedValue(previewResponse)
    const wrapper = mountGoalForm({
      mode: 'reconfirm',
      projectId: 'project-001',
      initialGoalText: '我想系统学习机器学习基础',
      initialGoalType: 'domain',
      projectTitle: '机器学习基础学习计划',
      reconfirmReason: 'goal-targets-removed',
    })
    const vm = wrapper.vm as any

    await nextTick()
    expect(vm.form.goal_text).toBe('我想系统学习机器学习基础')
    expect(vm.form.goal_type).toBe('domain')

    await findButtonByText(wrapper, '解析目标候选').trigger('click')
    await flushPromises()

    expect(previewForProjectMock).toHaveBeenCalledWith('project-001', {
      goal_text: '我想系统学习机器学习基础',
      requested_goal_type: 'domain',
    })
  })

  it('confirms updated resolution instead of creating a new project in reconfirm mode', async () => {
    previewForProjectMock.mockResolvedValue(previewResponse)
    confirmGoalResolutionMock.mockResolvedValue({
      id: 'project-001',
      title: '机器学习基础学习计划',
      goal_text: '我想系统学习机器学习基础',
      goal_type: 'domain',
      domain: 'machine_learning',
      status: 'draft',
      created_at: '2026-04-22T09:00:00Z',
      updated_at: '2026-04-22T10:00:00Z',
    })

    const wrapper = mountGoalForm({
      mode: 'reconfirm',
      projectId: 'project-001',
      initialGoalText: '我想系统学习机器学习基础',
      initialGoalType: 'domain',
      projectTitle: '机器学习基础学习计划',
      reconfirmReason: 'goal-targets-removed',
    })

    await findButtonByText(wrapper, '解析目标候选').trigger('click')
    await flushPromises()
    await findButtonByText(wrapper, '确认并更新项目目标').trigger('click')
    await flushPromises()

    expect(confirmGoalResolutionMock).toHaveBeenCalledWith('project-001', {
      goal_text: '我想系统学习机器学习基础',
      resolution_session_id: 'session-001',
      selected_candidate_id: 'cand-001',
    })
    expect(createMock).not.toHaveBeenCalled()
    const updatedEvent = wrapper.emitted('updated')?.[0]?.[0] as { id?: string } | undefined
    expect(updatedEvent?.id).toBe('project-001')
  })
})
