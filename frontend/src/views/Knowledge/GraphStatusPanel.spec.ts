import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import GraphStatusPanel from './GraphStatusPanel.vue'
import type { OverlayPreflightResponse } from '@/api/modules/graph'

const elementPlusStubs = {
  ElTag: defineComponent({ template: '<span><slot /></span>' }),
}

const preflight = {
  counts: {
    visible_overlay_nodes: 2,
    visible_overlay_edges: 1,
  },
} as unknown as OverlayPreflightResponse

describe('GraphStatusPanel', () => {
  it('renders graph scope, counts, overlay preflight and cache diagnostics', () => {
    const wrapper = mount(GraphStatusPanel, {
      props: {
        scopeLabel: '学习路径子图',
        statusHint: '仅展示最新学习路径命中的知识点和依赖关系。',
        nodeCount: 12,
        edgeCount: 8,
        overlayPreflight: preflight,
        overlayPreflightTagType: 'success',
        showGraphCacheDiagnostics: true,
        graphCacheDiagnosticItems: [
          { key: 'pack_graph_elements', label: '领域图缓存', hitRateLabel: '命中 75%', sizeLabel: '2/16' },
          { key: 'project_graph_snapshot', label: '项目快照缓存', hitRateLabel: '命中 100%', sizeLabel: '1/64' },
        ],
        graphCacheStatsLoading: true,
        graphCacheStatsError: '缓存读取失败',
      },
      global: { stubs: elementPlusStubs },
    })

    expect(wrapper.text()).toContain('学习路径子图')
    expect(wrapper.text()).toContain('节点 12')
    expect(wrapper.text()).toContain('关系 8')
    expect(wrapper.text()).toContain('本地读模型')
    expect(wrapper.text()).toContain('增强候选 2 / 1')
    expect(wrapper.text()).toContain('领域图缓存 命中 75% · 2/16')
    expect(wrapper.text()).toContain('项目快照缓存 命中 100% · 1/64')
    expect(wrapper.text()).toContain('刷新中')
    expect(wrapper.text()).toContain('缓存读取失败')
  })

  it('hides optional diagnostics and overlay counts when they are unavailable', () => {
    const wrapper = mount(GraphStatusPanel, {
      props: {
        scopeLabel: '领域基线图',
        statusHint: '展示领域知识包的稳定基线。',
        nodeCount: 0,
        edgeCount: 0,
        overlayPreflight: null,
        overlayPreflightTagType: 'warning',
        showGraphCacheDiagnostics: false,
        graphCacheDiagnosticItems: [],
        graphCacheStatsLoading: false,
        graphCacheStatsError: '',
      },
      global: { stubs: elementPlusStubs },
    })

    expect(wrapper.text()).toContain('领域基线图')
    expect(wrapper.text()).not.toContain('增强候选')
    expect(wrapper.find('[data-testid="graph-cache-diagnostics"]').exists()).toBe(false)
  })
})
