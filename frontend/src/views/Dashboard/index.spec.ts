import { defineComponent } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DashboardIndex from './index.vue'
import ProgressList from './components/ProgressList.vue'

const {
  pushMock,
  loadLatestMock,
  loadSummaryMock,
  loadEventsMock,
  addEventMock,
  resourceGetPlanResourcesMock,
  currentProjectState,
  currentPlanState,
  trackingState,
} = vi.hoisted(() => ({
  pushMock: vi.fn(),
  loadLatestMock: vi.fn(),
  loadSummaryMock: vi.fn(),
  loadEventsMock: vi.fn(),
  addEventMock: vi.fn(),
  resourceGetPlanResourcesMock: vi.fn(),
  currentProjectState: {
    value: {
      id: 'project-001',
      title: '机器学习基础学习计划',
    } as any,
  },
  currentPlanState: {
    value: null as any,
  },
  trackingState: {
    summary: null as any,
    events: [] as any[],
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
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
    loadLatest: loadLatestMock,
  }),
}))

vi.mock('@/stores/tracking', () => ({
  useTrackingStore: () => ({
    get summary() {
      return trackingState.summary
    },
    set summary(value) {
      trackingState.summary = value
    },
    get events() {
      return trackingState.events
    },
    set events(value) {
      trackingState.events = value
    },
    loadSummary: loadSummaryMock,
    loadEvents: loadEventsMock,
    addEvent: addEventMock,
  }),
}))

vi.mock('@/api/modules/resource', () => ({
  resourceApi: {
    getPlanResources: resourceGetPlanResourcesMock,
  },
}))

const cardStub = defineComponent({ template: '<section><slot name="header" /><slot /></section>' })
const slotStub = (tag: string) => defineComponent({ template: `<${tag}><slot /></${tag}>` })

const latestPlan = {
  id: 'plan-001',
  stages: [
    {
      stage_index: 0,
      stage_name: '基础阶段',
      estimated_hours: 2,
      tasks: [
        {
          node_id: 'ml_c01',
          name: '机器学习概览',
          order_in_stage: 0,
          difficulty: 1,
          importance: 5,
          estimated_hours: 2,
        },
      ],
    },
  ],
}

const nodeResource = {
  id: 'resource-001',
  title: '机器学习导论资料',
  url: 'https://example.com/ml-intro',
  snippet: '导论资料摘要',
  source_type: 'tavily_auto',
}

function mountDashboard() {
  return shallowMount(DashboardIndex, {
    global: {
      directives: {
        loading: () => undefined,
      },
      stubs: {
        StatsOverview: slotStub('div'),
        ElCard: cardStub,
        ElEmpty: slotStub('div'),
        ElButton: slotStub('button'),
        ElIcon: slotStub('i'),
        DataAnalysis: slotStub('i'),
      },
    },
  })
}

describe('Dashboard resources', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    currentProjectState.value = { id: 'project-001', title: '机器学习基础学习计划' }
    currentPlanState.value = null
    trackingState.summary = null
    trackingState.events = []
    loadSummaryMock.mockResolvedValue(undefined)
    loadEventsMock.mockResolvedValue(undefined)
    loadLatestMock.mockImplementation(async () => {
      currentPlanState.value = latestPlan
    })
    resourceGetPlanResourcesMock.mockResolvedValue({
      path_id: 'plan-001',
      stages: [
        {
          stage_name: '基础阶段',
          stage_resources: [],
          nodes: [
            {
              node_id: 'ml_c01',
              node_name: '机器学习概览',
              resources: [nodeResource],
            },
          ],
        },
      ],
    })
  })

  it('loads resources after latest path and passes a node resource map into ProgressList', async () => {
    const wrapper = mountDashboard()
    await flushPromises()

    expect(loadLatestMock).toHaveBeenCalledWith('project-001')
    expect(resourceGetPlanResourcesMock).toHaveBeenCalledWith('project-001', 'plan-001')

    const progressList = wrapper.findComponent(ProgressList)
    expect(progressList.exists()).toBe(true)
    expect(progressList.props('nodeResourcesMap')).toEqual({ ml_c01: [nodeResource] })
    expect(progressList.props('resourceError')).toBe('')
  })

  it('keeps progress list usable when resource loading fails', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    resourceGetPlanResourcesMock.mockRejectedValueOnce({ response: { data: { error: '资源读取失败' } } })

    const wrapper = mountDashboard()
    await flushPromises()

    const progressList = wrapper.findComponent(ProgressList)
    expect(progressList.exists()).toBe(true)
    expect(progressList.props('nodeResourcesMap')).toEqual({})
    expect(progressList.props('resourceError')).toBe('资源读取失败')
    warnSpy.mockRestore()
  })
})
