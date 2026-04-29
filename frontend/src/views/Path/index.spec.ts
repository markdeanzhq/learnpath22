import { defineComponent, nextTick } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PathIndex from './index.vue'

const {
  pushMock,
  replanMock,
  loadLatestMock,
  refreshServerStatusMock,
  planApiGetExplanationMock,
  planApiPreviewVariantsMock,
  planApiPreviewGraphOptionsMock,
  planApiConfirmVariantMock,
  planApiPreviewFeedbackMock,
  planApiConfirmKnownNodeDraftMock,
  planApiConfirmFeedbackMock,
  resourceGetPlanResourcesMock,
  resourceRecommendMock,
  searchMock,
  elMessageErrorMock,
  currentProjectState,
  currentPlanState,
  lastReplanResultState,
  llmApiKeySetState,
  llmExplanationPolishState,
} = vi.hoisted(() => ({
  pushMock: vi.fn(),
  replanMock: vi.fn(),
  loadLatestMock: vi.fn(),
  refreshServerStatusMock: vi.fn(),
  planApiGetExplanationMock: vi.fn(),
  planApiPreviewVariantsMock: vi.fn(),
  planApiPreviewGraphOptionsMock: vi.fn(),
  planApiConfirmVariantMock: vi.fn(),
  planApiPreviewFeedbackMock: vi.fn(),
  planApiConfirmKnownNodeDraftMock: vi.fn(),
  planApiConfirmFeedbackMock: vi.fn(),
  resourceGetPlanResourcesMock: vi.fn(),
  resourceRecommendMock: vi.fn(),
  searchMock: vi.fn(),
  elMessageErrorMock: vi.fn(),
  currentProjectState: {
    value: {
      id: 'project-001',
      title: '机器学习基础学习计划',
      goal_text: '我想系统学习机器学习基础',
      goal_type: 'domain',
      domain: 'machine_learning',
      status: 'draft',
      created_at: '2026-04-22T09:00:00Z',
      updated_at: '2026-04-22T09:00:00Z',
    },
  },
  currentPlanState: {
    value: {
      id: 'plan-001',
      version: 1,
      budget_status: 'feasible',
      total_hours: 12,
      stages: [] as any[],
    },
  },
  lastReplanResultState: {
    value: null as any,
  },
  llmApiKeySetState: {
    value: true,
  },
  llmExplanationPolishState: {
    value: false,
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
}))

vi.mock('pinia', () => ({
  storeToRefs: () => ({
    llmApiKeySet: llmApiKeySetState,
    llmExplanationPolish: llmExplanationPolishState,
  }),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: elMessageErrorMock,
    warning: vi.fn(),
  },
}))

vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({
    get currentProject() {
      return currentProjectState.value
    },
  }),
}))

vi.mock('@/stores/plan', () => ({
  usePlanStore: () => ({
    get currentPlan() {
      return currentPlanState.value
    },
    set currentPlan(value) {
      currentPlanState.value = value
    },
    get lastReplanResult() {
      return lastReplanResultState.value
    },
    set lastReplanResult(value) {
      lastReplanResultState.value = value
    },
    loading: false,
    replan: replanMock,
    loadLatest: loadLatestMock,
  }),
}))

vi.mock('@/stores/settings', () => ({
  useSettingsStore: () => ({
    get llmApiKeySet() {
      return llmApiKeySetState.value
    },
    set llmApiKeySet(value) {
      llmApiKeySetState.value = value
    },
    get llmExplanationPolish() {
      return llmExplanationPolishState.value
    },
    set llmExplanationPolish(value) {
      llmExplanationPolishState.value = value
    },
    refreshServerStatus: refreshServerStatusMock,
  }),
}))

vi.mock('@/api/modules/plan', () => ({
  planApi: {
    getExplanation: planApiGetExplanationMock,
    previewVariants: planApiPreviewVariantsMock,
    previewGraphOptions: planApiPreviewGraphOptionsMock,
    confirmVariant: planApiConfirmVariantMock,
    previewFeedback: planApiPreviewFeedbackMock,
    confirmKnownNodeDraft: planApiConfirmKnownNodeDraftMock,
    confirmFeedback: planApiConfirmFeedbackMock,
  },
}))

vi.mock('@/api/modules/search', () => ({
  searchApi: {
    search: searchMock,
  },
}))

vi.mock('@/api/modules/resource', () => ({
  resourceApi: {
    getPlanResources: resourceGetPlanResourcesMock,
    recommendPlanResources: resourceRecommendMock,
    bindManualResource: vi.fn(),
  },
}))

const slotStub = (tag: string) => defineComponent({
  props: ['title', 'description', 'subTitle'],
  template: `
    <${tag}>
      <span v-if="title">{{ title }}</span>
      <span v-if="description">{{ description }}</span>
      <span v-if="subTitle">{{ subTitle }}</span>
      <slot />
      <slot name="extra" />
    </${tag}>
  `,
})

