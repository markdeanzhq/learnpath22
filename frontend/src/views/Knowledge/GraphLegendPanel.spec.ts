import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import GraphLegendPanel from './GraphLegendPanel.vue'

const categoryLegend = [
  { key: 'foundation', label: '编程基础', color: '#E6A23C' },
  { key: 'ml_core', label: '机器学习核心', color: '#F56C6C' },
]

const relationLegend = [
  { type: 'REQUIRES', label: '前置依赖', description: '必须先学', lineStyle: 'solid' as const, hasArrow: true },
  { type: 'RELATED_TO', label: '相关关联', description: '推荐了解', lineStyle: 'dashed' as const, hasArrow: false },
]

describe('GraphLegendPanel', () => {
  it('renders node categories and relation semantics', () => {
    const wrapper = mount(GraphLegendPanel, {
      props: { categoryLegend, relationLegend },
    })

    expect(wrapper.text()).toContain('节点颜色')
    expect(wrapper.text()).toContain('编程基础')
    expect(wrapper.text()).toContain('机器学习核心')
    expect(wrapper.text()).toContain('前置依赖：必须先学')
    expect(wrapper.text()).toContain('相关关联：推荐了解')
    expect(wrapper.find('.legend-line-arrow').exists()).toBe(true)
    expect(wrapper.find('.legend-line-dashed').exists()).toBe(true)
  })
})
