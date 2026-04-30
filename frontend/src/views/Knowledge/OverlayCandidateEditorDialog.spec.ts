import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import OverlayCandidateEditorDialog from './OverlayCandidateEditorDialog.vue'
import type { CandidateEditorState } from './composables/useOverlayCandidateEditor'

function createEditor(overrides: Partial<CandidateEditorState> = {}): CandidateEditorState {
  return {
    visible: true,
    saving: false,
    kind: 'node',
    id: 'candidate-001',
    title: '编辑节点候选：线性回归',
    errors: ['missing_summary'],
    validationStatus: 'invalid',
    reviewStatus: 'pending',
    form: {
      name: '线性回归',
      summary: '',
      legality_rationale: '',
      group: 'core',
      category: 'model',
      difficulty_final: 2,
      importance_final: 3,
      estimated_hours: 2,
      req_math: 2,
      req_coding: 2,
      req_ml: 1,
      theory_weight: 0.6,
      practice_weight: 0.4,
    },
    ...overrides,
  }
}

const elementPlusStubs = {
  ElDialog: defineComponent({
    props: ['modelValue', 'title'],
    emits: ['update:modelValue'],
    template: '<section><h2>{{ title }}</h2><slot /><footer><slot name="footer" /></footer></section>',
  }),
  ElForm: defineComponent({
    template: '<form><slot /></form>',
  }),
  ElFormItem: defineComponent({
    props: ['label'],
    template: '<label><span>{{ label }}</span><slot /></label>',
  }),
  ElButton: defineComponent({
    emits: ['click'],
    template: '<button type="button" @click="$emit(\'click\')"><slot /></button>',
  }),
  ElInput: defineComponent({
    props: ['modelValue'],
    template: '<input :value="modelValue" />',
  }),
  ElInputNumber: defineComponent({
    props: ['modelValue'],
    template: '<input type="number" :value="modelValue" />',
  }),
  ElSelect: defineComponent({
    template: '<div><slot /></div>',
  }),
  ElOption: defineComponent({
    props: ['label'],
    template: '<div><slot>{{ label }}</slot></div>',
  }),
}

function mountDialog(editor = createEditor()) {
  return mount(OverlayCandidateEditorDialog, {
    props: {
      visible: editor.visible,
      candidateEditor: editor,
      candidateEditorIssueSummary: '当前候选有 1 个问题：缺少摘要。',
      candidateEditorQuickFixErrors: ['missing_summary'],
      overlayEndpointOptions: [
        { id: 'n1', label: '机器学习导论', hint: '当前图谱节点' },
        { id: 'n2', label: '线性回归', hint: '草稿节点', disabled: true },
      ],
      candidateEditorFieldIssue: (field: string) => field === 'summary' ? '缺少摘要。补充一句说明该候选的学习含义。' : '',
      quickFixLabel: (error: string) => error === 'missing_summary' ? '补默认摘要' : '应用建议',
    },
    global: {
      stubs: elementPlusStubs,
    },
  })
}

describe('OverlayCandidateEditorDialog', () => {
  it('renders node editor issues and forwards quick-fix, save and close events', async () => {
    const wrapper = mountDialog()

    expect(wrapper.text()).toContain('编辑节点候选：线性回归')
    expect(wrapper.text()).toContain('当前候选有 1 个问题：缺少摘要。')
    expect(wrapper.text()).toContain('缺少摘要。补充一句说明该候选的学习含义。')

    await wrapper.findAll('button').find((button) => button.text() === '补默认摘要')?.trigger('click')
    await wrapper.findAll('button').find((button) => button.text() === '保存并重新校验')?.trigger('click')
    await wrapper.findAll('button').find((button) => button.text() === '取消')?.trigger('click')

    expect(wrapper.emitted('quick-fix')).toEqual([['missing_summary']])
    expect(wrapper.emitted('save')).toHaveLength(1)
    expect(wrapper.emitted('update:visible')).toEqual([[false]])
  })

  it('renders edge endpoint choices and relation controls', () => {
    const wrapper = mountDialog(createEditor({
      kind: 'edge',
      title: '编辑关系候选：机器学习导论 → 线性回归',
      form: {
        source_node_id: 'n1',
        target_node_id: 'n2',
        relation_type: 'REQUIRES',
        legality_rationale: '',
      },
    }))

    expect(wrapper.text()).toContain('来源节点 ID 或名称')
    expect(wrapper.text()).toContain('机器学习导论')
    expect(wrapper.text()).toContain('当前图谱节点')
    expect(wrapper.text()).toContain('REQUIRES')
  })

  it('renders resource-specific fields', () => {
    const wrapper = mountDialog(createEditor({
      kind: 'resource',
      title: '编辑资源候选：线性回归教程',
      form: {
        title: '线性回归教程',
        url: 'https://example.test/linear-regression',
        resource_type: 'article',
        summary: '',
        evidence_source_id: 'source-001',
        quality_score: 0.8,
      },
    }))

    expect(wrapper.text()).toContain('证据来源 ID')
    expect(wrapper.text()).toContain('质量分')
    expect(wrapper.text()).toContain('资源类型')
  })
})
