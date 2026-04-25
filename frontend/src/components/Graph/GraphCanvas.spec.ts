import { shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import GraphCanvas from './GraphCanvas.vue'

const { cyDestroyMock, cyElementsMock, cyGetElementByIdMock, reviewMenuProps } = vi.hoisted(() => ({
  cyDestroyMock: vi.fn(),
  cyElementsMock: vi.fn(),
  cyGetElementByIdMock: vi.fn(),
  reviewMenuProps: [] as any[],
}))

vi.mock('cytoscape', () => ({
  default: vi.fn((options: any) => {
    const elements = options.elements.map((element: any) => ({
      id: () => element.data.id,
      data: vi.fn(),
    }))
    cyElementsMock.mockReturnValue(elements)
    cyGetElementByIdMock.mockImplementation((id: string) => ({
      length: 1,
      data: vi.fn(),
      id: () => id,
    }))
    return {
      destroy: cyDestroyMock,
      on: vi.fn(),
      nodes: vi.fn(() => ({ removeClass: vi.fn() })),
      elements: cyElementsMock,
      getElementById: cyGetElementByIdMock,
      layout: vi.fn(() => ({ run: vi.fn() })),
    }
  }),
}))

vi.mock('./ReviewContextMenu.vue', () => ({
  default: {
    name: 'ReviewContextMenu',
    props: ['visible', 'x', 'y', 'containerWidth', 'containerHeight', 'targetType', 'targetData'],
    emits: ['review'],
    setup(props: any, { emit }: any) {
      reviewMenuProps.push(props)
      return { emitReview: (status: string) => emit('review', status) }
    },
    template: '<button data-testid="review-menu" @click="emitReview(\'confirmed\')"></button>',
  },
}))

describe('GraphCanvas lifecycle rendering', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    reviewMenuProps.length = 0
  })

  it('normalizes unknown overlay lifecycle without rebuilding graph for data-only updates', async () => {
    const wrapper = shallowMount(GraphCanvas, {
      props: {
        elements: [
          {
            group: 'nodes',
            data: {
              id: 'po:project-001:n:test',
              label: '扩展节点',
              origin: 'overlay',
            },
          },
        ],
      },
      attachTo: document.body,
    })
    await vi.dynamicImportSettled()

    await wrapper.setProps({
      elements: [
        {
          group: 'nodes',
          data: {
            id: 'po:project-001:n:test',
            label: '扩展节点',
            origin: 'overlay',
            review_status: 'confirmed',
            planning_enabled: false,
          },
        },
      ],
    })

    expect(cyDestroyMock).not.toHaveBeenCalled()
    expect(cyGetElementByIdMock).toHaveBeenCalledWith('po:project-001:n:test')
  })

  it('does not emit review events for unknown lifecycle menu targets', async () => {
    const wrapper = shallowMount(GraphCanvas, {
      props: {
        elements: [],
        reviewMode: true,
      },
      attachTo: document.body,
    })
    await wrapper.setData?.({})
    ;(wrapper.vm as any).menuState = {
      visible: true,
      x: 0,
      y: 0,
      containerWidth: 100,
      containerHeight: 100,
      targetType: 'node',
      targetData: {
        id: 'po:project-001:n:test',
        origin: 'overlay',
        review_status: 'unknown',
      },
    }
    await wrapper.vm.$nextTick()

    wrapper.findComponent({ name: 'ReviewContextMenu' }).vm.$emit('review', 'confirmed')
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('reviewNode')).toBeUndefined()
  })
})
