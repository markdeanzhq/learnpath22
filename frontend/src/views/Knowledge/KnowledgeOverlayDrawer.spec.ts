import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import KnowledgeOverlayDrawer from './KnowledgeOverlayDrawer.vue'
import type {
  GoalExtensionDraftResponse,
  OverlayEdgeCandidate,
  OverlayExtractionPayloadPreviewResponse,
  OverlayNodeCandidate,
  OverlayResourceCandidate,
} from '@/api/modules/graph'
import type { OverlaySessionView } from './composables/useOverlayCandidateWorkflow'
import { createOverlayForm } from './composables/useOverlayDraftInput'

const elementPlusStubs = {
  DisplayModeSwitch: defineComponent({
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<button type="button" class="display-mode-update" @click="$emit(\'update:modelValue\', \'debug\')">切换显示模式</button>',
  }),
  ElDrawer: defineComponent({ template: '<section><slot /></section>' }),
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
    props: ['disabled'],
    emits: ['click'],
    template: '<button type="button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
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
    template: '<button type="button" class="input-update" @click="$emit(\'update:modelValue\', \'secret-002\')">更新输入</button>',
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

const preview: OverlayExtractionPayloadPreviewResponse = {
  source_ids: ['source-001'],
  mode: 'default',
  extraction_payload: {},
  warnings: [],
  counts: { nodes: 1, edges: 0, resources: 0 },
  provenance: {},
}

function mountDrawer() {
  return mount(KnowledgeOverlayDrawer, {
    props: {
      visible: true,
      displayMode: 'simple',
      overlaySubmitting: false,
      overlayExtractionPreviewLoading: false,
      overlayAutoDraftLoading: false,
      activeGoalDraftResolutionSessionId: null,
      manualGoalDraftLoading: false,
      goalDraftProposalLoading: false,
      goalDraftInboxProposal: null,
      goalDraftProposalDismissed: false,
      goalDraftInboxMissingConcepts: [],
      goalDraftInboxCounts: { nodes: 0, edges: 0, resources: 0 },
      goalDraftInboxNodes: [],
      goalDraftInboxEdges: [],
      goalDraftInboxResources: [],
      overlayDraftMode: 'manual',
      overlayForm: createOverlayForm(),
      manualOverlayMode: true,
      overlaySearchQuery: '随机森林',
      overlaySearchResults: [
        { title: '随机森林入门', url: 'https://example.com/random-forest', snippet: '随机森林是基于决策树的集成学习方法', score: 0.92, provider: 'tavily' },
      ],
      overlaySearchLoading: false,
      overlaySearchError: '',
      overlayAddingSearchUrl: '',
      persistedSearchResults: [],
      overlayBridgeMessage: '',
      overlayExtractionPreview: preview,
      normalizedPreviewPayload: {
        nodes: [{ name: '线性回归', summary: '监督学习基础模型' }],
        edges: [],
        resources: [],
        warnings: [],
      },
      selectedPreviewCounts: { nodes: 1, edges: 0, resources: 0 },
      overlayCandidateValidation: null,
      isPreviewCandidateSelected: (group, index) => group === 'nodes' && index === 0,
      candidateTitle: (candidate, fallback) => candidate.name || candidate.title || fallback,
      edgeCandidateSummary: (candidate) => `${candidate.source_node_id || '未知来源'} → ${candidate.target_node_id || '未知目标'}`,
      overlayError: '',
      lastOverlaySession: session,
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
      validationErrorMessage: (error) => `提示：${error}`,
      resourceBinding: { resourceId: 'resource-001', targetType: 'project_node', targetId: 'node-001' },
      resourceTargetOptions: [{ id: 'node-001', label: '线性回归' }],
      promotionPreview: {
        status: 'ready',
        candidate_count: 2,
        baseline_pack_hash: 'hash-old',
        resulting_pack_hash: 'hash-new',
        resources: [{ id: 'resource-001', title: '线性回归教程', resource_type: 'article', node_ids: [], stage_ids: [] }],
        errors: [],
      },
      promotionResult: { status: 'promoted', reason: 'promoted' },
      promotionSecret: 'secret-001',
      promotionLoading: false,
      promotionStatusMessage: '推广成功，候选已归档隐藏。',
    },
    global: {
      directives: {
        loading: () => undefined,
      },
      stubs: elementPlusStubs,
    },
  })
}

describe('KnowledgeOverlayDrawer', () => {
  it('forwards the overlay preview to session repair and binding event chain', async () => {
    const wrapper = mountDrawer()

    await wrapper.findAll('button').find((button) => button.text() === '生成候选预览')?.trigger('click')
    await wrapper.findAll('input[type="checkbox"]')[0].setValue(false)
    await wrapper.findAll('button').find((button) => button.text() === '编辑修复')?.trigger('click')
    await wrapper.findAll('button').find((button) => button.text() === '批量确认待审核 1')?.trigger('click')
    await wrapper.findAll('button').find((button) => button.text() === '批量纳入规划 1')?.trigger('click')
    await wrapper.findAll('.select-update')[0].trigger('click')
    await wrapper.findAll('button').find((button) => button.text() === '绑定资源')?.trigger('click')
    const inputButtons = wrapper.findAll('.input-update')
    await inputButtons[inputButtons.length - 1].trigger('click')

    expect(wrapper.emitted('preview-overlay-extraction-payload')).toHaveLength(1)
    expect(wrapper.emitted('toggle-preview-candidate')).toEqual([['nodes', 0, false]])
    expect(wrapper.emitted('edit-node')).toEqual([[nodeCandidate]])
    expect(wrapper.emitted('confirm-valid-candidates')).toHaveLength(1)
    expect(wrapper.emitted('enable-confirmed-planning')).toHaveLength(1)
    expect(wrapper.emitted('update-resource-binding')).toEqual([['resourceId', 'updated-value']])
    expect(wrapper.emitted('bind-resource')).toHaveLength(1)
    expect(wrapper.emitted('update:promotionSecret')).toEqual([['secret-002']])
  })

  it('updates display mode, candidate filter, search query and overlay form through explicit events', async () => {
    const wrapper = mountDrawer()

    await wrapper.find('.display-mode-update').trigger('click')
    await wrapper.findAll('.radio-update')[2].trigger('click')
    await wrapper.findAll('.input-update')[0].trigger('click')
    await wrapper.findAll('.input-update')[1].trigger('click')

    expect(wrapper.emitted('update:displayMode')).toEqual([['debug']])
    expect(wrapper.emitted('update:overlayCandidateFilter')).toEqual([['blocking']])
    expect(wrapper.emitted('update:overlaySearchQuery')).toEqual([['secret-002']])
    expect(wrapper.emitted('update-overlay-form')?.[0][0]).toEqual(expect.objectContaining({ constraintNote: 'secret-002' }))
  })

  it('shows guidance and forwards embedded search actions', async () => {
    const wrapper = mountDrawer()

    expect(wrapper.text()).toContain('推荐流程')
    expect(wrapper.text()).toContain('资料转图谱候选')
    expect(wrapper.text()).toContain('项目资料库负责保存历史')
    expect(wrapper.text()).toContain('搜索来源并生成候选草稿')
    expect(wrapper.text()).toContain('手动资料补充指南')
    expect(wrapper.text()).toContain('适合粘贴教程片段')
    expect(wrapper.text()).toContain('先修复校验失败候选')
    expect(wrapper.text()).toContain('首个目标：线性回归')
    expect(wrapper.text()).toContain('随机森林入门')

    await wrapper.findAll('button').find((button) => button.text() === '搜索来源并生成候选草稿')?.trigger('click')
    await wrapper.findAll('button').find((button) => button.text() === '搜索草稿来源')?.trigger('click')
    await wrapper.findAll('button').find((button) => button.text() === '加入草稿来源')?.trigger('click')

    expect(wrapper.emitted('create-auto-draft')).toHaveLength(1)
    expect(wrapper.emitted('search-overlay-results')).toHaveLength(1)
    expect(wrapper.emitted('add-search-result-to-overlay')).toEqual([[
      { title: '随机森林入门', url: 'https://example.com/random-forest', snippet: '随机森林是基于决策树的集成学习方法', score: 0.92, provider: 'tavily' },
      0,
    ]])
  })
})
