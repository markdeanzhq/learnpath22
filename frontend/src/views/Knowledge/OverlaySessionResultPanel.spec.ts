import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import OverlaySessionResultPanel from './OverlaySessionResultPanel.vue'
import type {
  GoalExtensionDraftResponse,
  OverlayEdgeCandidate,
  OverlayNodeCandidate,
  OverlayResourceCandidate,
} from '@/api/modules/graph'
import type { OverlaySessionView } from './composables/useOverlayCandidateWorkflow'

const elementPlusStubs = {
  ElDescriptions: defineComponent({ template: '<dl><slot /></dl>' }),
  ElDescriptionsItem: defineComponent({
    props: ['label'],
    template: '<div><dt>{{ label }}</dt><dd><slot /></dd></div>',
  }),
  ElTag: defineComponent({ template: '<span><slot /></span>' }),
  ElAlert: defineComponent({
    props: ['title', 'type'],
    template: '<div :data-type="type">{{ title }}</div>',
  }),
  ElButton: defineComponent({
    emits: ['click'],
    template: '<button type="button" @click="$emit(\'click\')"><slot /></button>',
  }),
  ElRadioGroup: defineComponent({
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div><button type="button" class="radio-update" @click="$emit(\'update:modelValue\', \'blocking\')">切换筛选</button><slot /></div>',
  }),
  ElRadioButton: defineComponent({ template: '<span><slot /></span>' }),
  ElForm: defineComponent({ template: '<form><slot /></form>' }),
  ElFormItem: defineComponent({
    props: ['label'],
    template: '<label><span>{{ label }}</span><slot /></label>',
  }),
  ElSelect: defineComponent({
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<div><button type="button" class="select-update" @click="$emit(\'update:modelValue\', \'updated-value\')">更新选择</button><slot /></div>',
  }),
  ElOption: defineComponent({
    props: ['label'],
    template: '<div><slot>{{ label }}</slot></div>',
  }),
  ElInput: defineComponent({
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<button type="button" class="input-update" @click="$emit(\'update:modelValue\', \'secret-002\')">更新密钥</button>',
  }),
}

const nodeCandidate = {
  node_id: 'node-001',
  name: '线性回归',
  summary: '监督学习基础模型',
  validation_status: 'invalid',
  validation_errors: ['missing_summary'],
} as unknown as OverlayNodeCandidate

const edgeCandidate = {
  edge_id: 'edge-001',
  source_node_id: '机器学习导论',
  target_node_id: '线性回归',
  relation_type: 'REQUIRES',
  legality_rationale: '需要先理解基础概念',
  validation_status: 'valid',
  validation_errors: [],
} as unknown as OverlayEdgeCandidate

const resourceCandidate = {
  resource_id: 'resource-001',
  title: '线性回归教程',
  summary: '图文教程',
  resource_type: 'article',
  validation_status: 'needs_review',
  validation_errors: ['missing_evidence_source_id'],
  binding_summary: { count: 1 },
} as unknown as OverlayResourceCandidate

const session = {
  session: {
    session_id: 'session-001',
    session_status: 'validated',
  },
  sources: [{ source_id: 'source-001' }],
  nodes: [nodeCandidate],
  edges: [edgeCandidate],
  resources: [resourceCandidate],
  warnings: [],
} as unknown as OverlaySessionView

const goalDraft = {
  gap_analysis: {
    user_goal: '学习线性回归',
    why_current_graph_is_insufficient: '当前图谱缺少项目特定概念',
  },
  draft_metadata: {
    draft_engine: 'rules',
    prompt_version: 'v1',
    requires_user_review: true,
    can_directly_plan: false,
  },
} as unknown as GoalExtensionDraftResponse

