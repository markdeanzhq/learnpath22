import { defineComponent } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import ProjectIndex from './index.vue'

const {
  pushMock,
  generateMock,
  loadListMock,
  loadByIdMock,
  setCurrentProjectMock,
  clearCurrentProjectMock,
  deleteProjectMock,
  trackingResetMock,
  planResetMock,
  routeState,
  currentProjectState,
} = vi.hoisted(() => ({
  pushMock: vi.fn(),
  generateMock: vi.fn(),
  loadListMock: vi.fn(),
  loadByIdMock: vi.fn(),
  setCurrentProjectMock: vi.fn(),
  clearCurrentProjectMock: vi.fn(),
  deleteProjectMock: vi.fn(),
  trackingResetMock: vi.fn(),
  planResetMock: vi.fn(),
  routeState: {
    query: {} as Record<string, string>,
  },
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
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
  useRoute: () => routeState,
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
  },
  ElMessageBox: {
    confirm: vi.fn(),
  },
}))

vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({
    get currentProject() {
      return currentProjectState.value
    },
    get projects() {
      return currentProjectState.value ? [currentProjectState.value] : []
    },
    loading: false,
    loadList: loadListMock,
    loadById: loadByIdMock,
    setCurrentProject: setCurrentProjectMock,
    clearCurrentProject: clearCurrentProjectMock,
    deleteProject: deleteProjectMock,
  }),
}))

vi.mock('@/stores/plan', () => ({
  usePlanStore: () => ({
    loading: false,
    currentPlan: null,
    lastReplanResult: null,
    generate: generateMock,
    reset: planResetMock,
  }),
}))

vi.mock('@/stores/tracking', () => ({
  useTrackingStore: () => ({
    reset: trackingResetMock,
  }),
}))

const tableStub = defineComponent({
  props: {
    data: {
      type: Array,
      default: () => [],
    },
  },
  template: '<div><slot /><template v-for="row in data" :key="row.id || row.title"><slot name="default" :row="row" /></template></div>',
})

const tableColumnStub = defineComponent({
  template: '<div><slot :row="{}" /></div>',
})

const goalFormStub = defineComponent({
  name: 'GoalForm',
  props: {
    mode: { type: String, default: 'create' },
    projectId: { type: String, default: '' },
    projectTitle: { type: String, default: '' },
    initialGoalText: { type: String, default: '' },
    initialGoalType: { type: String, default: 'auto' },
    reconfirmReason: { type: String, default: '' },
  },
  template: '<div data-testid="goal-form">{{ mode }}|{{ projectId }}|{{ projectTitle }}|{{ initialGoalText }}|{{ initialGoalType }}|{{ reconfirmReason }}</div>',
})

const slotStub = (tag: string) => defineComponent({
  template: `<${tag}><slot /></${tag}>`,
})

function mountProjectIndex() {
  return shallowMount(ProjectIndex, {
    global: {
      directives: {
        loading: () => undefined,
      },
      stubs: {
        GoalForm: goalFormStub,
        ProfileQuestionnaire: slotStub('div'),
        ElRow: slotStub('div'),
        ElCol: slotStub('div'),
        ElCard: slotStub('section'),
        ElSteps: slotStub('div'),
        ElStep: slotStub('div'),
        ElButton: slotStub('button'),
        ElTable: tableStub,
        ElTableColumn: tableColumnStub,
        ElTag: slotStub('span'),
        ElResult: slotStub('div'),
        ElEmpty: slotStub('div'),
        ElIcon: slotStub('i'),
      },
    },
  })
}

describe('Project page goal reconfirm flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeState.query = {}
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
  })

  it('enters project-level reconfirm mode from route query', async () => {
    routeState.query = {
      mode: 'reconfirm',
      projectId: 'project-001',
      reason: 'goal-targets-removed',
    }

    const wrapper = mountProjectIndex()
    await flushPromises()

    expect(loadListMock).toHaveBeenCalled()
    expect((wrapper.vm as any).step).toBe(0)
    expect((wrapper.vm as any).currentProjectId).toBe('project-001')
    expect(wrapper.get('[data-testid="goal-form"]').text()).toContain('reconfirm|project-001|机器学习基础学习计划|我想系统学习机器学习基础|domain|goal-targets-removed')
  })

  it('redirects to reconfirm flow when generating a path hits GOAL_TARGETS_REMOVED', async () => {
    generateMock.mockRejectedValue({
      response: {
        status: 409,
        data: {
          error: 'GOAL_TARGETS_REMOVED',
        },
      },
    })

    const wrapper = mountProjectIndex()
    ;(wrapper.vm as any).currentProjectId = 'project-001'

    await expect((wrapper.vm as any).goToPath()).resolves.toBeUndefined()

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