function mountPathIndex() {
  return shallowMount(PathIndex, {
    global: {
      directives: {
        loading: () => undefined,
      },
      stubs: {
        StageTimeline: slotStub('div'),
        Explanation: slotStub('div'),
        ElCard: slotStub('section'),
        ElTag: slotStub('span'),
        ElDropdown: slotStub('div'),
        ElDropdownMenu: slotStub('div'),
        ElDropdownItem: slotStub('div'),
        ElButton: slotStub('button'),
        ElTabs: slotStub('div'),
        ElTabPane: slotStub('div'),
        ElAlert: slotStub('div'),
        ElCollapse: slotStub('div'),
        ElCollapseItem: slotStub('div'),
        ElEmpty: slotStub('div'),
        ElResult: slotStub('div'),
        ElIcon: slotStub('i'),
        ElInput: slotStub('div'),
        ElRadioGroup: slotStub('div'),
        ElRadio: slotStub('label'),
        ElSelect: slotStub('div'),
        ElOption: slotStub('div'),
        ElTable: slotStub('div'),
        ElTableColumn: slotStub('div'),
      },
    },
  })
}

function createResourceResponse(title: string) {
  return {
    path_id: 'plan-001',
    stages: [
      {
        stage_name: '基础准备',
        stage_resources: [],
        nodes: [
          {
            node_id: 'ml-a01',
            node_name: '机器学习导论',
            resources: [
              {
                id: `resource-${title}`,
                title,
                url: 'https://example.com/resource',
                source_type: 'tavily_auto',
              },
            ],
          },
        ],
      },
    ],
  }
}

function createExplanationResponse(overrides: Record<string, any> = {}) {
  return {
    node_explanations: [],
    ordering_explanations: [],
    stage_explanations: [],
    budget_explanation: null,
    reinforcement_explanations: [],
    dependency_chain_explanations: [],
    meta: {
      polish: {
        requested: false,
        applied: false,
        scope: [],
        fallback_reason: null,
      },
    },
    ...overrides,
  }
}

function createVariantPreviewResponse(overrides: Record<string, any> = {}) {
  return {
    variant_preview_id: 'variant-preview-001',
    project_id: 'project-001',
    status: 'active',
    expires_at: '2026-04-22T10:00:00Z',
    pack_hash: 'pack-hash-001',
    project_graph_hash: 'graph-hash-001',
    profile_hash: 'profile-hash-001',
    parameter_hash: 'parameter-hash-001',
    variants: [
      {
        variant_id: 'variant-standard',
        path_mode: 'standard',
        budget_summary: {
          status: 'feasible',
          total_hours: 12,
          estimated_weeks: 4,
        },
        included_node_ids: ['ml-a01', 'ml-a02'],
        excluded_node_ids: [],
        audit_summary: {
          tradeoff: '保持标准顺序',
        },
      },
      {
        variant_id: 'variant-compressed',
        path_mode: 'compressed',
        budget_summary: {
          status: 'tight',
          total_hours: 8,
          estimated_weeks: 3,
        },
        included_node_ids: ['ml-a01'],
        excluded_node_ids: ['ml-a02'],
        audit_summary: {
          tradeoff: '压缩低优先级节点',
        },
      },
    ],
    ...overrides,
  }
}

function createGraphOptionPreviewResponse(overrides: Record<string, any> = {}) {
  return createVariantPreviewResponse({
    variant_preview_id: 'graph-option-preview-001',
    project_graph_hash: 'graph-hash-enhanced',
    variants: [
      {
        variant_id: 'baseline-standard',
        path_mode: 'standard',
        preview_kind: 'graph_option',
        graph_option: 'baseline',
        option_label: '基础图谱路径',
        option_description: '不纳入项目级扩展草稿。',
        status: 'available',
        budget_summary: { status: 'feasible', total_hours: 12 },
        included_node_ids: ['ml-a01'],
        excluded_node_ids: [],
        added_node_ids: [],
        removed_node_ids: [],
        visible_overlay_node_ids: [],
        visible_overlay_edge_ids: [],
        path_overlay_node_ids: [],
        path_overlay_edge_ids: [],
        overlay_node_ids: [],
        overlay_edge_ids: [],
        order_changed: false,
        stage_changed: false,
        budget_changed: false,
        project_graph_hash: 'graph-hash-baseline',
        audit_summary: { nodes_missing_vs_enhanced: ['po:project-001:n:rf'] },
      },
      {
        variant_id: 'enhanced-standard',
        path_mode: 'standard',
        preview_kind: 'graph_option',
        graph_option: 'enhanced',
        option_label: '增强图谱路径',
        option_description: '纳入已审核的项目级扩展草稿。',
        status: 'available',
        budget_summary: { status: 'feasible', total_hours: 14 },
        included_node_ids: ['ml-a01', 'po:project-001:n:rf'],
        excluded_node_ids: [],
        added_node_ids: ['po:project-001:n:rf'],
        removed_node_ids: [],
        visible_overlay_node_ids: ['po:project-001:n:rf'],
        visible_overlay_edge_ids: [],
        path_overlay_node_ids: ['po:project-001:n:rf'],
        path_overlay_edge_ids: [],
        overlay_node_ids: ['po:project-001:n:rf'],
        overlay_edge_ids: [],
        order_changed: true,
        stage_changed: false,
        budget_changed: true,
        project_graph_hash: 'graph-hash-enhanced',
        audit_summary: { nodes_added_vs_baseline: ['po:project-001:n:rf'] },
      },
    ],
    ...overrides,
  })
}

