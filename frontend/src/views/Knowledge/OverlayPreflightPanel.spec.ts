import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import OverlayPreflightPanel from './OverlayPreflightPanel.vue'
import type { OverlayPreflightResponse } from '@/api/modules/graph'

const elementPlusStubs = {
  ElTag: defineComponent({ template: '<span><slot /></span>' }),
  ElButton: defineComponent({
    emits: ['click'],
    template: '<button type="button" @click="$emit(\'click\')"><slot /></button>',
  }),
}

const preflight = {
  project_id: 'project-001',
  status: 'ok',
  summary: '1 个节点 / 1 条关系可进入增强图谱，当前未发现阻塞问题。',
  counts: {
    active_nodes: 2,
    active_edges: 1,
    visible_overlay_nodes: 1,
    visible_overlay_edges: 1,
    path_overlay_nodes: 1,
    path_overlay_edges: 0,
    ignored_overlay_edges: 2,
    nodes: { pending_review: 1, invalid: 0 },
    edges: { pending_review: 0, invalid: 1 },
  },
} as unknown as OverlayPreflightResponse

describe('OverlayPreflightPanel', () => {
  it('renders overlay preflight status, counts, guidance and issues', () => {
    const wrapper = mount(OverlayPreflightPanel, {
      props: {
        preflight,
        tagType: 'success',
        statusLabel: '可用',
        guidance: '增强图谱已可用于项目图谱和路径预检。',
        issues: [{ kind: 'warning', message: '存在待审核候选' }],
      },
      global: { stubs: elementPlusStubs },
    })

    expect(wrapper.text()).toContain('增强图谱使用状态')
    expect(wrapper.text()).toContain('可用')
    expect(wrapper.text()).toContain('1 个节点 / 1 条关系可进入增强图谱')
    expect(wrapper.text()).toContain('候选 2 节点 / 1 关系')
    expect(wrapper.text()).toContain('可进入增强图谱 1 节点 / 1 关系')
    expect(wrapper.text()).toContain('待审核 1')
    expect(wrapper.text()).toContain('校验失败 1')
    expect(wrapper.text()).toContain('当前路径命中 1 节点 / 0 关系')
    expect(wrapper.text()).toContain('忽略关系 2')
    expect(wrapper.text()).toContain('存在待审核候选')
  })

  it('emits a path comparison action when overlay candidates can enter planning', async () => {
    const wrapper = mount(OverlayPreflightPanel, {
      props: {
        preflight,
        tagType: 'success',
        statusLabel: '可用',
        guidance: '增强图谱已可用于项目图谱和路径预检。',
        issues: [],
      },
      global: { stubs: elementPlusStubs },
    })

    expect(wrapper.text()).toContain('查看路径对比')
    await wrapper.find('button').trigger('click')

    expect(wrapper.emitted('open-path-comparison')).toHaveLength(1)
  })

  it('emits selected candidate action without changing lifecycle state locally', async () => {
    const repairAction = {
      actionType: 'repair_invalid',
      targetFilter: 'blocking',
      label: '修复校验失败 1',
      description: '打开候选队列并定位首个校验失败项。',
      count: 1,
      openFirstRepairable: true,
      tagType: 'danger',
    } as const
    const reviewAction = {
      actionType: 'review_needs_review',
      targetFilter: 'review',
      label: '复核需确认 1',
      description: '打开待复核候选。',
      count: 1,
      openFirstRepairable: true,
      tagType: 'warning',
    } as const
    const wrapper = mount(OverlayPreflightPanel, {
      props: {
        preflight,
        tagType: 'warning',
        statusLabel: '需关注',
        guidance: '先修复校验失败候选。',
        issues: [],
        candidateActions: [repairAction, reviewAction],
        primaryAction: repairAction,
      },
      global: { stubs: elementPlusStubs },
    })

    expect(wrapper.text()).toContain('候选处理入口')
    expect(wrapper.text()).toContain('修复校验失败 1')
    expect(wrapper.text()).toContain('复核需确认 1')

    const repairButton = wrapper.findAll('button').find((button) => button.text().includes('修复校验失败'))
    expect(repairButton).toBeTruthy()
    await repairButton!.trigger('click')

    expect(wrapper.emitted('open-candidate-action')).toEqual([[repairAction]])
  })

  it('omits ignored edge and issue sections when there is no extra signal', () => {
    const wrapper = mount(OverlayPreflightPanel, {
      props: {
        preflight: {
          ...preflight,
          counts: { ...preflight.counts, ignored_overlay_edges: 0 },
        },
        tagType: 'warning',
        statusLabel: '需关注',
        guidance: '当前草稿尚未产生可进入增强图谱的节点或关系。',
        issues: [],
      },
      global: { stubs: elementPlusStubs },
    })

    expect(wrapper.text()).not.toContain('忽略关系')
    expect(wrapper.find('.overlay-preflight-issues').exists()).toBe(false)
  })
})
