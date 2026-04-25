import { shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ProgressList from './ProgressList.vue'

const pushMock = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
}))

const slotStub = (tag: string) => ({ template: `<${tag}><slot /></${tag}>` })

describe('ProgressList graph links', () => {
  it('routes progress task nodes to the latest path graph', () => {
    const wrapper = shallowMount(ProgressList, {
      props: {
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
        events: [],
      },
      global: {
        stubs: {
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
        },
      },
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
})
