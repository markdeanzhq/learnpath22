import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import NodeDetail from './NodeDetail.vue'

const slotStub = { template: '<div><slot /></div>' }

type TestNodeDetail = InstanceType<typeof NodeDetail>['$props']['node']

function mountDetail(node: TestNodeDetail) {
  return mount(NodeDetail, {
    props: { node },
    global: {
      stubs: {
        ElDrawer: slotStub,
        ElDescriptions: slotStub,
        ElDescriptionsItem: slotStub,
        ElTag: slotStub,
        ElRate: slotStub,
        ElSwitch: { template: '<button :disabled="disabled"><slot /></button>', props: ['disabled', 'modelValue'] },
        ElEmpty: slotStub,
        ElButton: { template: '<button :disabled="disabled"><slot /></button>', props: ['disabled'] },
      },
    },
  })
}

describe('NodeDetail origin-aware actions', () => {
  it('does not show rejected for baseline adjacent edges', () => {
    const wrapper = mountDetail({
      id: 'ml_c01',
      label: '基线节点',
      origin: 'baseline',
      review_status: 'pending',
      adjacent_edges: [
        {
          id: 'edge-001',
          source: 'ml_c01',
          target: 'ml_c02',
          target_label: '目标节点',
          direction: 'outgoing',
          origin: 'baseline',
          review_status: 'pending',
        },
      ],
    })

    expect(wrapper.text()).toContain('确认保留')
    expect(wrapper.text()).toContain('标记移除')
    expect(wrapper.text()).not.toContain('拒绝扩展')
  })

  it('shows rejected and keeps planning toggle separate for overlay adjacent edges', () => {
    const wrapper = mountDetail({
      id: 'po:project-001:n:test',
      label: '扩展节点',
      origin: 'overlay',
      review_status: 'pending',
      validation_status: 'valid',
      promotion_status: 'not_promoted',
      planning_enabled: true,
      adjacent_edges: [
        {
          id: 'po:project-001:e:test',
          source: 'po:project-001:n:test',
          target: 'ml_c02',
          target_label: '目标节点',
          direction: 'outgoing',
          origin: 'overlay',
          review_status: 'pending',
          validation_status: 'valid',
          promotion_status: 'not_promoted',
          planning_enabled: true,
        },
      ],
    })

    expect(wrapper.text()).toContain('拒绝扩展')
    expect(wrapper.findAll('button').some((button) => button.text().includes('拒绝扩展'))).toBe(true)
  })

  it('disables planner-affecting controls for unknown lifecycle', () => {
    const wrapper = mountDetail({
      id: 'po:project-001:n:test',
      label: '扩展节点',
      origin: 'overlay',
      review_status: 'unknown' as never,
      validation_status: 'unknown',
      promotion_status: 'unknown',
      planning_enabled: true,
      adjacent_edges: [
        {
          id: 'po:project-001:e:test',
          source: 'po:project-001:n:test',
          target: 'ml_c02',
          target_label: '目标节点',
          direction: 'outgoing',
          origin: 'overlay',
          review_status: 'unknown' as never,
          validation_status: 'unknown',
          promotion_status: 'unknown',
          planning_enabled: true,
        },
      ],
    })

    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBeGreaterThan(0)
    expect(buttons.every((button) => button.attributes('disabled') !== undefined)).toBe(true)
    expect(wrapper.text()).toContain('未知状态')
  })

  it('renders unknown origin explicitly without baseline fallback', () => {
    const wrapper = mountDetail({
      id: 'external-node',
      label: '未知节点',
      review_status: 'pending',
      adjacent_edges: [
        {
          id: 'external-edge',
          source: 'external-node',
          target: 'ml_c02',
          target_label: '目标节点',
          direction: 'outgoing',
          review_status: 'pending',
        },
      ],
    })

    expect(wrapper.text()).toContain('未知来源')
    expect(wrapper.text()).not.toContain('领域基线')
  })
})