function createFeedbackPreviewResponse(overrides: Record<string, any> = {}) {
  return {
    feedback_preview_id: 'feedback-preview-001',
    project_id: 'project-001',
    intent_type: 'increase_practice',
    confidence: 0.92,
    controlled_parameters: {
      practice_weight: 0.7,
    },
    diff: {
      added: ['ml-practice-01'],
      removed: [],
    },
    budget_delta: {
      total_hours_delta: 2,
    },
    blocked_actions: [],
    requires_confirmation: true,
    requires_second_confirm: false,
    status: 'active',
    expires_at: '2026-04-22T10:00:00Z',
    pack_hash: 'pack-hash-001',
    project_graph_hash: 'graph-hash-001',
    ...overrides,
  }
}

function createReplanResult(overrides: Record<string, any> = {}) {
  return {
    id: 'plan-002',
    project_id: 'project-001',
    version: 2,
    mode: 'variant_confirm',
    stages: [
      {
        stage_index: 0,
        stage_name: '基础准备',
        tasks: [{ node_id: 'ml-a01', name: '机器学习导论' }],
        estimated_hours: 2,
      },
    ],
    budget_status: 'feasible',
    total_hours: 12,
    diff: null,
    ...overrides,
  }
}

function findButtonByText(wrapper: ReturnType<typeof mountPathIndex>, text: string) {
  const matched = wrapper.findAll('button').find((button) => button.text().includes(text))
  if (!matched) {
    throw new Error(`Button not found: ${text}`)
  }
  return matched
}

function createDeferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: any) => void
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve
    reject = nextReject
  })
  return { promise, resolve, reject }
}

