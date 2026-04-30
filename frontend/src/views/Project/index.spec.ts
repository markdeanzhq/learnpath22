import { defineComponent } from 'vue'
import { flushPromises, mount, shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import ProjectIndex from './index.vue'
import ProjectListPanel from './components/ProjectListPanel.vue'
import ProjectWorkflowPanel from './components/ProjectWorkflowPanel.vue'
import type { ProjectWorkflowState, ProjectWorkflowStepStatus } from '@/api/modules/project'

const {
  pushMock,
  replaceMock,
  generateMock,
  loadListMock,
  loadByIdMock,
  setCurrentProjectMock,
  clearCurrentProjectMock,
  deleteProjectMock,
  getWorkflowStateMock,
  trackingResetMock,
  planResetMock,
  routeState,
  currentProjectState,
} = vi.hoisted(() => ({
  pushMock: vi.fn(),
  replaceMock: vi.fn(),
  generateMock: vi.fn(),
  loadListMock: vi.fn(),
  loadByIdMock: vi.fn(),
  setCurrentProjectMock: vi.fn(),
  clearCurrentProjectMock: vi.fn(),
  deleteProjectMock: vi.fn(),
  getWorkflowStateMock: vi.fn(),
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
  useRouter: () => ({ push: pushMock, replace: replaceMock }),
  useRoute: () => routeState,
}))

vi.mock('element-plus/es/components/message/index', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('element-plus/es/components/message-box/index', () => ({
  ElMessageBox: {
    confirm: vi.fn(),
  },
}))

vi.mock('@/api/modules/project', () => ({
  projectApi: {
    getWorkflowState: getWorkflowStateMock,
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

const projectWorkflowPanelStub = defineComponent({
  name: 'ProjectWorkflowPanel',
  props: {
    step: { type: Number, default: -1 },
    goalFormMode: { type: String, default: 'create' },
    currentProjectId: { type: String, default: '' },
    currentProject: { type: Object, default: null },
    reconfirmReason: { type: String, default: '' },
    generatingPlan: { type: Boolean, default: false },
  },
  template: '<div data-testid="workflow-panel">{{ goalFormMode }}|{{ currentProjectId }}|{{ currentProject?.title || "" }}|{{ currentProject?.goal_text || "" }}|{{ currentProject?.goal_type || "auto" }}|{{ reconfirmReason }}</div>',
})

const projectListPanelStub = defineComponent({
  name: 'ProjectListPanel',
  template: '<div data-testid="project-list-panel" />',
})

function createWorkflowState(action = 'complete_profile'): ProjectWorkflowState {
  const profileStatus: ProjectWorkflowStepStatus = action === 'complete_profile' ? 'active' : 'completed'
  const overlayStatus: ProjectWorkflowStepStatus = action === 'review_overlay' ? 'warning' : 'pending'
  const pathStatus: ProjectWorkflowStepStatus = action === 'generate_path' ? 'active' : 'pending'

  return {
    project_id: 'project-001',
    project_status: 'active',
    updated_at: '2026-04-22T09:00:00Z',
    current_stage: action,
    recommended_next_action: {
      action,
      label: action === 'review_overlay' ? '审核扩展候选' : action === 'generate_path' ? '生成学习路径' : '继续画像采集',
      description: '下一步建议',
      route: action === 'review_overlay' ? '/knowledge' : action === 'generate_path' ? '/path' : '/project',
      enabled: true,
    },
    steps: [
      { key: 'goal', label: '目标确认', status: 'completed', summary: '已确认 3 个目标节点。' },
      { key: 'profile', label: '画像采集', status: profileStatus, summary: '画像状态' },
      { key: 'overlay', label: '图谱扩展', status: overlayStatus, summary: '扩展状态' },
      { key: 'path', label: '路径规划', status: pathStatus, summary: '路径状态' },
      { key: 'tracking', label: '学习跟踪', status: 'pending', summary: '跟踪状态' },
    ],
    goal: { confirmed: true },
    profile: { completed: action !== 'complete_profile' },
    overlay: { counts: { active_nodes: action === 'review_overlay' ? 1 : 0, active_edges: 0 } },
    path: { node_count: action === 'generate_path' ? 0 : 6 },
    tracking: { completion_rate: 0 },
  }
}

const slotStub = (tag: string) => defineComponent({
  template: `<${tag}><slot /></${tag}>`,
})

const buttonStub = defineComponent({
  props: {
    loading: { type: Boolean, default: false },
    disabled: { type: Boolean, default: false },
  },
  emits: ['click'],
  template: '<button :disabled="loading || disabled" @click="$emit(\'click\', $event)"><slot /></button>',
})

const cardStub = defineComponent({
  template: '<section><header><slot name="header" /></header><slot /></section>',
})

const emptyStub = defineComponent({
  props: {
    description: { type: String, default: '' },
  },
  template: '<div><slot name="image" />{{ description }}<slot /></div>',
})

const resultStub = defineComponent({
  props: {
    title: { type: String, default: '' },
    subTitle: { type: String, default: '' },
  },
  template: '<div>{{ title }}{{ subTitle }}<slot /><slot name="extra" /></div>',
})

const projectCreateWizardDialogStub = defineComponent({
  name: 'ProjectCreateWizardDialog',
  props: {
    modelValue: { type: Boolean, default: false },
    step: { type: Number, default: 0 },
    currentProjectId: { type: String, default: '' },
    currentProject: { type: Object, default: null },
    createFormDirty: { type: Boolean, default: false },
  },
  emits: ['update:modelValue', 'projectCreated', 'profileCompleted', 'generatePath', 'startCreate', 'createFormDirtyChanged', 'continueLater'],
  template: `
    <section v-if="modelValue" data-testid="create-wizard-dialog">
      <h2>创建学习项目</h2>
      <p>{{ step === 0 ? '先确认学习目标是否可规划' : step === 1 ? '继续完成画像采集' : '项目已准备好' }}</p>
      <p>目标解析</p>
      <p v-if="step === 1">画像可以稍后继续</p>
      <p v-if="createFormDirty">已有未提交创建信息</p>
      <button v-if="step === 1" @click="$emit('continueLater')">稍后在项目页继续</button>
    </section>
  `,
})

function mountProjectIndex() {
  return shallowMount(ProjectIndex, {
    global: {
      directives: {
        loading: () => undefined,
      },
      stubs: {
        ProjectListPanel: projectListPanelStub,
        ProjectWorkflowPanel: projectWorkflowPanelStub,
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
        ProjectCreateWizardDialog: projectCreateWizardDialogStub,
      },
    },
  })
}

function mountProjectListPanel(projects = [currentProjectState.value]) {
  return mount(ProjectListPanel, {
    props: {
      projects,
      loading: false,
      deletingProjectId: '',
    },
    global: {
      directives: {
        loading: () => undefined,
      },
      stubs: {
        ElCard: cardStub,
        ElButton: buttonStub,
        ElTag: slotStub('span'),
        ElEmpty: emptyStub,
        ElIcon: slotStub('i'),
      },
    },
  })
}

function findButtonByText(wrapper: ReturnType<typeof mountProjectIndex>, text: string) {
  const matched = wrapper.findAll('button').find((button) => button.text().includes(text))
  if (!matched) {
    throw new Error(`Button not found: ${text}`)
  }
  return matched
}

function mountProjectWorkflowPanel(step = 2, workflowState: ReturnType<typeof createWorkflowState> | null = null) {
  return mount(ProjectWorkflowPanel, {
    props: {
      step,
      goalFormMode: 'create',
      currentProjectId: 'project-001',
      currentProject: currentProjectState.value,
      reconfirmReason: '',
      generatingPlan: false,
      workflowState,
      workflowLoading: false,
    },
    global: {
      stubs: {
        GoalForm: slotStub('div'),
        ProfileQuestionnaire: slotStub('div'),
        ElCard: cardStub,
        ElSteps: slotStub('div'),
        ElStep: slotStub('div'),
        ElButton: buttonStub,
        ElTag: slotStub('span'),
        ElResult: resultStub,
        ElIcon: slotStub('i'),
      },
    },
  })
}

describe('Project page panels', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getWorkflowStateMock.mockResolvedValue(createWorkflowState())
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

  it('renders project cards with explicit goal and actions', async () => {
    const wrapper = mountProjectListPanel()

    expect(wrapper.text()).toContain('我的项目')
    expect(wrapper.text()).toContain('机器学习基础学习计划')
    expect(wrapper.text()).toContain('我想系统学习机器学习基础')
    expect(wrapper.text()).toContain('领域型')
    expect(wrapper.text()).toContain('可继续完成画像或生成学习路径。')
    expect(wrapper.text()).toContain('继续学习')

    await wrapper.get('.project-card-item').trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toEqual(currentProjectState.value)
  })

  it('renders extension review projects with draft review action', () => {
    currentProjectState.value = {
      ...currentProjectState.value,
      status: 'extension_review',
      title: '随机森林扩展计划',
      goal_text: '我想学习随机森林',
    }

    const wrapper = mountProjectListPanel()

    expect(wrapper.text()).toContain('随机森林扩展计划')
    expect(wrapper.text()).toContain('待扩展审核')
    expect(wrapper.text()).toContain('审核草稿')
    expect(wrapper.text()).toContain('需要先审核扩展草稿')
  })

  it('renders empty project guidance and emits create', async () => {
    const wrapper = mountProjectListPanel([])

    expect(wrapper.text()).toContain('还没有学习项目')
    expect(wrapper.text()).toContain('先创建一个机器学习基础学习计划')

    await wrapper.findAll('button').find((button) => button.text().includes('创建学习项目'))?.trigger('click')
    expect(wrapper.emitted('create')).toBeTruthy()
  })

  it('renders completed workflow summary and emits path generation', async () => {
    const wrapper = mountProjectWorkflowPanel(2)

    expect(wrapper.text()).toContain('项目已准备好')
    expect(wrapper.text()).toContain('已确认目标')
    expect(wrapper.text()).toContain('我想系统学习机器学习基础')
    expect(wrapper.text()).toContain('画像摘要')
    expect(wrapper.text()).toContain('已采集基础、偏好和时间预算')
    expect(wrapper.text()).toContain('生成阶段化学习路径')

    await wrapper.findAll('button').find((button) => button.text().includes('生成学习路径'))?.trigger('click')
    expect(wrapper.emitted('generatePath')).toBeTruthy()
  })

  it('renders project workflow overview and emits the recommended action', async () => {
    const wrapper = mountProjectWorkflowPanel(2, createWorkflowState('review_overlay'))

    expect(wrapper.text()).toContain('项目工作流总览')
    expect(wrapper.text()).toContain('目标确认')
    expect(wrapper.text()).toContain('图谱扩展')
    expect(wrapper.text()).toContain('扩展候选')
    expect(wrapper.text()).toContain('审核扩展候选')

    await wrapper.findAll('button').find((button) => button.text().includes('审核扩展候选'))?.trigger('click')
    expect(wrapper.emitted('openKnowledge')).toBeTruthy()
  })

  it('opens the create wizard dialog without replacing the launcher panel', async () => {
    const wrapper = mountProjectIndex()
    const vm = wrapper.vm as any

    vm.startCreate()
    await flushPromises()

    expect(replaceMock).toHaveBeenCalledWith({
      path: '/project',
      query: {
        create: '1',
      },
    })
    expect(vm.createWizardVisible).toBe(true)
    expect(vm.createWizardStep).toBe(0)
    expect(vm.step).toBe(-1)
    expect(wrapper.get('[data-testid="create-wizard-dialog"]').text()).toContain('创建学习项目')
    expect(wrapper.get('[data-testid="create-wizard-dialog"]').text()).toContain('先确认学习目标是否可规划')
    expect(wrapper.get('[data-testid="create-wizard-dialog"]').text()).toContain('目标解析')
  })

  it('opens the create wizard from route query', async () => {
    routeState.query = { create: '1' }

    const wrapper = mountProjectIndex()
    await flushPromises()

    expect((wrapper.vm as any).createWizardVisible).toBe(true)
    expect((wrapper.vm as any).createWizardStep).toBe(0)
    expect(wrapper.get('[data-testid="create-wizard-dialog"]').text()).toContain('先确认学习目标是否可规划')
  })

  it('continues profile collection in the wizard after project creation and allows leaving it for later', async () => {
    const wrapper = mountProjectIndex()
    const vm = wrapper.vm as any
    const createdProject = {
      ...currentProjectState.value,
      id: 'project-new',
      title: '新建机器学习计划',
    }

    vm.startCreate()
    await flushPromises()
    wrapper.getComponent(projectCreateWizardDialogStub).vm.$emit('projectCreated', createdProject)
    await flushPromises()

    expect(vm.createWizardStep).toBe(1)
    expect(vm.currentProjectId).toBe('project-new')
    expect(vm.step).toBe(1)
    expect(setCurrentProjectMock).toHaveBeenCalledWith(createdProject)
    expect(wrapper.get('[data-testid="create-wizard-dialog"]').text()).toContain('继续完成画像采集')
    expect(wrapper.get('[data-testid="create-wizard-dialog"]').text()).toContain('画像可以稍后继续')

    await findButtonByText(wrapper, '稍后在项目页继续').trigger('click')

    expect(vm.createWizardVisible).toBe(false)
    expect(vm.step).toBe(1)
    expect(vm.currentProjectId).toBe('project-new')
  })
})

describe('Project page goal reconfirm flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getWorkflowStateMock.mockResolvedValue(createWorkflowState())
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
      create: '1',
    }

    const wrapper = mountProjectIndex()
    await flushPromises()

    expect(loadListMock).toHaveBeenCalled()
    expect(replaceMock).toHaveBeenCalledWith({
      path: '/project',
      query: {
        mode: 'reconfirm',
        projectId: 'project-001',
        reason: 'goal-targets-removed',
      },
    })
    expect((wrapper.vm as any).step).toBe(0)
    expect((wrapper.vm as any).currentProjectId).toBe('project-001')
    expect(wrapper.get('[data-testid="workflow-panel"]').text()).toContain('reconfirm|project-001|机器学习基础学习计划|我想系统学习机器学习基础|domain|goal-targets-removed')
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
