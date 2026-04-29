import { defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { AuditHighlight, ExplanationReadability, ExplanationResponse } from '@/api/modules/plan'
import Explanation from './Explanation.vue'
import { useExplanationState } from './useExplanationState'

const {
  planApiGetExplanationMock,
  planApiAskExplanationMock,
} = vi.hoisted(() => ({
  planApiGetExplanationMock: vi.fn(),
  planApiAskExplanationMock: vi.fn(),
}))

vi.mock('@/api/modules/plan', () => ({
  planApi: {
    getExplanation: planApiGetExplanationMock,
    askExplanation: planApiAskExplanationMock,
  },
}))

const slotStub = (tag: string) => defineComponent({
  props: ['title', 'description', 'type', 'disabled', 'loading', 'modelValue'],
  template: `
    <${tag} :disabled="disabled">
      <slot name="header" />
      <span v-if="title">{{ title }}</span>
      <span v-if="description">{{ description }}</span>
      <slot />
    </${tag}>
  `,
})

const tagStub = defineComponent({
  props: ['type', 'disabled', 'loading', 'modelValue'],
  template: '<span :disabled="disabled"><slot /></span>',
})

const buttonStub = defineComponent({
  props: ['disabled', 'loading'],
  emits: ['click'],
  template: '<button :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>',
})

const switchStub = defineComponent({
  props: ['modelValue', 'activeText'],
  emits: ['change'],
  template: '<button class="polish-switch" @click="$emit(\'change\', !modelValue)">{{ activeText }}</button>',
})

const globalMountOptions = {
  directives: {
    loading: () => undefined,
  },
  stubs: {
    ElAlert: slotStub('div'),
    ElButton: buttonStub,
    ElCard: slotStub('section'),
    ElCol: slotStub('div'),
    ElCollapse: slotStub('div'),
    ElCollapseItem: slotStub('article'),
    ElEmpty: slotStub('div'),
    ElRow: slotStub('div'),
    ElSwitch: switchStub,
    ElTag: tagStub,
    ElTimeline: slotStub('div'),
    ElTimelineItem: slotStub('div'),
  },
}

function createBaseReadability(): ExplanationReadability {
  return {
    overview_summary: {
      headline: '系统按目标、前置依赖和时间预算生成路径。',
      goal_names: ['机器学习基础'],
      node_count: 1,
      total_hours: 6,
      budget_status: 'feasible',
      path_mode: 'standard',
      notes: [],
    },
    goal_resolution_summary: {
      target_node_ids: ['ml-c01'],
      target_node_names: ['机器学习概览'],
      source_breakdown: {},
      warnings: [],
    },
    generation_steps: [
      {
        step_id: 'goal',
        title: '解析目标',
        summary: '识别目标节点。',
        evidence_items: ['goal_text'],
        node_ids: ['ml-c01'],
      },
    ],
    node_groups: [
      {
        group_id: 'target',
        title: '目标节点',
        summary: '直接对应目标。',
        node_ids: ['ml-c01'],
        nodes: [
          {
            node_id: 'ml-c01',
            node_name: '机器学习概览',
            reason: '目标命中',
          },
        ],
      },
    ],
    ordering_summary: {
      summary: '先学概览。',
      ordered_node_ids: ['ml-c01'],
      key_factors: ['目标相关度'],
    },
    stage_summary: {
      summary: '放在基础阶段。',
      stage_count: 1,
      stages: [
        {
          key: 'stage-1',
          stage_name: '基础阶段',
          summary: '建立基础。',
        },
      ],
    },
    budget_summary: {
      summary: '预算可行。',
      total_hours: 6,
      weekly_hours: 3,
      estimated_weeks: 2,
      status: 'feasible',
      path_mode: 'standard',
      compressed_dependency_note: null,
    },
    trace_summary: {
      overlay_node_count: 0,
      overlay_edge_count: 0,
      overlay_lineage_items: [],
      fallback_used: false,
      fallback_reasons: [],
      live_pack_fields: [],
    },
    audit_highlights: [],
  }
}

function createExplanationResponse(overrides: Partial<ExplanationResponse> = {}): ExplanationResponse {
  return {
    node_explanations: [],
    ordering_explanations: [],
    stage_explanations: [],
    budget_explanation: null,
    reinforcement_explanations: [],
    dependency_chain_explanations: [],
    readability: createBaseReadability(),
    meta: {
      provenance: {
        truth_source: 'plan_audit_snapshot',
        fallback_used: false,
        fallback_reasons: [],
        live_pack_fields: [],
      },
      polish: {
        requested: false,
        applied: false,
        scope: [],
        fallback_reason: null,
      },
    },
    ...overrides,
  }
}

function mountExplanation(props: Record<string, any> = {}) {
  return mount(Explanation, {
    props: {
      explanation: createExplanationResponse(),
      loading: false,
      error: '',
      polishRequested: false,
      displayMode: 'simple',
      aiAvailability: {
        llmApiKeySet: true,
        polishEnabled: true,
        polishAvailable: true,
      },
      askResponse: null,
      askLoading: false,
      askError: '',
      ...props,
    },
    global: globalMountOptions,
  })
}

function createDeferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: any) => void
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve
    reject = nextReject
  })
  return { promise, resolve, reject }
}

