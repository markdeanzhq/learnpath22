import { defineComponent } from 'vue'
import { mount, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import StageTimeline from './StageTimeline.vue'
import TaskCard from './TaskCard.vue'

const pushMock = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
}))

const slotStub = (tag: string) => defineComponent({
  props: ['description'],
  template: `<${tag}><span v-if="description">{{ description }}</span><slot /></${tag}>`,
})

const buttonStub = defineComponent({
  props: {
    link: { type: Boolean, default: false },
    type: { type: String, default: '' },
    size: { type: String, default: '' },
  },
  emits: ['click'],
  template: '<button @click="$emit(\'click\')"><slot /></button>',
})

const taskCardStub = defineComponent({
  name: 'TaskCard',
  props: {
    task: { type: Object, required: true },
    taskNumber: { type: Number, default: 1 },
    practiceIntensity: { type: Number, default: null },
  },
  emits: ['locateNode'],
  template: '<button class="task-card-stub" @click="$emit(\'locateNode\', task.node_id)">第 {{ taskNumber }} 项 {{ task.name }} 练习强度 {{ practiceIntensity }}</button>',
})

const stages = [
  {
    stage_index: 0,
    stage_name: '基础阶段',
    estimated_hours: 5,
    tasks: [
      {
        node_id: 'ml_c01',
        name: '机器学习概览',
        order_in_stage: 0,
        difficulty: 1,
        importance: 5,
        estimated_hours: 2,
      },
      {
        node_id: 'ml_c02',
        name: '监督学习',
        order_in_stage: 1,
        difficulty: 3,
        importance: 4,
        estimated_hours: 3,
      },
    ],
  },
]

function mountStageTimeline(stageList: any[] = stages, practiceIntensity: number | null = null) {
  return shallowMount(StageTimeline, {
    props: { stages: stageList, practiceIntensity },
    global: {
      stubs: {
        TaskCard: taskCardStub,
        ElTimeline: slotStub('div'),
        ElTimelineItem: slotStub('div'),
        ElTag: slotStub('span'),
        ElRow: slotStub('div'),
        ElCol: slotStub('div'),
        ElEmpty: slotStub('div'),
      },
    },
  })
}

describe('StageTimeline', () => {
  beforeEach(() => {
    pushMock.mockClear()
  })

  it('renders learning-oriented stage summary and numbered tasks', () => {
    const wrapper = mountStageTimeline()

    expect(wrapper.text()).toContain('阶段 1')
    expect(wrapper.text()).toContain('基础阶段')
    expect(wrapper.text()).toContain('2 个知识点')
    expect(wrapper.text()).toContain('约 5 小时')
    expect(wrapper.text()).toContain('按顺序完成本阶段知识点')

    const taskCards = wrapper.findAll('.task-card-stub')
    expect(taskCards[0].text()).toContain('第 1 项 机器学习概览')
    expect(taskCards[1].text()).toContain('第 2 项 监督学习')
  })

  it('passes practice intensity into task cards and adjusts stage guidance', () => {
    const wrapper = mountStageTimeline(stages, 5)

    expect(wrapper.text()).toContain('优先选择代码、案例或小题完成动手验证')
    expect(wrapper.text()).toContain('练习强度 5')
    expect(wrapper.findComponent(taskCardStub).props('practiceIntensity')).toBe(5)
  })

  it('routes located task nodes to the latest path graph', async () => {
    const wrapper = mountStageTimeline()

    await wrapper.get('.task-card-stub').trigger('click')

    expect(wrapper.emitted('locateNode')?.[0]).toEqual(['ml_c01'])
    expect(pushMock).toHaveBeenCalledWith({
      name: 'Knowledge',
      query: {
        scope: 'path',
        path_id: 'latest',
        nodeId: 'ml_c01',
      },
    })
  })

  it('renders clear empty guidance when no stages or tasks exist', () => {
    const emptyWrapper = mountStageTimeline([])
    expect(emptyWrapper.text()).toContain('当前路径暂无阶段')
    expect(emptyWrapper.text()).toContain('请返回项目页重新生成')

    const emptyTaskWrapper = mountStageTimeline([{
      stage_index: 0,
      stage_name: '空阶段',
      estimated_hours: null,
      tasks: [],
      empty_reason: '核心掌握暂无任务：当前目标范围没有匹配到该阶段的知识点。',
    }])
    expect(emptyTaskWrapper.text()).toContain('空阶段')
    expect(emptyTaskWrapper.text()).toContain('核心掌握暂无任务：当前目标范围没有匹配到该阶段的知识点。')
    expect(emptyTaskWrapper.text()).toContain('系统不会为了填满版式加入无关知识点')
  })
})

describe('TaskCard', () => {
  it('renders learning guidance and emits locate event', async () => {
    const wrapper = mount(TaskCard, {
      props: {
        taskNumber: 3,
        task: {
          node_id: 'ml_c03',
          name: '损失函数',
          order_in_stage: 2,
          difficulty: 2,
          importance: 5,
          estimated_hours: 1,
        },
        practiceIntensity: 5,
      },
      global: {
        stubs: {
          ElCard: slotStub('section'),
          ElTag: slotStub('span'),
          ElButton: buttonStub,
          ElIcon: slotStub('i'),
          Star: slotStub('svg'),
          Clock: slotStub('svg'),
        },
      },
    })

    expect(wrapper.text()).toContain('第 3 项')
    expect(wrapper.text()).toContain('损失函数')
    expect(wrapper.text()).toContain('关键知识点')
    expect(wrapper.text()).toContain('入门难度 2/5')
    expect(wrapper.text()).toContain('约 1 小时')
    expect(wrapper.text()).toContain('关键节点：高练习密度')
    expect(wrapper.text()).toContain('优先在推荐资源中找代码、案例或小题完成一次动手验证。')

    await wrapper.get('button').trigger('click')

    expect(wrapper.emitted('locateNode')?.[0]).toEqual(['ml_c03'])
  })
})
