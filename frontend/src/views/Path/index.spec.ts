import { defineComponent } from 'vue'
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
  template: `<${tag}><slot /></${tag}>`,
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

  it('renders feedback preview state without applying it as a saved plan', async () => {
    const wrapper = mountPathIndex()
    await flushPromises()

    const vm = wrapper.vm as any
    vm.feedbackText = '我想增加实践内容'
    await vm.previewFeedback()
    await flushPromises()

    expect(planApiPreviewFeedbackMock).toHaveBeenCalledWith('project-001', '我想增加实践内容')
    expect(vm.feedbackPreview.feedback_preview_id).toBe('feedback-preview-001')
    expect(vm.feedbackDiffEntries).toEqual([{ key: 'added', values: ['ml-practice-01'] }])
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