function mountExplanationState() {
  return mount(defineComponent({
    setup(_, { expose }) {
      const projectId = ref<string | undefined>('project-001')
      const state = useExplanationState(projectId)
      expose({ projectId, ...state })
      return () => null
    },
  }))
}

function mountExplanationStateWithScope(scope = 'plan-001') {
  return mount(defineComponent({
    setup(_, { expose }) {
      const projectId = ref<string | undefined>('project-001')
      const scopeId = ref<string | undefined>(scope)
      const state = useExplanationState(projectId, scopeId)
      expose({ projectId, scopeId, ...state })
      return () => null
    },
  }))
}

describe('Explanation component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the same DOM for the same props and does not trigger explanation requests', () => {
    const props = {
      explanation: createExplanationResponse(),
      polishRequested: true,
    }

    const first = mountExplanation(props)
    const second = mountExplanation(props)

    expect(second.html()).toBe(first.html())
    expect(planApiGetExplanationMock).not.toHaveBeenCalled()
    expect(planApiAskExplanationMock).not.toHaveBeenCalled()
  })

  it('renders a defense-friendly guide before detailed explanation cards', () => {
    const wrapper = mountExplanation()

    expect(wrapper.text()).toContain('答辩导览')
    expect(wrapper.text()).toContain('路径为何成立')
    expect(wrapper.text()).toContain('系统按目标、前置依赖和时间预算生成路径。')
    expect(wrapper.text()).toContain('目标锁定')
    expect(wrapper.text()).toContain('机器学习基础')
    expect(wrapper.text()).toContain('依赖闭包')
    expect(wrapper.text()).toContain('0 个前置')
    expect(wrapper.text()).toContain('画像补强')
    expect(wrapper.text()).toContain('0 个补强')
    expect(wrapper.text()).toContain('阶段与预算')
    expect(wrapper.text()).toContain('1 阶段 / 6 小时')
    expect(wrapper.text()).toContain('推荐讲述顺序')
    expect(wrapper.text()).toContain('先说明学习目标如何映射到目标知识点')
  })

  it('shows AI polish waiting feedback while polished explanation is loading', () => {
    const wrapper = mountExplanation({
      loading: true,
      polishRequested: true,
      explanation: createExplanationResponse(),
    })

    expect(wrapper.text()).toContain('正在润色路径解释')
    expect(wrapper.text()).toContain('您可以先继续阅读下方规则文本')
    expect(wrapper.find('.polish-loading-card').exists()).toBe(true)
  })

  it('shows initial skeleton when polish loads before explanation exists', () => {
    const wrapper = mountExplanation({
      loading: true,
      polishRequested: true,
      explanation: null,
    })

    expect(wrapper.text()).toContain('AI 润色最长可能需要约 1 分钟')
    expect(wrapper.find('.polish-skeleton').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('路径解释摘要')
  })

  it('labels polish from response meta instead of the requested flag', () => {
    const wrapper = mountExplanation({
      polishRequested: true,
      explanation: createExplanationResponse({
        meta: {
          provenance: {
            truth_source: 'plan_audit_snapshot',
            fallback_used: false,
            fallback_reasons: [],
            live_pack_fields: [],
          },
          polish: {
            requested: true,
            applied: false,
            scope: [],
            fallback_reason: 'missing_api_key',
          },
        },
      }),
    })

    expect(wrapper.text()).toContain('本次未应用 AI 润色')
    expect(wrapper.text()).toContain('未配置 LLM_API_KEY')
    expect(wrapper.text()).toContain('规则文本')
    expect(wrapper.text()).not.toContain('本次已应用 AI 润色')
  })

  it('shows generation step node names before internal trace IDs in defense mode', () => {
    const wrapper = mountExplanation({ displayMode: 'defense' })

    expect(wrapper.text()).toContain('机器学习概览')
    expect(wrapper.text()).toContain('内部节点 ID 可通过悬停查看')
    expect(wrapper.text()).not.toContain('未识别知识点（ml-c01）')
    expect(wrapper.find('.node-name-tag').attributes('title')).toBe('节点 ID：ml-c01')
  })

  it('renders audit sources as readable labels while keeping raw source traceable', () => {
    const wrapper = mountExplanation({
      explanation: createExplanationResponse({
        readability: {
          ...createBaseReadability(),
          audit_highlights: [
            {
              key: 'priority',
              title: '优先级依据',
              summary: '目标相关度最高。',
              source: 'audit.ordering_logs',
              value: {
                ordered_node_ids: ['ml-c01'],
              },
            },
          ],
        },
      }),
      displayMode: 'debug',
      askResponse: {
        question_id: 'why_path_order',
        answer: '因为依赖约束优先。',
        evidence_refs: [
          {
            source: 'audit.ordering_logs',
            key: 'ml-c01',
            node_id: 'ml-c01',
          },
        ],
        limitations: [],
        ai_used: false,
      },
    })

    expect(wrapper.text()).toContain('来源：排序审计记录')
    expect(wrapper.text()).toContain('排序审计记录')
    expect(wrapper.text()).not.toContain('来源：audit.ordering_logs')
  })

  it('shows raw rule text comparison only in debug mode', () => {
    const explanation = createExplanationResponse({
      node_explanations: [
        {
          node_id: 'ml-c01',
          node_name: '机器学习概览',
          reason: '润色后的纳入理由',
          raw_reason: '规则原始纳入理由',
          decision_type: 'target',
        },
      ],
      stage_explanations: [
        {
          node_id: 'ml-c01',
          node_name: '机器学习概览',
          assigned_stage: '基础阶段',
          reasons: ['基础类别'],
          rationale: '润色后的阶段说明',
          raw_rationale: '规则原始阶段说明',
        },
      ],
    })

    const defenseWrapper = mountExplanation({ displayMode: 'defense', explanation })
    expect(defenseWrapper.text()).not.toContain('原始规则文本对照')
    expect(defenseWrapper.text()).not.toContain('规则原始纳入理由')

    const debugWrapper = mountExplanation({ displayMode: 'debug', explanation })
    expect(debugWrapper.text()).toContain('原始规则文本对照')
    expect(debugWrapper.text()).toContain('节点纳入原因：机器学习概览')
    expect(debugWrapper.text()).toContain('阶段划分说明：机器学习概览')
    expect(debugWrapper.text()).toContain('当前展示：润色后的纳入理由')
    expect(debugWrapper.text()).toContain('规则原始纳入理由')
    expect(debugWrapper.text()).toContain('规则原始阶段说明')
  })

  it('keeps advanced audit collapsed in debug mode and ignores unknown DTO fields', () => {
    const wrapper = mountExplanation({
      displayMode: 'debug',
      explanation: createExplanationResponse({
        readability: {
          ...createBaseReadability(),
          audit_highlights: [
            {
              key: 'priority',
              title: '优先级依据',
              summary: '目标相关度最高。',
              source: 'audit.ordering_logs',
              value: {
                stable_field: '稳定 DTO 字段',
              },
              ignored_backend_field: '不要渲染这个字段',
            } as AuditHighlight,
          ],
        },
      }),
    })

    expect((wrapper.vm as any).activeAuditPanels).toEqual([])
    expect(wrapper.text()).toContain('高级审计依据')
    expect(wrapper.text()).toContain('优先级依据')
    expect(wrapper.text()).toContain('目标相关度最高。')
    expect(wrapper.text()).not.toContain('不要渲染这个字段')
  })

  it('shows only preset Q&A entries when no node target exists and renders node limitations', async () => {
    const wrapper = mountExplanation({
      explanation: createExplanationResponse({
        readability: {
          ...createBaseReadability(),
          node_groups: [],
        },
        node_explanations: [],
      }),
      askResponse: {
        question_id: 'why_include_node',
        answer: '缺少 node_id，无法定位具体知识点。',
        evidence_refs: [],
        limitations: ['请选择具体知识点后再询问。'],
        ai_used: false,
      },
    })

    const questions = wrapper.findAll('.question-grid button')
    expect(questions).toHaveLength(3)
    expect(wrapper.text()).toContain('为什么按这个顺序学习？')
    expect(wrapper.text()).toContain('当前时间预算是否可行？')
    expect(wrapper.text()).toContain('如果时间不够怎么办？')
    expect(wrapper.find('.node-question-list').exists()).toBe(false)
    expect(wrapper.text()).toContain('请选择具体知识点后再询问。')
  })
})

