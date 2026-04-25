import { shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import StageTimeline from './StageTimeline.vue'

const pushMock = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: pushMock }),
}))

const slotStub = (tag: string) => ({ template: `<${tag}><slot /></${tag}>` })

describe('StageTimeline graph links', () => {
  it('routes located task nodes to the latest path graph', () => {
    const wrapper = shallowMount(StageTimeline, {
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
      },
      global: {
        stubs: {
          TaskCard: slotStub('div'),
          ElTimeline: slotStub('div'),
          ElTimelineItem: slotStub('div'),
          ElTag: slotStub('span'),
          ElRow: slotStub('div'),
          ElCol: slotStub('div'),
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
