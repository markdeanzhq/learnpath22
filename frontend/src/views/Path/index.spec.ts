import { defineComponent } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PathIndex from './index.vue'

const {
  pushMock,
  replanMock,
  loadLatestMock,
  planApiGetExplanationMock,
  resourceGetPlanResourcesMock,
  resourceRecommendMock,
  searchMock,
  currentProjectState,
  currentPlanState,
  lastReplanResultState,
} = vi.hoisted(() => ({
  pushMock: vi.fn(),
  replanMock: vi.fn(),
  loadLatestMock: vi.fn(),
  planApiGetExplanationMock: vi.fn(),
  resourceGetPlanResourcesMock: vi.fn(),
  resourceRecommendMock: vi.fn(),
  searchMock: vi.fn(),
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
      stages: [],
    },
  },
  lastReplanResultState: {
    value: null as any,
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
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
      stages: [],
    }
    lastReplanResultState.value = null
    loadLatestMock.mockResolvedValue(undefined)
    planApiGetExplanationMock.mockResolvedValue({ summary: 'ok' })
    resourceGetPlanResourcesMock.mockResolvedValue({ plan_id: 'plan-001', stages: [] })
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
