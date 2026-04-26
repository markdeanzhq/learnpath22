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
})
