import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import GraphStatePanel from './GraphStatePanel.vue'

const elementPlusStubs = {
  ElEmpty: defineComponent({
    props: ['description'],
    template: '<section><p>{{ description }}</p><slot /></section>',
  }),
  ElResult: defineComponent({
    props: ['title', 'subTitle'],
    template: '<section><h3>{{ title }}</h3><p>{{ subTitle }}</p><slot name="extra" /></section>',
  }),
  ElSpace: defineComponent({ template: '<div><slot /></div>' }),
  ElButton: defineComponent({
    props: ['loading'],
    emits: ['click'],
    template: '<button type="button" :data-loading="loading" @click="$emit(\'click\')"><slot /></button>',
  }),
}

function mountPanel(props: InstanceType<typeof GraphStatePanel>['$props']) {
  return mount(GraphStatePanel, {
    props,
    global: { stubs: elementPlusStubs },
  })
}

describe('GraphStatePanel', () => {
  it('renders the no-project empty state', () => {
    const wrapper = mountPanel({ state: 'no-project' })

    expect(wrapper.text()).toContain('请先在项目页选择一个项目后再查看知识图谱')
  })

  it('renders the loading skeleton', () => {
    const wrapper = mountPanel({ state: 'loading' })

    expect(wrapper.find('[data-testid="graph-loading-skeleton"]').exists()).toBe(true)
    expect(wrapper.findAll('.graph-skeleton-node')).toHaveLength(8)
    expect(wrapper.text()).toContain('正在整理知识节点、审核状态与扩展候选')
  })

  it('renders empty actions and forwards refresh/sync events', async () => {
    const wrapper = mountPanel({
      state: 'empty',
      emptyDescription: '当前范围暂无图谱数据',
      syncing: true,
    })

    expect(wrapper.text()).toContain('当前范围暂无图谱数据')
    expect(wrapper.findAll('button')[1].attributes('data-loading')).toBe('true')

    await wrapper.findAll('button')[0].trigger('click')
    await wrapper.findAll('button')[1].trigger('click')

    expect(wrapper.emitted('refresh')).toHaveLength(1)
    expect(wrapper.emitted('sync')).toHaveLength(1)
  })

  it('renders error actions with fallback and explicit messages', async () => {
    const wrapper = mountPanel({ state: 'error', syncing: false })

    expect(wrapper.text()).toContain('知识图谱加载失败')
    expect(wrapper.text()).toContain('请稍后重试或重新同步图谱')

    await wrapper.findAll('button')[0].trigger('click')
    await wrapper.findAll('button')[1].trigger('click')

    expect(wrapper.emitted('refresh')).toHaveLength(1)
    expect(wrapper.emitted('sync')).toHaveLength(1)

    await wrapper.setProps({ errorMessage: '后端读取失败' })
    expect(wrapper.text()).toContain('后端读取失败')
  })
})