describe('useExplanationState', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('does not cache failed polish fallback responses in memory', async () => {
    const fallbackResponse = createExplanationResponse({
      meta: {
        provenance: {
          truth_source: 'plan_audit_snapshot',
          fallback_used: false,
          fallback_reasons: [],
          live_pack_fields: [],
        },
        polish: {
          requested: true,
          applied: false,
          scope: [],
          fallback_reason: 'timeout',
        },
      },
      node_explanations: [
        {
          node_id: 'fallback-node',
          node_name: 'Fallback',
          reason: 'fallback',
          decision_type: 'target',
        },
      ],
    })
    planApiGetExplanationMock.mockResolvedValueOnce(fallbackResponse)

    const firstWrapper = mountExplanationStateWithScope('plan-failed-polish-cache')
    const firstVm = firstWrapper.vm as any
    await firstVm.load(true)
    await flushPromises()
    expect(firstVm.explanation.node_explanations[0].node_id).toBe('fallback-node')

    const deferred = createDeferred<any>()
    planApiGetExplanationMock.mockImplementationOnce(() => deferred.promise)
    const secondWrapper = mountExplanationStateWithScope('plan-failed-polish-cache')
    const secondVm = secondWrapper.vm as any
    const reload = secondVm.load(true)
    await flushPromises()

    expect(secondVm.explanation).toBeNull()

    deferred.resolve(createExplanationResponse())
    await reload
  })

  it('shows actionable timeout copy when polished explanation exceeds request budget', async () => {
    planApiGetExplanationMock.mockRejectedValueOnce({
      code: 'ECONNABORTED',
      message: 'timeout of 30000ms exceeded',
    })

    const wrapper = mountExplanationState()
    const vm = wrapper.vm as any

    await vm.load(true)
    await flushPromises()

    expect(vm.error).toContain('AI 润色超时')
    expect(vm.error).toContain('关闭 AI 润色')
    expect(vm.loading).toBe(false)
  })

  it('suppresses stale responses without overriding explanation, loading, or error', async () => {
    const requestA = createDeferred<any>()
    const requestB = createDeferred<any>()
    planApiGetExplanationMock
      .mockImplementationOnce(() => requestA.promise)
      .mockImplementationOnce(() => requestB.promise)

    const wrapper = mountExplanationState()
    const vm = wrapper.vm as any

    const loadA = vm.load(false)
    const loadB = vm.load(true)

    requestB.resolve(createExplanationResponse({
      meta: {
        provenance: {
          truth_source: 'plan_audit_snapshot',
          fallback_used: false,
          fallback_reasons: [],
          live_pack_fields: [],
        },
        polish: {
          requested: true,
          applied: true,
          scope: ['node:ml-c01'],
          fallback_reason: null,
        },
      },
      node_explanations: [
        {
          node_id: 'node-b',
          node_name: 'B',
          reason: 'newest',
          decision_type: 'target',
        },
      ],
    }))
    await loadB
    await flushPromises()

    expect(vm.explanation.meta.polish.applied).toBe(true)
    expect(vm.explanation.node_explanations[0].node_id).toBe('node-b')
    expect(vm.loading).toBe(false)
    expect(vm.error).toBe('')

    requestA.reject({ response: { data: { error: 'stale failed' } } })
    await loadA
    await flushPromises()

    expect(vm.explanation.meta.polish.applied).toBe(true)
    expect(vm.explanation.node_explanations[0].node_id).toBe('node-b')
    expect(vm.loading).toBe(false)
    expect(vm.error).toBe('')
  })
})
