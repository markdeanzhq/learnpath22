import { shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ProgressList from './ProgressList.vue'

const pushMock = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
}))

const slotStub = (tag: string) => ({ template: `<${tag}><slot /></${tag}>` })

const stages = [
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
]

const globalStubs = {
  ElCollapse: slotStub('div'),
  ElCollapseItem: slotStub('div'),
  ElTag: slotStub('span'),
  ElIcon: slotStub('i'),
  ElButton: slotStub('button'),
  ElButtonGroup: slotStub('div'),
  SuccessFilled: slotStub('i'),
  Loading: slotStub('i'),
  RemoveFilled: slotStub('i'),
  MoreFilled: slotStub('i'),
}

describe('ProgressList graph links', () => {
  it('routes progress task nodes to the latest path graph', () => {
    const wrapper = shallowMount(ProgressList, {
      props: {
        stages,
        events: [],
      },
      global: { stubs: globalStubs },
    })

    ;(wrapper.vm as any).handleLocateNode('ml_c01')

    expect(pushMock).toHaveBeenCalledWith({
      name: 'Knowledge',
      query: {
        scope: 'path',
        path_id: 'latest',
        nodeId: 'ml_c01',
      },
    })
  })

  it('renders collapsible task resources with safe links and source labels', () => {
    const wrapper = shallowMount(ProgressList, {
      props: {
        stages,
        events: [],
        nodeResourcesMap: {
          ml_c01: [
            {
              id: 'resource-001',
              title: '机器学习导论资料',
              url: 'https://example.com/ml-intro',
              snippet: '适合入门的导论资料。',
              source_type: 'tavily_auto',
              preference_reason: '匹配学习者偏好的视频课程形态。',
            },
            {
              id: 'resource-unsafe',
              title: '不可直接打开资料',
              url: 'javascript:alert(1)',
              snippet: null,
              source_type: 'manual',
            },
          ],
        },
      },
      global: { stubs: globalStubs },
    })

    expect(wrapper.text()).toContain('学习资料 2 条')
    expect(wrapper.text()).toContain('机器学习导论资料')
    expect(wrapper.text()).toContain('在线增强')
    expect(wrapper.text()).toContain('适合入门的导论资料。')
    expect(wrapper.text()).toContain('匹配学习者偏好的视频课程形态。')
    expect(wrapper.text()).toContain('建议动作：先阅读一条绑定资料')
    expect(wrapper.text()).toContain('不可直接打开资料')
    expect(wrapper.find('a.resource-link').attributes('href')).toBe('https://example.com/ml-intro')
    expect(wrapper.findAll('a.resource-link')).toHaveLength(1)
  })

  it('shows empty and failure resource fallbacks without blocking progress actions', () => {
    const emptyWrapper = shallowMount(ProgressList, {
      props: {
        stages,
        events: [],
        nodeResourcesMap: {},
      },
      global: { stubs: globalStubs },
    })
    expect(emptyWrapper.text()).toContain('学习资料 0 条')
    expect(emptyWrapper.text()).toContain('建议动作：先点击开始记录进度')
    expect(emptyWrapper.text()).toContain('该知识点暂无绑定资源')
    expect(emptyWrapper.text()).toContain('开始')

    const failedWrapper = shallowMount(ProgressList, {
      props: {
        stages,
        events: [],
        nodeResourcesMap: {},
        resourceError: '资源读取失败',
      },
      global: { stubs: globalStubs },
    })
    expect(failedWrapper.text()).toContain('资源暂不可用')
    expect(failedWrapper.text()).toContain('资源读取失败；进度操作仍可继续')
    expect(failedWrapper.text()).toContain('完成')
  })
})