describe('Path page goal reconfirm flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    currentProjectState.value = {
      id: 'project-001',
      title: '机器学习基础学习计划',
      goal_text: '我想系统学习机器学习基础',
      goal_type: 'domain',
      domain: 'machine_learning',
      status: 'draft',
      created_at: '2026-04-22T09:00:00Z',
      updated_at: '2026-04-22T09:00:00Z',
    }
    currentPlanState.value = {
      id: 'plan-001',
      version: 1,
      budget_status: 'feasible',
      total_hours: 12,
      stages: [
        {
          stage_index: 0,
          stage_name: '基础准备',
          tasks: [{ node_id: 'ml-a01', name: '机器学习导论' }],
          estimated_hours: 2,
        },
      ],
    }
    lastReplanResultState.value = null
    llmApiKeySetState.value = true
    llmExplanationPolishState.value = false
    refreshServerStatusMock.mockResolvedValue(undefined)
    loadLatestMock.mockImplementation(async () => {
      currentPlanState.value = {
        id: 'plan-001',
        version: 1,
        budget_status: 'feasible',
        total_hours: 12,
        stages: [
          {
            stage_index: 0,
            stage_name: '基础准备',
            tasks: [{ node_id: 'ml-a01', name: '机器学习导论' }],
            estimated_hours: 2,
          },
        ],
      }
    })
    planApiGetExplanationMock.mockResolvedValue(createExplanationResponse())
    planApiPreviewVariantsMock.mockResolvedValue(createVariantPreviewResponse())
    planApiPreviewGraphOptionsMock.mockResolvedValue(createGraphOptionPreviewResponse())
    planApiConfirmVariantMock.mockResolvedValue(createReplanResult())
    planApiPreviewFeedbackMock.mockResolvedValue(createFeedbackPreviewResponse())
    planApiConfirmKnownNodeDraftMock.mockResolvedValue({
      draft_id: 'known-draft-001',
      feedback_preview_id: 'feedback-preview-001',
      project_id: 'project-001',
      node_ids: ['ml-a01'],
      evidence: [],
      status: 'confirmed',
      expires_at: '2026-04-22T10:00:00Z',
    })
    planApiConfirmFeedbackMock.mockResolvedValue(createReplanResult({ mode: 'feedback_confirm' }))
    resourceGetPlanResourcesMock.mockResolvedValue({ path_id: 'plan-001', stages: [] })
  })

  it('renders path dashboard summary and primary actions', async () => {
    const wrapper = mountPathIndex()
    await flushPromises()

    expect(wrapper.text()).toContain('学习路径驾驶舱')
    expect(wrapper.text()).toContain('机器学习基础学习计划')
    expect(wrapper.text()).toContain('目标：我想系统学习机器学习基础')
    expect(wrapper.text()).toContain('阶段数')
    expect(wrapper.text()).toContain('知识点')
    expect(wrapper.text()).toContain('预计投入')
    expect(wrapper.text()).toContain('12 小时')
    expect(wrapper.text()).toContain('时间预算')
    expect(wrapper.text()).toContain('继续学习')
    expect(wrapper.text()).toContain('调整路径')
    expect(wrapper.text()).toContain('查看解释')

    await findButtonByText(wrapper, '调整路径').trigger('click')
    expect((wrapper.vm as any).activeTab).toBe('previews')
  })

  it('renders the path adjustment workbench with guided options', async () => {
    const wrapper = mountPathIndex()
    await flushPromises()

    expect(wrapper.text()).toContain('路径调整中心')
    expect(wrapper.text()).toContain('先预览影响，再决定是否生成新版本')
    expect(wrapper.text()).toContain('1 选择调整方式')
    expect(wrapper.text()).toContain('2 查看差异和预算')
    expect(wrapper.text()).toContain('3 确认后保存新版')
    expect(wrapper.text()).toContain('立即生成新版')
    expect(wrapper.text()).toContain('先比较，再应用')
    expect(wrapper.text()).toContain('学习节奏')
    expect(wrapper.text()).toContain('适合：想改变学习投入或侧重点')
    expect(wrapper.text()).toContain('图谱范围')
    expect(wrapper.text()).toContain('适合：目标涉及项目级扩展知识')
    expect(wrapper.text()).toContain('自然语言')
    expect(wrapper.text()).toContain('适合：不知道该选哪个参数')
    expect(wrapper.text()).toContain('还没有生成变体预览')
    expect(wrapper.text()).toContain('搜索资料会绑定到当前知识点')
  })

  it('renders guided empty states for no project, no path, and load failure', async () => {
    currentProjectState.value = null as any
    currentPlanState.value = null as any
    const noProjectWrapper = mountPathIndex()
    await flushPromises()
    expect(noProjectWrapper.text()).toContain('请先选择学习项目')
    expect(noProjectWrapper.text()).toContain('学习路径需要依附于项目')

    currentProjectState.value = {
      id: 'project-empty',
      title: '空项目',
      goal_text: '我想学习机器学习',
      goal_type: 'domain',
      domain: 'machine_learning',
      status: 'draft',
      created_at: '2026-04-22T09:00:00Z',
      updated_at: '2026-04-22T09:00:00Z',
    }
    currentPlanState.value = null as any
    loadLatestMock.mockRejectedValueOnce({ response: { status: 404 } })
    const noPathWrapper = mountPathIndex()
    await flushPromises()
    expect(noPathWrapper.text()).toContain('还没有生成学习路径')
    expect(noPathWrapper.text()).toContain('先回到项目页完成画像并生成路径')

    loadLatestMock.mockRejectedValueOnce({ response: { data: { error: '路径读取失败' } } })
    const errorWrapper = mountPathIndex()
    await flushPromises()
    expect(errorWrapper.text()).toContain('路径加载失败')
    expect(errorWrapper.text()).toContain('路径读取失败')
    expect(errorWrapper.text()).toContain('重试加载')
  })

  it('updates the display mode hint for simple, defense, and debug modes', async () => {
    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    expect(wrapper.text()).toContain('普通模式：隐藏审计细节')
    expect(wrapper.text()).toContain('切换模式只影响展示，不会修改正式路径')

    vm.displayMode = 'defense'
    await nextTick()
    expect(wrapper.text()).toContain('答辩模式：显示算法依据与可解释链路')
    expect(wrapper.text()).toContain('生成流程、audit 摘要、overlay 计数')

    vm.displayMode = 'debug'
    await nextTick()
    expect(wrapper.text()).toContain('调试模式：显示 hash、审计字段与内部追溯信息')
    expect(wrapper.text()).toContain('graph drift、preview 过期和解释 DTO')

    vm.displayMode = 'simple'
    await nextTick()
  })

  it('uses llmExplanationPolish from settings store on initial explanation load', async () => {
    llmExplanationPolishState.value = true

    mountPathIndex()
    await flushPromises()

    expect(refreshServerStatusMock).toHaveBeenCalled()
    expect(planApiGetExplanationMock.mock.calls[0]?.[0]).toBe('project-001')
    expect(planApiGetExplanationMock.mock.calls[0]?.[1]).toBe(true)
  })

  it('keeps the newest explanation response when requests resolve out of order', async () => {
    planApiGetExplanationMock.mockResolvedValueOnce(createExplanationResponse())

    const wrapper = mountPathIndex()
    await flushPromises()

    const requestA = createDeferred<any>()
    const requestB = createDeferred<any>()
    planApiGetExplanationMock
      .mockImplementationOnce(() => requestA.promise)
      .mockImplementationOnce(() => requestB.promise)

    const vm = wrapper.vm as any
    const reloadA = vm.reloadExplanation(false)
    const reloadB = vm.reloadExplanation(true)

    requestB.resolve(createExplanationResponse({
      meta: {
        polish: {
          requested: true,
          applied: true,
          scope: ['node:ml-a01'],
          fallback_reason: null,
        },
      },
      node_explanations: [{ node_id: 'node-b', node_name: 'B', reason: 'newest', decision_type: 'target' }],
    }))
    await reloadB
    await flushPromises()

    expect(vm.explanation.meta.polish.applied).toBe(true)
    expect(vm.explanation.node_explanations[0].node_id).toBe('node-b')
    expect(vm.explanationError).toBe('')
    expect(vm.explanationLoading).toBe(false)

    requestA.reject({ response: { data: { error: 'stale failed' } } })
    await reloadA
    await flushPromises()

    expect(vm.explanation.meta.polish.applied).toBe(true)
    expect(vm.explanation.node_explanations[0].node_id).toBe('node-b')
    expect(vm.explanationError).toBe('')
    expect(vm.explanationLoading).toBe(false)
  })

  it('shows cached explanation while reloading the same plan', async () => {
    planApiGetExplanationMock.mockResolvedValueOnce(createExplanationResponse({
      node_explanations: [{ node_id: 'node-cached', node_name: '缓存节点', reason: 'cached', decision_type: 'target' }],
    }))

    const wrapper = mountPathIndex()
    await flushPromises()

    const request = createDeferred<any>()
    planApiGetExplanationMock.mockImplementationOnce(() => request.promise)

    const vm = wrapper.vm as any
    const reload = vm.reloadExplanation(false)
    await flushPromises()

    expect(vm.explanation.node_explanations[0].node_id).toBe('node-cached')
    expect(vm.explanationLoading).toBe(true)

    request.resolve(createExplanationResponse({
      node_explanations: [{ node_id: 'node-fresh', node_name: '新节点', reason: 'fresh', decision_type: 'target' }],
    }))
    await reload
    await flushPromises()

    expect(vm.explanation.node_explanations[0].node_id).toBe('node-fresh')
  })

  it('keeps existing resources when refresh fails', async () => {
    resourceGetPlanResourcesMock.mockResolvedValueOnce(createResourceResponse('已保存推荐资源'))

    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.planResources.stages[0].nodes[0].resources[0].title).toBe('已保存推荐资源')

    resourceGetPlanResourcesMock.mockRejectedValueOnce({ response: { data: { error: '资源读取失败' } } })
    await vm.loadPlanResources()
    await flushPromises()

    expect(vm.planResources.stages[0].nodes[0].resources[0].title).toBe('已保存推荐资源')
    expect(elMessageErrorMock).toHaveBeenCalledWith('资源读取失败')
  })

  it('renders node-first resource workbench and missing resource guidance', async () => {
    resourceGetPlanResourcesMock.mockResolvedValueOnce({
      path_id: 'plan-001',
      stages: [
        {
          stage_name: '基础准备',
          stage_resources: [],
          nodes: [
            {
              node_id: 'ml-a01',
              node_name: '机器学习导论',
              resources: [
                {
                  id: 'resource-intro',
                  title: '机器学习导论资源',
                  url: 'https://example.com/ml-intro',
                  snippet: '适合入门的机器学习导论资料。',
                  score: 0.91,
                  source_type: 'tavily_auto',
                },
              ],
            },
            {
              node_id: 'ml-a02',
              node_name: '监督学习',
              resources: [],
            },
          ],
        },
      ],
    })

    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    expect(wrapper.text()).toContain('知识点资源工作台')
    expect(wrapper.text()).toContain('资源默认跟随知识点展示')
    expect(wrapper.text()).toContain('总资源')
    expect(wrapper.text()).toContain('待补充知识点')
    expect(wrapper.text()).toContain('机器学习导论资源')
    expect(wrapper.text()).toContain('在线增强')
    expect(vm.totalResourceCount).toBe(1)
    expect(vm.selectedNodeResourceCount).toBe(1)
    expect(vm.missingResourceNodeCount).toBe(1)

    await wrapper.findAll('.resource-node-button')[1].trigger('click')
    await nextTick()

    expect(vm.selectedNodeId).toBe('ml-a02')
    expect(vm.selectedNodeResourceCount).toBe(0)
    expect(wrapper.text()).toContain('该知识点暂无资源，可自动补充或搜索绑定')
  })

  it('redirects to project-level reconfirm when replan hits GOAL_TARGETS_REMOVED', async () => {
    replanMock.mockRejectedValue({
      response: {
        status: 409,
        data: {
          error: 'GOAL_TARGETS_REMOVED',
        },
      },
    })

    const wrapper = mountPathIndex()
    await flushPromises()

    await expect((wrapper.vm as any).handleReplan('progress_aware')).resolves.toBeUndefined()

    expect(pushMock).toHaveBeenCalledWith({
      path: '/project',
      query: {
        mode: 'reconfirm',
        projectId: 'project-001',
        reason: 'goal-targets-removed',
      },
    })
  })

  it('previews variants without mutating the saved latest plan', async () => {
    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.previewVariants()
    await flushPromises()

    expect(planApiPreviewVariantsMock).toHaveBeenCalledWith('project-001')
    expect(vm.variantPreview.variant_preview_id).toBe('variant-preview-001')
    expect(vm.selectedVariantId).toBe('variant-standard')
    expect(vm.activeTab).toBe('previews')
    expect(currentPlanState.value.id).toBe('plan-001')
    expect(loadLatestMock).toHaveBeenCalledTimes(1)
  })

  it('confirms the selected variant then clears previews and reloads latest plan', async () => {
    loadLatestMock.mockImplementation(async () => {
      currentPlanState.value = {
        id: 'plan-002',
        version: 2,
        budget_status: 'feasible',
        total_hours: 10,
        stages: [],
      }
    })

    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.previewVariants()
    await flushPromises()
    vm.selectedVariantId = 'variant-compressed'

    await vm.confirmSelectedVariant()
    await flushPromises()

    expect(planApiConfirmVariantMock).toHaveBeenCalledWith('project-001', 'variant-preview-001', 'variant-compressed')
    expect(vm.variantPreview).toBeNull()
    expect(vm.feedbackPreview).toBeNull()
    expect(vm.previewUnsafeMessage).toBe('')
    expect(currentPlanState.value.id).toBe('plan-002')
    expect(vm.activeTab).toBe('timeline')
  })

  it('previews baseline and enhanced graph options without applying them', async () => {
    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.previewGraphOptions()
    await flushPromises()

    expect(planApiPreviewGraphOptionsMock).toHaveBeenCalledWith('project-001', undefined)
    expect(vm.graphOptionPreview.variant_preview_id).toBe('graph-option-preview-001')
    expect(vm.selectedGraphOptionVariantId).toBe('baseline-standard')
    expect(vm.variantPreview).toBeNull()
    expect(vm.feedbackPreview).toBeNull()
    expect(vm.canConfirmGraphOption).toBe(true)
    expect(wrapper.text()).toContain('基础 / 增强图谱路径对比')
    expect(wrapper.text()).toContain('增强图谱路径')
    expect(wrapper.text()).toContain('增强方案会新增 1 个已审核知识点')
    expect(wrapper.text()).not.toContain('po:project-001:n:rf')
    expect(currentPlanState.value.id).toBe('plan-001')
  })

  it('explains when enhanced graph has overlay but does not change current path', async () => {
    const unchangedPreview: any = createGraphOptionPreviewResponse({
      variants: [
        {
          variant_id: 'baseline-standard',
          path_mode: 'standard',
          preview_kind: 'graph_option',
          graph_option: 'baseline',
          option_label: '基础图谱路径',
          option_description: '不纳入项目级扩展草稿。',
          status: 'available',
          budget_summary: { status: 'feasible', total_hours: 12 },
          included_node_ids: ['ml-a01'],
          excluded_node_ids: [],
          added_node_ids: [],
          removed_node_ids: [],
          visible_overlay_node_ids: [],
          visible_overlay_edge_ids: [],
          path_overlay_node_ids: [],
          path_overlay_edge_ids: [],
          overlay_node_ids: [],
          overlay_edge_ids: [],
          order_changed: false,
          stage_changed: false,
          budget_changed: false,
          project_graph_hash: 'graph-hash-baseline',
          audit_summary: {},
        },
        {
          variant_id: 'enhanced-standard',
          path_mode: 'standard',
          preview_kind: 'graph_option',
          graph_option: 'enhanced',
          option_label: '增强图谱路径',
          option_description: '纳入已审核的项目级扩展草稿。',
          status: 'available',
          budget_summary: { status: 'feasible', total_hours: 12 },
          included_node_ids: ['ml-a01'],
          excluded_node_ids: [],
          added_node_ids: [],
          removed_node_ids: [],
          visible_overlay_node_ids: ['po:project-001:n:not-hit'],
          visible_overlay_edge_ids: [],
          path_overlay_node_ids: [],
          path_overlay_edge_ids: [],
          overlay_node_ids: ['po:project-001:n:not-hit'],
          overlay_edge_ids: [],
          order_changed: false,
          stage_changed: false,
          budget_changed: false,
          project_graph_hash: 'graph-hash-enhanced',
          audit_summary: {},
        },
      ],
    })
    planApiPreviewGraphOptionsMock.mockResolvedValueOnce(unchangedPreview)
    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.previewGraphOptions()
    await flushPromises()

    expect(wrapper.text()).toContain('增强图谱已纳入 1 个已审核扩展知识点和 0 条关系')
    expect(wrapper.text()).toContain('最终路径节点与基础方案一致')
    expect(wrapper.text()).not.toContain('po:project-001:n:not-hit')
  })

  it('explains edge/order/budget changes even when enhanced graph keeps the same node set', async () => {
    const edgeOnlyPreview: any = createGraphOptionPreviewResponse({
      variants: [
        {
          variant_id: 'baseline-standard',
          path_mode: 'standard',
          preview_kind: 'graph_option',
          graph_option: 'baseline',
          option_label: '基础图谱路径',
          option_description: '不纳入项目级扩展草稿。',
          status: 'available',
          budget_summary: { status: 'feasible', total_hours: 12 },
          included_node_ids: ['ml-a01', 'ml-b01'],
          excluded_node_ids: [],
          added_node_ids: [],
          removed_node_ids: [],
          visible_overlay_node_ids: [],
          visible_overlay_edge_ids: [],
          path_overlay_node_ids: [],
          path_overlay_edge_ids: [],
          overlay_node_ids: [],
          overlay_edge_ids: [],
          order_changed: false,
          stage_changed: false,
          budget_changed: false,
          project_graph_hash: 'graph-hash-baseline',
          audit_summary: {},
        },
        {
          variant_id: 'enhanced-standard',
          path_mode: 'standard',
          preview_kind: 'graph_option',
          graph_option: 'enhanced',
          option_label: '增强图谱路径',
          option_description: '纳入已审核的项目级扩展草稿。',
          status: 'available',
          budget_summary: { status: 'tight', total_hours: 14 },
          included_node_ids: ['ml-a01', 'ml-b01'],
          excluded_node_ids: [],
          added_node_ids: [],
          removed_node_ids: [],
          visible_overlay_node_ids: [],
          visible_overlay_edge_ids: ['po:project-001:e:dep'],
          path_overlay_node_ids: [],
          path_overlay_edge_ids: ['po:project-001:e:dep'],
          overlay_node_ids: [],
          overlay_edge_ids: ['po:project-001:e:dep'],
          order_changed: true,
          stage_changed: false,
          budget_changed: true,
          project_graph_hash: 'graph-hash-enhanced',
          audit_summary: {},
        },
      ],
    })
    planApiPreviewGraphOptionsMock.mockResolvedValueOnce(edgeOnlyPreview)
    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.previewGraphOptions()
    await flushPromises()

    expect(wrapper.text()).toContain('增强方案已命中当前路径')
    expect(wrapper.text()).toContain('路径命中 0 个扩展知识点 / 1 条扩展关系')
    expect(wrapper.text()).toContain('学习顺序变化')
    expect(wrapper.text()).toContain('预算估算变化')
    expect(wrapper.text()).toContain('即使节点集合一致')
    expect(wrapper.text()).not.toContain('po:project-001:e:dep')
  })

  it('explains when no reviewed overlay is available for graph option comparison', async () => {
    const noOverlayPreview: any = createGraphOptionPreviewResponse({
      project_graph_hash: 'graph-hash-baseline',
      variants: [
        {
          variant_id: 'baseline-standard',
          path_mode: 'standard',
          preview_kind: 'graph_option',
          graph_option: 'baseline',
          option_label: '基础图谱路径',
          option_description: '不纳入项目级扩展草稿。',
          status: 'available',
          budget_summary: { status: 'feasible', total_hours: 12 },
          included_node_ids: ['ml-a01'],
          excluded_node_ids: [],
          added_node_ids: [],
          removed_node_ids: [],
          visible_overlay_node_ids: [],
          visible_overlay_edge_ids: [],
          path_overlay_node_ids: [],
          path_overlay_edge_ids: [],
          overlay_node_ids: [],
          overlay_edge_ids: [],
          order_changed: false,
          stage_changed: false,
          budget_changed: false,
          project_graph_hash: 'graph-hash-baseline',
          audit_summary: {},
        },
        {
          variant_id: 'enhanced-standard',
          path_mode: 'standard',
          preview_kind: 'graph_option',
          graph_option: 'enhanced',
          option_label: '增强图谱路径',
          option_description: '纳入已审核的项目级扩展草稿。',
          status: 'available',
          budget_summary: { status: 'feasible', total_hours: 12 },
          included_node_ids: ['ml-a01'],
          excluded_node_ids: [],
          added_node_ids: [],
          removed_node_ids: [],
          visible_overlay_node_ids: [],
          visible_overlay_edge_ids: [],
          path_overlay_node_ids: [],
          path_overlay_edge_ids: [],
          overlay_node_ids: [],
          overlay_edge_ids: [],
          order_changed: false,
          stage_changed: false,
          budget_changed: false,
          project_graph_hash: 'graph-hash-baseline',
          audit_summary: {},
        },
      ],
    })
    planApiPreviewGraphOptionsMock.mockResolvedValueOnce(noOverlayPreview)
    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.previewGraphOptions()
    await flushPromises()

    expect(wrapper.text()).toContain('当前没有已审核、校验通过且开启规划的扩展图谱')
    expect(wrapper.text()).toContain('基础方案与增强方案会完全一致')
  })

  it('reveals graph option audit and hash details by display mode', async () => {
    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.previewGraphOptions()
    await flushPromises()

    expect(wrapper.text()).not.toContain('overlay 1 节点 / 0 边')
    expect(wrapper.text()).not.toContain('po:project-001:n:rf')
    expect(wrapper.text()).not.toContain('当前 graph：')

    vm.displayMode = 'defense'
    await nextTick()
    expect(wrapper.text()).toContain('overlay 1 节点 / 0 边')
    expect(wrapper.text()).toContain('po:project-001:n:rf')
    expect(wrapper.text()).not.toContain('当前 graph：')

    vm.displayMode = 'debug'
    await nextTick()
    expect(wrapper.text()).toContain('当前 graph：')

    vm.displayMode = 'simple'
    await nextTick()
  })

  it('does not select unavailable graph options', async () => {
    const unavailablePreview: any = createGraphOptionPreviewResponse()
    unavailablePreview.variants[0] = {
      ...unavailablePreview.variants[0],
      status: 'unavailable',
      blocked_reason: 'GOAL_TARGETS_REMOVED',
    }
    planApiPreviewGraphOptionsMock.mockResolvedValueOnce(unavailablePreview)
    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.previewGraphOptions()
    await flushPromises()

    expect(vm.selectedGraphOptionVariantId).toBe('enhanced-standard')
    vm.selectGraphOptionVariant(unavailablePreview.variants[0])
    expect(vm.selectedGraphOptionVariantId).toBe('enhanced-standard')
    expect(wrapper.text()).toContain('暂不可用')
    expect(vm.graphOptionPreview.variants[0].blocked_reason).toBe('GOAL_TARGETS_REMOVED')
  })

  it('confirms the selected graph option through the variant confirmation API', async () => {
    loadLatestMock.mockImplementation(async () => {
      currentPlanState.value = {
        id: 'plan-graph-option',
        version: 2,
        budget_status: 'feasible',
        total_hours: 14,
        stages: [],
      }
    })

    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.previewGraphOptions()
    await flushPromises()
    vm.selectedGraphOptionVariantId = 'enhanced-standard'

    await vm.confirmGraphOption()
    await flushPromises()

    expect(planApiConfirmVariantMock).toHaveBeenCalledWith(
      'project-001',
      'graph-option-preview-001',
      'enhanced-standard',
    )
    expect(vm.graphOptionPreview).toBeNull()
    expect(vm.variantPreview).toBeNull()
    expect(vm.feedbackPreview).toBeNull()
    expect(currentPlanState.value.id).toBe('plan-graph-option')
    expect(vm.activeTab).toBe('timeline')
  })

  it('renders feedback preview state without applying it as a saved plan', async () => {
    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.feedbackText = '我想增加实践内容'
    await vm.previewFeedback()
    await flushPromises()

    expect(planApiPreviewFeedbackMock).toHaveBeenCalledWith('project-001', '我想增加实践内容')
    expect(vm.feedbackPreview.feedback_preview_id).toBe('feedback-preview-001')
    expect(vm.feedbackDiffEntries).toEqual([{ key: '新增知识点', values: ['ml-practice-01'] }])
    expect(vm.canConfirmFeedback).toBe(true)
    expect(currentPlanState.value.id).toBe('plan-001')
  })

  it('requires known-node draft confirmation before applying mark-known feedback', async () => {
    planApiPreviewFeedbackMock.mockResolvedValueOnce(createFeedbackPreviewResponse({
      intent_type: 'mark_known_nodes',
      requires_second_confirm: true,
      known_node_draft: {
        draft_id: 'known-draft-001',
        feedback_preview_id: 'feedback-preview-001',
        project_id: 'project-001',
        node_ids: ['ml-a01'],
        evidence: [],
        status: 'draft',
        expires_at: '2026-04-22T10:00:00Z',
      },
    }))

    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.feedbackText = '机器学习导论我已经会了'
    await vm.previewFeedback()
    await flushPromises()

    expect(vm.canConfirmFeedback).toBe(false)

    await vm.confirmKnownNodeDraft()
    await flushPromises()

    expect(planApiConfirmKnownNodeDraftMock).toHaveBeenCalledWith('project-001', 'known-draft-001')
    expect(vm.feedbackPreview.known_node_draft.status).toBe('confirmed')
    expect(vm.canConfirmFeedback).toBe(true)

    await vm.confirmFeedbackPreview()
    await flushPromises()

    expect(planApiConfirmFeedbackMock).toHaveBeenCalledWith('project-001', 'feedback-preview-001')
    expect(vm.feedbackPreview).toBeNull()
    expect(vm.activeTab).toBe('timeline')
  })

  it('clears unsafe preview state when backend reports stale preview drift', async () => {
    planApiPreviewVariantsMock.mockRejectedValueOnce({
      response: {
        data: {
          error: 'STALE_VARIANT_PREVIEW',
        },
      },
    })

    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.previewVariants()
    await flushPromises()

    expect(vm.variantPreview).toBeNull()
    expect(vm.feedbackPreview).toBeNull()
    expect(vm.previewUnsafeMessage).toBe('预览已过期或路径依赖的画像/图谱/知识包已变化，请重新生成预览。')
  })

  it('ignores duplicate preview and confirm requests while path previews are in flight', async () => {
    const previewDeferred = createDeferred<any>()
    planApiPreviewVariantsMock.mockReturnValueOnce(previewDeferred.promise)
    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    const firstPreview = vm.previewVariants()
    const secondPreview = vm.previewVariants()
    await flushPromises()

    expect(planApiPreviewVariantsMock).toHaveBeenCalledTimes(1)
    previewDeferred.resolve(createVariantPreviewResponse())
    await firstPreview
    await secondPreview
    await flushPromises()

    const confirmDeferred = createDeferred<any>()
    planApiConfirmVariantMock.mockReturnValueOnce(confirmDeferred.promise)
    const firstConfirm = vm.confirmSelectedVariant()
    const secondConfirm = vm.confirmSelectedVariant()
    await flushPromises()

    expect(planApiConfirmVariantMock).toHaveBeenCalledTimes(1)
    confirmDeferred.resolve(createReplanResult())
    await firstConfirm
    await secondConfirm
    await flushPromises()
  })

  it('clears previews when the path context is reloaded', async () => {
    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    await vm.previewVariants()
    await flushPromises()
    expect(vm.variantPreview).not.toBeNull()

    await vm.loadPath()
    await flushPromises()

    expect(vm.variantPreview).toBeNull()
    expect(vm.feedbackPreview).toBeNull()
    expect(vm.previewUnsafeMessage).toBe('')
  })
})
