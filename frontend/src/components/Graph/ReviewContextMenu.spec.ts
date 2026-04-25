import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ReviewContextMenu from './ReviewContextMenu.vue'

function mountMenu(targetData: Record<string, unknown>) {
  return mount(ReviewContextMenu, {
    props: {
      visible: true,
      x: 20,
      y: 20,
      containerWidth: 800,
      containerHeight: 600,
      targetType: 'node',
      targetData,
    },
    attachTo: document.body,
  })
}

describe('ReviewContextMenu origin-aware actions', () => {
  it('does not show rejected for baseline elements', () => {
    const wrapper = mountMenu({
      id: 'ml_c01',
      origin: 'baseline',
      review_status: 'pending',
    })

    expect(wrapper.text()).toContain('确认保留')
    expect(wrapper.text()).toContain('标记移除')
    expect(wrapper.text()).toContain('恢复待审')
    expect(wrapper.text()).not.toContain('拒绝扩展')
  })

  it('shows rejected for overlay elements', () => {
    const wrapper = mountMenu({
      id: 'po:project-001:n:test',
      origin: 'overlay',
      review_status: 'pending',
    })

    expect(wrapper.text()).toContain('拒绝扩展')
  })

  it('hides review actions for unknown origin', () => {
    const wrapper = mountMenu({
      id: 'bad-node',
      origin: 'external',
      review_status: 'pending',
    })

    const reviewButtons = wrapper.findAll('button.menu-item').filter((button) => button.text() !== '查看节点详情')
    expect(wrapper.text()).toContain('未知 origin')
    expect(reviewButtons).toHaveLength(0)
  })

  it('disables review actions for unknown lifecycle status', () => {
    const wrapper = mountMenu({
      id: 'po:project-001:n:test',
      origin: 'overlay',
      review_status: 'unknown',
    })

    const reviewButtons = wrapper.findAll('button.menu-item').filter((button) => button.text() !== '查看节点详情')
    expect(wrapper.text()).toContain('未知状态')
    expect(wrapper.text()).toContain('未知审核状态')
    expect(reviewButtons.every((button) => button.attributes('disabled') !== undefined)).toBe(true)
  })
})
