import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import OverlayExtractionPreviewPanel from './OverlayExtractionPreviewPanel.vue'
import type {
  OverlayExtractionPayloadPreviewResponse,
  OverlayExtractionPayloadValidationResponse,
} from '@/api/modules/graph'
import type { OverlayPreviewGroup } from './composables/useOverlayDraftInput'

const elementPlusStubs = {
  ElDescriptions: defineComponent({
    template: '<dl><slot /></dl>',
  }),
  ElDescriptionsItem: defineComponent({
    props: ['label'],
    template: '<div><dt>{{ label }}</dt><dd><slot /></dd></div>',
  }),
  ElTag: defineComponent({
    template: '<span><slot /></span>',
  }),
  ElAlert: defineComponent({
    props: ['title', 'type'],
    template: '<div :data-type="type">{{ title }}</div>',
  }),
}

const preview: OverlayExtractionPayloadPreviewResponse = {
  source_ids: ['source-001', 'source-002'],
  mode: 'custom_extension',
  extraction_payload: {},
  warnings: ['资料内容较少', '建议人工复核'],
  counts: {
    nodes: 2,
    edges: 1,
    resources: 1,
  },
  provenance: {},
}

const validation: OverlayExtractionPayloadValidationResponse = {
  source_ids: ['source-001'],
  warnings: [],
  counts: {
    nodes: { total: 2, valid: 1, invalid: 1, needs_review: 0 },
    edges: { total: 1, valid: 1, invalid: 0, needs_review: 0 },
    resources: { total: 1, valid: 0, invalid: 0, needs_review: 1 },
  },
  summary: {
    has_blocking_errors: true,
    needs_review: true,
    invalid_count: 1,
    needs_review_count: 1,
  },
  nodes: [],
  edges: [],
  resources: [],
}

function mountPanel(selected: Partial<Record<OverlayPreviewGroup, number[]>> = {}) {
  const selectedIndexes = {
    nodes: selected.nodes || [0],
    edges: selected.edges || [0],
    resources: selected.resources || [0],
  }
  return mount(OverlayExtractionPreviewPanel, {
    props: {
      preview,
      normalizedPreviewPayload: {
        nodes: [
          { name: '线性回归', summary: '监督学习基础模型', confidence: 0.82 },
          { name: '梯度下降', legality_rationale: '用于优化模型参数' },
        ],
        edges: [
          { source_node_id: '机器学习导论', target_node_id: '线性回归', relation_type: 'REQUIRES', legality_rationale: '需要先理解基础概念' },
        ],
        resources: [
          { title: '线性回归教程', summary: '图文教程', resource_type: 'article' },
        ],
      },
      selectedPreviewCounts: {
        nodes: selectedIndexes.nodes.length,
        edges: selectedIndexes.edges.length,
        resources: selectedIndexes.resources.length,
      },
      validation,
      isPreviewCandidateSelected: (group: OverlayPreviewGroup, index: number) => selectedIndexes[group].includes(index),
      candidateTitle: (candidate: Record<string, any>, fallback: string) => candidate.name || candidate.title || fallback,
      edgeCandidateSummary: (candidate: Record<string, any>) => `${candidate.source_node_id} → ${candidate.target_node_id}`,
    },
    global: {
      stubs: elementPlusStubs,
    },
  })
}

describe('OverlayExtractionPreviewPanel', () => {
  it('renders counts, candidates, warnings and validation summary', () => {
    const wrapper = mountPanel()

    expect(wrapper.text()).toContain('AI 抽取预览')
    expect(wrapper.text()).toContain('节点候选')
    expect(wrapper.text()).toContain('1 / 2')
    expect(wrapper.text()).toContain('来源数')
    expect(wrapper.text()).toContain('2')
    expect(wrapper.text()).toContain('线性回归')
    expect(wrapper.text()).toContain('机器学习导论 → 线性回归')
    expect(wrapper.text()).toContain('线性回归教程')
    expect(wrapper.text()).toContain('资料内容较少；建议人工复核')
    expect(wrapper.text()).toContain('预校验：通过 2，失败 1，待复核 1')
  })

  it('emits candidate toggle events with group, index and checked state', async () => {
    const wrapper = mountPanel()

    await wrapper.findAll('input[type="checkbox"]')[0].setValue(false)
    await wrapper.findAll('input[type="checkbox"]')[3].setValue(false)

    expect(wrapper.emitted('toggle-candidate')).toEqual([
      ['nodes', 0, false],
      ['resources', 0, false],
    ])
  })

  it('uses fallback copy for missing candidate details', () => {
    const wrapper = mount(OverlayExtractionPreviewPanel, {
      props: {
        preview: { ...preview, warnings: [], counts: { nodes: 1, edges: 1, resources: 1 } },
        normalizedPreviewPayload: {
          nodes: [{}],
          edges: [{}],
          resources: [{}],
        },
        selectedPreviewCounts: { nodes: 0, edges: 0, resources: 0 },
        validation: null,
        isPreviewCandidateSelected: () => false,
        candidateTitle: vi.fn((candidate: Record<string, any>, fallback: string) => candidate.name || candidate.title || fallback),
        edgeCandidateSummary: vi.fn(() => '未知来源 → 未知目标'),
      },
      global: {
        stubs: elementPlusStubs,
      },
    })

    expect(wrapper.text()).toContain('节点候选 1')
    expect(wrapper.text()).toContain('暂无摘要')
    expect(wrapper.text()).toContain('暂无合法性说明')
    expect(wrapper.text()).toContain('未知来源 → 未知目标')
  })
})