function mountPanel(overrides: Partial<InstanceType<typeof OverlaySessionResultPanel>['$props']> = {}) {
  return mount(OverlaySessionResultPanel, {
    props: {
      session,
      showTechnicalDetails: true,
      showAuditDetails: true,
      overlaySessionGuide: '下一步：先修复失败候选。',
      overlaySessionStats: { valid: 1, invalid: 1, needsReview: 1, pendingReview: 2 },
      overlayCandidateDiagnostics: [
        {
          key: 'blocking',
          title: '先修复校验失败候选',
          description: '这些候选会阻塞增强图谱进入路径。',
          statusLabel: '需修复',
          actionLabel: '查看需修复',
          count: 1,
          filter: 'blocking',
          tagType: 'danger',
          firstTargetTitle: '线性回归',
          firstError: 'missing_summary',
        },
      ],
      overlayCandidateDiagnosticSummary: {
        severity: 'blocking',
        title: '先修复校验失败候选',
        description: '这些候选会阻塞增强图谱进入路径。 首个处理目标：线性回归。',
        statusLabel: '需修复',
        tagType: 'danger',
        primaryFilter: 'blocking',
        primaryActionLabel: '打开首个需处理候选',
        canOpenRepairTarget: true,
      },
      overlayWorkflowSteps: [
        { key: 'draft', title: '草稿创建', description: '生成候选', state: 'done', statusLabel: '已完成', tagType: 'success' },
        { key: 'review', title: '人工审核', description: '处理候选', state: 'current', statusLabel: '进行中', tagType: 'warning' },
      ],
      overlayWorkflowCurrentStep: { key: 'review', title: '人工审核', description: '处理候选', state: 'current', statusLabel: '进行中', tagType: 'warning' },
      overlayCandidateFilter: 'all',
      overlayCandidateFilterOptions: [
        { value: 'all', label: '全部' },
        { value: 'blocking', label: '需修复' },
      ],
      overlayCandidateFilterCounts: { all: 3, blocking: 1, review: 1, pending: 1, ready: 0 },
      filteredOverlayCandidateCount: 3,
      overlayBatchReviewLoading: false,
      overlayBatchConfirmableCount: 1,
      overlayBatchPlanningLoading: false,
      overlayBatchPlannableCount: 1,
      hasOverlayCandidateRepairTarget: true,
      overlayCandidateRepairTargetLabel: '打开首个需处理候选：线性回归',
      filteredOverlayNodes: [nodeCandidate],
      filteredOverlayEdges: [edgeCandidate],
      filteredOverlayResources: [resourceCandidate],
      goalExtensionDraftDetails: goalDraft,
      goalDraftMissingConcepts: ['线性回归'],
      goalDraftReviewNotes: ['请确认概念范围'],
      goalDraftReviewFocus: ['机器学习基础边界'],
      validationErrorMessage: (error: string) => `提示：${error}`,
      resourceBinding: { resourceId: 'resource-001', targetType: 'project_node', targetId: 'node-001' },
      resourceTargetOptions: [{ id: 'node-001', label: '线性回归' }],
      promotionPreview: {
        status: 'ready',
        candidate_count: 2,
        baseline_pack_hash: 'hash-old',
        resulting_pack_hash: 'hash-new',
        resources: [{ id: 'resource-001', title: '线性回归教程', resource_type: 'article', node_ids: [], stage_ids: [] }],
        errors: ['dry-run warning'],
      },
      promotionResult: { status: 'promoted', reason: 'promoted' },
      promotionSecret: 'secret-001',
      promotionLoading: false,
      promotionStatusMessage: '推广成功，候选已归档隐藏。',
      ...overrides,
    },
    global: {
      stubs: elementPlusStubs,
    },
  })
}

describe('OverlaySessionResultPanel', () => {
  it('renders session summary, workflow, candidates and goal draft details', () => {
    const wrapper = mountPanel()

    expect(wrapper.text()).toContain('抽取结果')
    expect(wrapper.text()).toContain('追溯编号：session-001')
    expect(wrapper.text()).toContain('通过 1，失败 1，待复核 1，待审核 2')
    expect(wrapper.text()).toContain('当前阶段：人工审核')
    expect(wrapper.text()).toContain('先修复校验失败候选')
    expect(wrapper.text()).toContain('首个目标：线性回归')
    expect(wrapper.text()).toContain('候选处理队列')
    expect(wrapper.text()).toContain('线性回归')
    expect(wrapper.text()).toContain('机器学习导论 → 线性回归')
    expect(wrapper.text()).toContain('线性回归教程')
    expect(wrapper.text()).toContain('目标缺口分析')
    expect(wrapper.text()).toContain('当前图谱缺少项目特定概念')
  })

  it('forwards candidate repair and filter events', async () => {
    const wrapper = mountPanel()
    const buttons = wrapper.findAll('button')

    await buttons.find((button) => button.text().includes('打开首个需处理候选'))?.trigger('click')
    await buttons.find((button) => button.text() === '批量确认待审核 1')?.trigger('click')
    await buttons.find((button) => button.text() === '批量纳入规划 1')?.trigger('click')
    await buttons.find((button) => button.text() === '编辑修复')?.trigger('click')
    await wrapper.find('.radio-update').trigger('click')

    expect(wrapper.emitted('open-first-repairable')).toHaveLength(1)
    expect(wrapper.emitted('confirm-valid-candidates')).toHaveLength(1)
    expect(wrapper.emitted('enable-confirmed-planning')).toHaveLength(1)
    expect(wrapper.emitted('edit-node')).toEqual([[nodeCandidate]])
    expect(wrapper.emitted('update:overlayCandidateFilter')).toEqual([['blocking']])
  })

  it('forwards resource binding and promotion events', async () => {
    const wrapper = mountPanel()

    await wrapper.findAll('.select-update')[0].trigger('click')
    await wrapper.find('.input-update').trigger('click')
    await wrapper.findAll('button').find((button) => button.text() === '绑定资源')?.trigger('click')
    await wrapper.findAll('button').find((button) => button.text() === '预览推广结果（不写入）')?.trigger('click')
    await wrapper.findAll('button').find((button) => button.text() === '确认推广')?.trigger('click')

    expect(wrapper.emitted('update-resource-binding')).toEqual([['resourceId', 'updated-value']])
    expect(wrapper.emitted('update:promotionSecret')).toEqual([['secret-002']])
    expect(wrapper.emitted('bind-resource')).toHaveLength(1)
    expect(wrapper.emitted('preview-promotion')).toHaveLength(1)
    expect(wrapper.emitted('commit-promotion')).toHaveLength(1)
    expect(wrapper.text()).toContain('推广成功，候选已归档隐藏。')
  })

  it('shows an empty filter hint when the current filter has no candidates', () => {
    const wrapper = mountPanel({ filteredOverlayCandidateCount: 0 })

    expect(wrapper.text()).toContain('当前筛选下暂无候选')
  })
})
