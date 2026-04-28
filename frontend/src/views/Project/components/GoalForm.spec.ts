import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import GoalForm from './GoalForm.vue'

const {
  createMock,
  previewMock,
  previewForProjectMock,
  confirmGoalResolutionMock,
  setCurrentProjectMock,
  pushMock,
} = vi.hoisted(() => ({
  createMock: vi.fn(),
  previewMock: vi.fn(),
  previewForProjectMock: vi.fn(),
  confirmGoalResolutionMock: vi.fn(),
  setCurrentProjectMock: vi.fn(),
  pushMock: vi.fn(),
}))

vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({
    create: createMock,
    setCurrentProject: setCurrentProjectMock,
  }),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
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

function createDeferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve
    reject = nextReject
  })
  return { promise, resolve, reject }
}

const previewResponse = {
  result_type: 'select_candidate',
  coverage_status: 'covered',
  session_id: 'session-001',
  expires_at: '2026-04-23T09:00:00Z',
  auto_detected_goal_type: 'domain',
  effective_goal_type: 'domain',
  recommended_candidate_id: 'cand-001',
  pack_hash: 'pack-hash-001',
  project_graph_hash: 'graph-hash-001',
  audit_trace: {
    trace_type: 'goal_resolution',
    trace_id: 'session-001',
    pack_hash: 'pack-hash-001',
    project_graph_hash: 'graph-hash-001',
  },
  goal_understanding: {
    schema_version: 'v1',
    raw_text: '我想系统学习机器学习基础',
    domain_decision: 'in_domain',
    primary_domain: 'machine_learning',
    ml_relevance: 'core',
    goal_type: 'domain',
    target_concepts: ['机器学习基础'],
    constraints: {},
    preferences: {},
    uncertainties: [],
    clarification_question: null,
    confidence: 0.94,
    evidence: [{ span: '机器学习基础', label: 'supported_domain', reason: '明确属于当前支持的机器学习基础领域' }],
    prompt_version: 'goal-understanding-v1',
    model: 'mock-llm',
    warnings: [],
  },
  goal_frame: {
    schema_version: 'v1',
    raw_text: '我想系统学习机器学习基础',
    domain: 'machine_learning',
    goal_type: 'domain',
    target_concepts: ['机器学习基础'],
    target_node_ids: ['ml_c09', 'ml_d08'],
    constraints: {},
    preferences: {},
    planner_parameters: { explanation_focus: [] },
    uncertainties: [],
    confidence: 0.9,
    sources: [{ source: 'rules', evidence: 'rules_first_goal_frame', confidence: 0.9 }],
  },
  warnings: [],
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
      explanation: 'template 候选，template=0.90 lexical=0.40 llm=0.00 specificity=0.60 penalty=0.00',
      confidence_level: 'high',
      confidence_reason: '命中预设目标模板，并通过当前知识图谱节点校验。',
      user_explanation: '系统较可靠地将你的目标映射到机器学习主干，确认后可用于生成正式学习路径。',
      debug_explanation: 'template 候选，template=0.90 lexical=0.40 llm=0.00 specificity=0.60 penalty=0.00',
      match_signals: [
        { type: 'template', label: '目标模板', strength: 'strong', detail: '命中预设学习目标模板。' },
        { type: 'graph', label: '知识图谱校验', strength: 'medium', detail: '候选来自当前图谱。' },
      ],
      recommended_action: 'confirm',
      is_recommended: true,
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
      explanation: 'lexical 候选，template=0.20 lexical=0.70 llm=0.00 specificity=0.80 penalty=0.00',
      confidence_level: 'medium',
      confidence_reason: '系统找到了可用候选，但匹配依据仍需要你确认是否符合真实目标。',
      user_explanation: '系统找到了一组可能匹配的目标知识点，请确认是否符合你的真实意图。',
      debug_explanation: 'lexical 候选，template=0.20 lexical=0.70 llm=0.00 specificity=0.80 penalty=0.00',
      match_signals: [
        { type: 'lexical', label: '关键词匹配', strength: 'medium', detail: '根据关键词召回。' },
      ],
      recommended_action: 'review',
      is_recommended: false,
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
  pushMock.mockReset()
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
    expect(wrapper.text()).toContain('可以创建学习路径')
    expect(wrapper.text()).toContain('系统理解：你想学习 机器学习基础。')
    expect(wrapper.text()).toContain('边界判断：领域内')
    expect(wrapper.text()).toContain('展示模式')
    expect(wrapper.text()).not.toContain('机器学习相关性：核心相关')
    expect(wrapper.text()).not.toContain('明确属于当前支持的机器学习基础领域')
    expect(wrapper.text()).toContain('推荐下一步')
    expect(wrapper.text()).toContain('当前知识图谱可以较可靠地支持')
    expect(wrapper.text()).toContain('确认学习目标')
    expect(wrapper.text()).toContain('高置信')
    expect(wrapper.text()).toContain('学习方案：系统学习｜系统学习机器学习基础')
    expect(wrapper.text()).toContain('路径将围绕这些内容展开')
    expect(wrapper.text()).toContain('系统较可靠地将你的目标映射到机器学习主干')
    expect(wrapper.text()).not.toContain('命中预设目标模板，并通过当前知识图谱节点校验。')
    expect(wrapper.text()).not.toContain('目标模板：强')
  })

  it('keeps the initial goal input user-friendly and hides technical options by default', () => {
    const wrapper = mountGoalForm()

    expect(wrapper.text()).toContain('用一句自然语言描述想学什么即可')
    expect(wrapper.text()).toContain('高级选项：手动指定目标类型')
    expect(wrapper.text()).not.toContain('reason_code')
    expect(wrapper.text()).not.toContain('reason_text')
  })

  it('creates project when create preview has no project graph hash', async () => {
    previewMock.mockResolvedValue({
      ...previewResponse,
      project_graph_hash: null,
      audit_trace: {
        ...previewResponse.audit_trace,
        project_graph_hash: null,
      },
    })
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
    expect(wrapper.text()).not.toContain('project_graph_hash：新建项目暂不适用')
    expect(wrapper.text()).not.toContain('知识包哈希一致')
    expect(wrapper.text()).not.toContain('当前预览不可继续写入')
    expect(wrapper.text()).toContain('确认这个选择')
    expect(wrapper.text()).toContain('确认后，系统会把所选学习方案作为正式路径目标。')

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

  it('requires explicit partial acceptance before creating a partial project', async () => {
    previewMock.mockResolvedValue({
      ...previewResponse,
      result_type: 'confirm_partial',
      coverage_status: 'partial',
      goal_frame: {
        ...previewResponse.goal_frame,
        raw_text: '我想学习机器学习和深度学习',
      },
      covered_target_node_ids: ['ml_c09'],
      missing_concepts: ['深度学习'],
      available_actions: [
        {
          action: 'use_existing_graph',
          label: '按已有图谱生成路径',
          description: '只使用当前已覆盖的机器学习基础内容，缺失概念会写入审计记录。',
          risk_level: 'low',
          requires_review: false,
          enabled: true,
        },
        {
          action: 'create_extension_draft',
          label: '生成扩展草稿并审核',
          description: '由 LLM/规则辅助补充缺失概念草稿，用户审核后才可用于增强路径。',
          risk_level: 'medium',
          requires_review: true,
          enabled: true,
        },
        {
          action: 'rewrite_goal',
          label: '改写学习目标',
          description: '把目标收敛到当前机器学习基础图谱已覆盖的概念后重新解析。',
          risk_level: 'low',
          requires_review: false,
          enabled: true,
        },
      ],
      candidates: [previewResponse.candidates[0]],
    })
    createMock.mockResolvedValue({
      id: 'project-partial',
      title: '部分覆盖计划',
      goal_text: '我想学习机器学习和深度学习',
      goal_type: 'domain',
      domain: 'machine_learning',
      status: 'draft',
      created_at: '2026-04-22T09:00:00Z',
    })
    const wrapper = mountGoalForm()
    const vm = wrapper.vm as any

    vm.form.title = '部分覆盖计划'
    vm.form.goal_text = '我想学习机器学习和深度学习'
    await nextTick()

    await findButtonByText(wrapper, '解析目标候选').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('你可以怎么继续')
    expect(wrapper.text()).toContain('按已有图谱生成路径')
    expect(wrapper.text()).toContain('生成扩展草稿并审核')
    expect(wrapper.text()).toContain('需要先审核草稿；审核前不会进入正式路径。')
    expect(wrapper.text()).toContain('确认这个选择')
    expect(wrapper.text()).toContain('请先勾选接受部分覆盖，系统才会创建或更新项目。')

    await findButtonByText(wrapper, '选择已有图谱方案').trigger('click')
    await nextTick()
    expect(wrapper.text()).toContain('确认后将只使用已覆盖部分生成路径，缺失概念会进入审计记录。')

    vm.acceptPartial = false
    await nextTick()
    await findButtonByText(wrapper, '接受部分覆盖并创建项目').trigger('click')
    await flushPromises()

    expect(createMock).not.toHaveBeenCalled()

    vm.acceptPartial = true
    await nextTick()
    expect(wrapper.text()).toContain('确认后将只使用已覆盖部分生成路径，缺失概念会进入审计记录。')

    await findButtonByText(wrapper, '接受部分覆盖并创建项目').trigger('click')
    await flushPromises()

    expect(createMock).toHaveBeenCalledWith({
      title: '部分覆盖计划',
      goal_text: '我想学习机器学习和深度学习',
      resolution_session_id: 'session-001',
      selected_candidate_id: 'cand-001',
      accept_partial: true,
    })
  })

  it('does not auto-select low-confidence lexical candidates', async () => {
    previewMock.mockResolvedValue({
      ...previewResponse,
      recommended_candidate_id: 'cand-low',
      candidates: [
        {
          ...previewResponse.candidates[1],
          candidate_id: 'cand-low',
          description: '学习机器学习的数学基础',
          score: 0.22,
          confidence_level: 'low',
          confidence_reason: '主要来自关键词匹配，未命中稳定目标模板或 LLM 语义确认，请谨慎确认。',
          user_explanation: '系统仅找到弱匹配候选，建议先澄清或改写目标后再创建项目。',
          debug_explanation: 'jieba 候选，template=0.00 lexical=0.60 llm=0.00 specificity=0.60 penalty=0.05',
          match_signals: [{ type: 'lexical', label: '关键词匹配', strength: 'medium', detail: '根据关键词召回。' }],
          recommended_action: 'clarify',
          is_recommended: false,
        },
      ],
    })
    const wrapper = mountGoalForm()
    const vm = wrapper.vm as any

    vm.form.title = '数学基础计划'
    vm.form.goal_text = '学习机器学习的数学基础'
    await nextTick()

    await findButtonByText(wrapper, '解析目标候选').trigger('click')
    await flushPromises()

    expect(vm.selectedCandidateId).toBe('')
    expect(vm.canCreate).toBe(false)
    expect(wrapper.text()).toContain('请谨慎确认系统理解')
    expect(wrapper.text()).toContain('当前只找到弱匹配候选')
    expect(wrapper.text()).toContain('低置信')
    expect(wrapper.text()).toContain('建议澄清')
    expect(wrapper.text()).toContain('系统仅找到弱匹配候选')
    expect(wrapper.text()).toContain('请先选择一个学习方案，再确认创建。')
  })

  it('clears unsafe preview state after stale preview errors', async () => {
    previewMock.mockResolvedValueOnce(previewResponse)
    previewMock.mockRejectedValueOnce({
      response: { data: { error: 'STALE_RESOLUTION_SESSION' } },
    })
    const wrapper = mountGoalForm()
    const vm = wrapper.vm as any

    vm.form.title = '机器学习基础学习计划'
    vm.form.goal_text = '我想系统学习机器学习基础'
    await nextTick()

    await findButtonByText(wrapper, '解析目标候选').trigger('click')
    await flushPromises()
    expect(vm.previewState).not.toBeNull()

    await findButtonByText(wrapper, '解析目标候选').trigger('click')
    await flushPromises()

    expect(vm.previewState).toBeNull()
    expect(wrapper.text()).not.toContain('确认并创建项目')
  })

  it('ignores duplicate preview and submit clicks while requests are in flight', async () => {
    const previewDeferred = createDeferred<any>()
    previewMock.mockReturnValue(previewDeferred.promise)
    const wrapper = mountGoalForm()
    const vm = wrapper.vm as any

    vm.form.title = '机器学习基础学习计划'
    vm.form.goal_text = '我想系统学习机器学习基础'
    await nextTick()

    const firstPreview = vm.handlePreview()
    const secondPreview = vm.handlePreview()
    await flushPromises()

    expect(previewMock).toHaveBeenCalledTimes(1)
    previewDeferred.resolve(previewResponse)
    await firstPreview
    await secondPreview
    await flushPromises()

    const createDeferredRequest = createDeferred<any>()
    createMock.mockReturnValue(createDeferredRequest.promise)
    const firstCreate = vm.handleCreate()
    const secondCreate = vm.handleCreate()
    await flushPromises()

    expect(createMock).toHaveBeenCalledTimes(1)
    createDeferredRequest.resolve({
      id: 'project-001',
      title: '机器学习基础学习计划',
      goal_text: '我想系统学习机器学习基础',
      goal_type: 'domain',
      domain: 'machine_learning',
      status: 'draft',
      created_at: '2026-04-22T09:00:00Z',
    })
    await firstCreate
    await secondCreate
    await flushPromises()
  })

  it('shows out-of-domain semantic rejection without allowing project creation', async () => {
    previewMock.mockResolvedValue({
      ...previewResponse,
      result_type: 'boundary_reject',
      coverage_status: 'out_of_domain',
      goal_understanding: {
        ...previewResponse.goal_understanding,
        raw_text: '想要学习基础物理',
        domain_decision: 'out_of_domain',
        primary_domain: 'physics',
        ml_relevance: 'none',
        target_concepts: ['基础物理'],
        confidence: 0.93,
        evidence: [{ span: '基础物理', label: 'primary_domain', reason: '目标主体是物理学基础' }],
      },
      goal_frame: {
        ...previewResponse.goal_frame,
        raw_text: '想要学习基础物理',
        target_concepts: ['基础物理'],
      },
      reason_code: 'OUT_OF_SUPPORTED_DOMAIN',
      reason_text: '当前原型仅支持机器学习基础领域。',
      rewrite_suggestions: ['如果想学习机器学习，请改写为“系统学习机器学习基础”。'],
      candidates: [],
    })
    const wrapper = mountGoalForm()
    const vm = wrapper.vm as any

    vm.form.title = '基础物理学习计划'
    vm.form.goal_text = '想要学习基础物理'
    await nextTick()

    await findButtonByText(wrapper, '解析目标候选').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('边界判断：领域外')
    expect(wrapper.text()).not.toContain('主领域：physics')
    expect(wrapper.text()).not.toContain('目标主体是物理学基础')
    expect(wrapper.text()).toContain('暂时不能创建这个目标')
    expect(wrapper.text()).not.toContain('技术详情')
    expect(wrapper.text()).not.toContain('OUT_OF_SUPPORTED_DOMAIN')
    expect(wrapper.text()).not.toContain('确认并创建项目')
    expect(createMock).not.toHaveBeenCalled()
  })

  it('shows cross-domain clarification and prevents direct creation', async () => {
    previewMock.mockResolvedValue({
      ...previewResponse,
      result_type: 'answer_clarification',
      coverage_status: 'cross_domain',
      clarification_session_id: 'clarify-cross',
      turn_count: 0,
      max_turns: 3,
      goal_understanding: {
        ...previewResponse.goal_understanding,
        raw_text: '学习新能源预测中的机器学习',
        domain_decision: 'cross_domain',
        primary_domain: 'new_energy',
        ml_relevance: 'application',
        target_concepts: ['新能源预测', '机器学习'],
        clarification_question: '是否只按机器学习基础部分创建路径？',
      },
      questions: [
        {
          question_id: 'confirm_ml_scope',
          field: 'domain_scope',
          prompt: '当前系统只覆盖机器学习基础，是否按机器学习部分创建路径？',
          options: [{ option_id: 'accept_ml_scope', label: '是，仅学习机器学习基础部分', value: {} }],
          allow_free_text: true,
        },
      ],
      candidates: [],
    })
    const wrapper = mountGoalForm()
    const vm = wrapper.vm as any

    vm.form.title = '新能源预测学习计划'
    vm.form.goal_text = '学习新能源预测中的机器学习'
    await nextTick()

    await findButtonByText(wrapper, '解析目标候选').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('跨领域目标')
    expect(wrapper.text()).toContain('边界判断：跨领域')
    expect(wrapper.text()).not.toContain('机器学习相关性：应用相关')
    expect(wrapper.text()).toContain('请选择继续方式')
    expect(wrapper.text()).toContain('当前系统只覆盖机器学习基础')
    expect(wrapper.text()).not.toContain('确认并创建项目')
  })

  it('links in-domain-uncovered project preview to Knowledge without creating a draft on open', async () => {
    previewForProjectMock.mockResolvedValue({
      ...previewResponse,
      result_type: 'review_extension_draft',
      coverage_status: 'in_domain_uncovered',
      session_id: 'session-draft',
      expires_at: '2026-04-23T09:00:00Z',
      missing_concepts: ['深度学习入门'],
      draft_entry: { action: 'create_project_overlay_draft', requires_explicit_request: true },
      available_actions: [
        {
          action: 'create_extension_draft',
          label: '生成扩展草稿并审核',
          description: '由 LLM/规则辅助补充缺失概念草稿，用户审核后才可用于增强路径。',
          risk_level: 'medium',
          requires_review: true,
          enabled: true,
        },
        {
          action: 'rewrite_goal',
          label: '改写学习目标',
          description: '把目标收敛到当前机器学习基础图谱已覆盖的概念后重新解析。',
          risk_level: 'low',
          requires_review: false,
          enabled: true,
        },
      ],
      candidates: [],
    })
    const wrapper = mountGoalForm({
      mode: 'reconfirm',
      projectId: 'project-001',
      initialGoalText: '深度学习入门',
      initialGoalType: 'concept',
      projectTitle: '机器学习基础学习计划',
    })

    await findButtonByText(wrapper, '解析目标候选').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('生成可审核的扩展草稿')
    expect(wrapper.text()).toContain('你可以怎么继续')
    expect(wrapper.text()).toContain('生成扩展草稿并审核')
    expect(wrapper.text()).toContain('需要先审核草稿；审核前不会进入正式路径。')
    expect(wrapper.text()).toContain('为什么不能直接生成路径？')
    expect(wrapper.text()).toContain('待补充概念：')
    await findButtonByText(wrapper, '预览扩展草稿').trigger('click')

    expect(pushMock).toHaveBeenCalledWith({
      name: 'Knowledge',
      query: {
        scope: 'project',
        goalDraft: '1',
        resolutionSessionId: 'session-draft',
      },
    })
  })

  it('creates an extension-review project from an uncovered goal preview', async () => {
    previewMock.mockResolvedValue({
      ...previewResponse,
      result_type: 'review_extension_draft',
      coverage_status: 'in_domain_uncovered',
      session_id: 'session-new-draft',
      expires_at: '2026-04-23T09:00:00Z',
      goal_frame: {
        ...previewResponse.goal_frame,
        raw_text: '我想学习深度学习入门',
        target_concepts: ['深度学习入门'],
        target_node_ids: [],
      },
      goal_understanding: {
        ...previewResponse.goal_understanding,
        raw_text: '我想学习深度学习入门',
        target_concepts: ['深度学习入门'],
      },
      missing_concepts: ['深度学习入门'],
      draft_entry: { action: 'create_project_overlay_draft', requires_explicit_request: true },
      available_actions: [
        {
          action: 'create_extension_draft',
          label: '生成扩展草稿并审核',
          description: '由 LLM/规则辅助补充缺失概念草稿，用户审核后才可用于增强路径。',
          risk_level: 'medium',
          requires_review: true,
          enabled: true,
        },
      ],
      candidates: [],
    })
    createMock.mockResolvedValue({
      id: 'project-extension-review',
      title: '深度学习入门计划',
      goal_text: '我想学习深度学习入门',
      goal_type: 'concept',
      domain: 'machine_learning',
      status: 'extension_review',
      created_at: '2026-04-22T09:00:00Z',
      updated_at: '2026-04-22T09:00:00Z',
      goal_resolution: null,
    })
    const wrapper = mountGoalForm()
    const vm = wrapper.vm as any

    vm.form.title = '深度学习入门计划'
    vm.form.goal_text = '我想学习深度学习入门'
    await nextTick()

    await findButtonByText(wrapper, '解析目标候选').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('创建待扩展项目')

    await findButtonByText(wrapper, '创建待扩展项目').trigger('click')
    await flushPromises()

    expect(createMock).toHaveBeenCalledWith({
      title: '深度学习入门计划',
      goal_text: '我想学习深度学习入门',
      resolution_session_id: 'session-new-draft',
      creation_mode: 'extension_review',
    })
    expect(pushMock).toHaveBeenCalledWith({
      name: 'Knowledge',
      query: {
        scope: 'project',
        goalDraft: '1',
        resolutionSessionId: 'session-new-draft',
      },
    })
  })
})
