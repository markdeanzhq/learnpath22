import { defineComponent } from 'vue'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import KnowledgeIndex from './index.vue'

const {
  graphGetGraphMock,
  graphCreateOverlaySourceMock,
  graphCreateOverlayExtractionSessionMock,
  graphPreviewOverlayExtractionPayloadMock,
  graphCreateGoalExtensionDraftMock,
  graphGetGoalExtensionDraftProposalMock,
  graphSetOverlayPlanningMock,
  graphReviewOverlayElementMock,
  confirmMock,
  graphGetOverlayExtractionSessionMock,
  graphPreviewOverlayPromotionMock,
  graphCommitOverlayPromotionMock,
  graphGetOverlayProjectionStatusMock,
  graphGetOverlayPreflightMock,
  searchListPersistedResultsMock,
  searchBridgeOverlaySourcesMock,
  resourceBindProjectResourceMock,
  projectPreviewForProjectMock,
  currentProjectState,
  routeState,
  replaceMock,
  successMock,
} = vi.hoisted(() => ({
  graphGetGraphMock: vi.fn(),
  graphCreateOverlaySourceMock: vi.fn(),
  graphCreateOverlayExtractionSessionMock: vi.fn(),
  graphPreviewOverlayExtractionPayloadMock: vi.fn(),
  graphCreateGoalExtensionDraftMock: vi.fn(),
  graphGetGoalExtensionDraftProposalMock: vi.fn(),
  graphSetOverlayPlanningMock: vi.fn(),
  graphReviewOverlayElementMock: vi.fn(),
  confirmMock: vi.fn(),
  graphGetOverlayExtractionSessionMock: vi.fn(),
  graphPreviewOverlayPromotionMock: vi.fn(),
  graphCommitOverlayPromotionMock: vi.fn(),
  graphGetOverlayProjectionStatusMock: vi.fn(),
  graphGetOverlayPreflightMock: vi.fn(),
  searchListPersistedResultsMock: vi.fn(),
  searchBridgeOverlaySourcesMock: vi.fn(),
  resourceBindProjectResourceMock: vi.fn(),
  projectPreviewForProjectMock: vi.fn(),
  currentProjectState: {
    value: {
      id: 'project-001',
      title: '机器学习基础学习计划',
      goal_text: '我想系统学习机器学习基础',
      goal_type: 'domain',
      domain: 'machine_learning',
      status: 'draft',
      created_at: '2026-04-22T09:00:00Z',
      updated_at: '2026-04-22T09:00:00Z',
    },
  },
  routeState: {
    query: {} as Record<string, string>,
  },
  replaceMock: vi.fn((location: any) => {
    routeState.query = location.query ?? {}
    return Promise.resolve()
  }),
  successMock: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ replace: replaceMock }),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: successMock,
    error: vi.fn(),
  },
  ElMessageBox: {
    confirm: confirmMock,
  },
}))

vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({
    get currentProject() {
      return currentProjectState.value
    },
  }),
}))

vi.mock('@/api/modules/graph', () => {
  const buildGraphQuery = (params: any = {}) => {
    const scope = ['domain', 'project', 'path'].includes(params.scope) ? params.scope : 'path'
    const query: any = { scope }
    if (scope === 'path') query.path_id = params.path_id || 'latest'
    if (params.nodeId) query.nodeId = params.nodeId
    return query
  }

  return {
    buildGraphQuery,
    normalizeGraphScope: (value: any) => {
      const nextValue = Array.isArray(value) ? value[0] : value
      return nextValue === 'domain' || nextValue === 'project' || nextValue === 'path' ? nextValue : 'path'
    },
    normalizeGraphPathId: (scope: string, value: any) => {
      const nextValue = Array.isArray(value) ? value[0] : value
      if (scope !== 'path') return undefined
      return typeof nextValue === 'string' && nextValue.trim() ? nextValue.trim() : 'latest'
    },
    graphApi: {
    getGraph: graphGetGraphMock,
    syncGraph: vi.fn(),
    getGraphEntities: vi.fn(),
    reviewNode: vi.fn(),
    reviewEdge: vi.fn(),
    createOverlaySource: graphCreateOverlaySourceMock,
    previewOverlayExtractionPayload: graphPreviewOverlayExtractionPayloadMock,
    createOverlayExtractionSession: graphCreateOverlayExtractionSessionMock,
    getGoalExtensionDraftProposal: graphGetGoalExtensionDraftProposalMock,
    createGoalExtensionDraft: graphCreateGoalExtensionDraftMock,
    setOverlayPlanning: graphSetOverlayPlanningMock,
    getOverlayExtractionSession: graphGetOverlayExtractionSessionMock,
    reviewOverlayElement: graphReviewOverlayElementMock,
    previewOverlayPromotion: graphPreviewOverlayPromotionMock,
    commitOverlayPromotion: graphCommitOverlayPromotionMock,
    getOverlayProjectionStatus: graphGetOverlayProjectionStatusMock,
    getOverlayPreflight: graphGetOverlayPreflightMock,
    },
  }
})

vi.mock('@/api/modules/search', () => ({
  searchApi: {
    listPersistedResults: searchListPersistedResultsMock,
    bridgeOverlaySources: searchBridgeOverlaySourcesMock,
  },
}))

vi.mock('@/api/modules/project', () => ({
  projectApi: {
    previewForProject: projectPreviewForProjectMock,
  },
}))

vi.mock('@/api/modules/resource', () => ({
  resourceApi: {
    bindProjectResource: resourceBindProjectResourceMock,
  },
}))

const slotStub = (tag: string) => defineComponent({
  template: `<${tag}><slot /></${tag}>`,
})

const graphToolbarStub = defineComponent({
  emits: ['create-overlay'],
  template: '<button data-testid="create-overlay" @click="$emit(\'create-overlay\')">create</button>',
})

function mountKnowledge() {
  return shallowMount(KnowledgeIndex, {
    global: {
      directives: {
        loading: () => undefined,
      },
      stubs: {
        GraphToolbar: graphToolbarStub,
        GraphCanvas: slotStub('div'),
        NodeDetail: slotStub('div'),
        EntityMetadataDrawer: slotStub('div'),
        ElCard: slotStub('section'),
        ElSpace: slotStub('div'),
        ElButton: slotStub('button'),
        ElButtonGroup: slotStub('div'),
        ElEmpty: slotStub('div'),
        ElResult: slotStub('div'),
        ElAlert: slotStub('div'),
        ElDrawer: slotStub('div'),
        ElForm: slotStub('form'),
        ElFormItem: slotStub('div'),
        ElRadioGroup: slotStub('div'),
        ElRadioButton: slotStub('button'),
        ElInput: slotStub('input'),
        ElSelect: slotStub('select'),
        ElOption: slotStub('option'),
        ElDescriptions: slotStub('div'),
        ElDescriptionsItem: slotStub('div'),
        ElTag: slotStub('span'),
      },
    },
  })
}

describe('Knowledge overlay entry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routeState.query = {}
    confirmMock.mockResolvedValue('confirm')
    graphGetGraphMock.mockResolvedValue({
      scope: 'path',
      elements: [],
      is_empty: true,
    })
    graphCreateOverlaySourceMock.mockResolvedValue({ source_id: 'src-001' })
    graphPreviewOverlayExtractionPayloadMock.mockImplementation((_projectId: string, payload: any) => Promise.resolve({
      source_ids: payload.source_ids,
      mode: payload.mode || 'default',
      extraction_payload: {
        nodes: [],
        edges: [],
        resources: [],
        warnings: ['llm_generated'],
      },
      warnings: ['llm_generated'],
      counts: { nodes: 0, edges: 0, resources: 0 },
      provenance: {
        draft_origin: 'llm_overlay_extraction',
        prompt_version: 'overlay-extraction-v1',
      },
    }))
    const sessionResponse = {
      session: {
        session_id: 'sess-001',
        project_id: 'project-001',
        mode: 'default',
        session_status: 'validated',
        source_ids: ['src-001'],
        warnings: [],
        created_at: '2026-04-22T09:00:00Z',
        updated_at: '2026-04-22T09:00:00Z',
      },
      sources: [],
      nodes: [],
      edges: [],
      resources: [],
      warnings: [],
    }
    graphCreateOverlayExtractionSessionMock.mockResolvedValue(sessionResponse)
    graphCreateGoalExtensionDraftMock.mockResolvedValue(sessionResponse)
    const draftProposalResponse = {
      resolution_session_id: 'resolution-001',
      project_id: 'project-001',
      session_status: 'draft_previewed',
      expires_at: '2026-04-22T10:00:00Z',
      draft_proposal: {
        missing_concepts: ['随机森林'],
        nodes: [{ name: '随机森林', summary: '系统推荐节点候选' }],
        edges: [{ source_name_or_id: '随机森林', target_node_id: 'ml_c12', relation_type: 'RELATED_TO', legality_rationale: '关联决策树基础' }],
        resources: [],
        counts: { nodes: 1, edges: 1, resources: 0 },
        warnings: ['goal_extension_draft_requires_review'],
        requires_user_review: true,
        writes_formal_graph: false,
        writes_formal_path: false,
      },
    }
    graphGetGoalExtensionDraftProposalMock.mockResolvedValue(draftProposalResponse)
    projectPreviewForProjectMock.mockResolvedValue({
      result_type: 'review_extension_draft',
      coverage_status: 'in_domain_uncovered',
      session_id: 'resolution-001',
      expires_at: '2026-04-22T10:00:00Z',
      missing_concepts: ['随机森林'],
      draft_proposal: draftProposalResponse.draft_proposal,
    })
    graphGetOverlayExtractionSessionMock.mockResolvedValue(sessionResponse)
    graphPreviewOverlayPromotionMock.mockResolvedValue({
      status: 'ready',
      valid: true,
      candidate_count: 1,
      baseline_pack_hash: 'hash-before',
      resulting_pack_hash: 'hash-after',
      errors: [],
      warnings: [],
      resources: [],
    })
    graphCommitOverlayPromotionMock.mockResolvedValue({
      reason: 'promoted',
      status: 'ready',
      batch: { status: 'promoted' },
    })
    graphGetOverlayProjectionStatusMock.mockResolvedValue({
      project_id: 'project-001',
      status: 'empty',
      ready: true,
      in_sync: true,
      reason: null,
    })
    graphGetOverlayPreflightMock.mockResolvedValue({
      project_id: 'project-001',
      status: 'ok',
      summary: '1 个节点 / 1 条关系可进入增强图谱，当前未发现阻塞问题。',
      counts: {
        active_nodes: 2,
        active_edges: 1,
        planner_visible_nodes: 1,
        planner_visible_edges: 1,
        visible_overlay_nodes: 1,
        visible_overlay_edges: 1,
        path_overlay_nodes: 1,
        path_overlay_edges: 0,
        ignored_overlay_edges: 0,
        shadowed_edges: 0,
        cycle_edges: 0,
        blocking_items: 0,
        warning_items: 0,
        nodes: { total: 2, valid: 2, confirmed: 1, pending_review: 1, planning_disabled: 0, invalid: 0 },
        edges: { total: 1, valid: 1, confirmed: 1, pending_review: 0, planning_disabled: 0, invalid: 0 },
      },
      visible_overlay_node_ids: ['po:project-001:n:rf'],
      visible_overlay_edge_ids: ['po:project-001:e:rf'],
      path_overlay_node_ids: ['po:project-001:n:rf'],
      path_overlay_edge_ids: [],
      ignored_overlay_edge_ids: [],
      shadowed_edge_ids: [],
      cycle_edge_ids: [],
      blocking_items: [],
      warning_items: [],
      project_graph_hash: 'graph-hash',
    })
    searchListPersistedResultsMock.mockResolvedValue([])
    searchBridgeOverlaySourcesMock.mockResolvedValue({
      source_ids: ['src-saved-001'],
      results: [
        {
          result_id: 'result-001',
          source_id: 'src-saved-001',
          source_type: 'search_url',
          reused: true,
          repaired: false,
        },
      ],
    })
    resourceBindProjectResourceMock.mockResolvedValue({ id: 'binding-001' })
  })

  it('creates pasted text source before extraction session', async () => {
    const wrapper = mountKnowledge()
    await flushPromises()

    ;(wrapper.vm as any).overlayForm.rawText = '逻辑回归扩展资料'
    await (wrapper.vm as any).submitOverlayDraft()

    expect(graphCreateOverlaySourceMock).toHaveBeenCalledWith('project-001', {
      source_type: 'pasted_text',
      raw_text: '逻辑回归扩展资料',
      raw_text_excerpt: '逻辑回归扩展资料',
      summary: null,
    })
    expect(graphPreviewOverlayExtractionPayloadMock).toHaveBeenCalledWith('project-001', {
      source_ids: ['src-001'],
      mode: 'default',
    })
    expect(graphCreateOverlayExtractionSessionMock).toHaveBeenCalledWith('project-001', {
      source_ids: ['src-001'],
      mode: 'default',
      extraction_payload: {
        nodes: [],
        edges: [],
        resources: [],
        warnings: ['llm_generated'],
      },
      session_provenance: {
        draft_origin: 'llm_overlay_extraction',
        prompt_version: 'overlay-extraction-v1',
        selected_counts: { nodes: 0, edges: 0, resources: 0 },
        filtered_by_user: true,
      },
    })
    expect(successMock).toHaveBeenCalled()
  })

  it('creates extraction session with only selected preview candidates', async () => {
    graphPreviewOverlayExtractionPayloadMock.mockImplementation((_projectId: string, payload: any) => Promise.resolve({
      source_ids: payload.source_ids,
      mode: 'default',
      extraction_payload: {
        nodes: [{ name: '保留节点', summary: '保留' }, { name: '移除节点', summary: '移除' }],
        edges: [{ source_name_or_id: '保留节点', target_node_id: 'ml_c01', relation_type: 'RELATED_TO' }],
        resources: [{ title: '移除资源', url: 'https://example.com/remove' }],
        warnings: ['llm_generated'],
      },
      warnings: ['llm_generated'],
      counts: { nodes: 2, edges: 1, resources: 1 },
      provenance: { draft_origin: 'llm_overlay_extraction' },
    }))
    const wrapper = mountKnowledge()
    await flushPromises()

    ;(wrapper.vm as any).overlayForm.rawText = '扩展资料'
    await (wrapper.vm as any).previewOverlayExtractionPayload()
    ;(wrapper.vm as any).togglePreviewCandidate('nodes', 1, false)
    ;(wrapper.vm as any).togglePreviewCandidate('resources', 0, false)
    await (wrapper.vm as any).submitOverlayDraft()

    expect(graphCreateOverlayExtractionSessionMock).toHaveBeenCalledWith('project-001', expect.objectContaining({
      extraction_payload: {
        nodes: [{ name: '保留节点', summary: '保留' }],
        edges: [{ source_name_or_id: '保留节点', target_node_id: 'ml_c01', relation_type: 'RELATED_TO' }],
        resources: [],
        warnings: ['llm_generated'],
      },
      session_provenance: expect.objectContaining({
        selected_counts: { nodes: 1, edges: 1, resources: 0 },
        filtered_by_user: true,
      }),
    }))
  })

  it('opens the latest path graph by default', async () => {
    mountKnowledge()
    await flushPromises()

    expect(graphGetGraphMock).toHaveBeenCalledWith('project-001', {
      scope: 'path',
      path_id: 'latest',
    })
  })

  it('falls back invalid scope query to latest path graph safely', async () => {
    routeState.query = { scope: 'bad-scope' }

    mountKnowledge()
    await flushPromises()

    expect(graphGetGraphMock).toHaveBeenCalledWith('project-001', {
      scope: 'path',
      path_id: 'latest',
    })
  })

  it('loads path deep link with latest path id and selected node', async () => {
    routeState.query = { scope: 'path', path_id: 'latest', nodeId: 'ml_c01' }

    mountKnowledge()
    await flushPromises()

    expect(graphGetGraphMock).toHaveBeenCalledWith('project-001', {
      scope: 'path',
      path_id: 'latest',
      nodeId: 'ml_c01',
    })
  })

  it('normalizes path scope without path id to latest', async () => {
    routeState.query = { scope: 'path' }

    mountKnowledge()
    await flushPromises()

    expect(graphGetGraphMock).toHaveBeenCalledWith('project-001', {
      scope: 'path',
      path_id: 'latest',
    })
  })

  it('writes toolbar path scope selection back to the route', async () => {
    routeState.query = { scope: 'project' }
    const wrapper = mountKnowledge()
    await flushPromises()

    await (wrapper.vm as any).onScopeChange('path')
    await flushPromises()

    expect(replaceMock).toHaveBeenCalledWith({
      name: 'Knowledge',
      query: {
        scope: 'path',
        path_id: 'latest',
      },
    })
  })

  it('preserves active session id when node route is replaced', async () => {
    routeState.query = { sessionId: 'sess-001' }
    const wrapper = mountKnowledge()
    await flushPromises()

    ;(wrapper.vm as any).onNodeClick({ id: 'ml_c01' })
    await flushPromises()

    expect(replaceMock).toHaveBeenLastCalledWith({
      name: 'Knowledge',
      query: {
        scope: 'path',
        path_id: 'latest',
        nodeId: 'ml_c01',
        sessionId: 'sess-001',
      },
    })
  })

  it('writes new extraction session id into route after draft creation', async () => {
    const wrapper = mountKnowledge()
    await flushPromises()

    ;(wrapper.vm as any).overlayForm.rawText = '逻辑回归扩展资料'
    await (wrapper.vm as any).submitOverlayDraft()
    await flushPromises()

    expect(replaceMock).toHaveBeenLastCalledWith({
      name: 'Knowledge',
      query: {
        scope: 'project',
        sessionId: 'sess-001',
      },
    })
    expect(graphGetOverlayProjectionStatusMock).toHaveBeenCalled()
  })

  it('resets stale overlay state when graph scope changes', async () => {
    const wrapper = mountKnowledge()
    await flushPromises()

    ;(wrapper.vm as any).overlayDrawerVisible = true
    ;(wrapper.vm as any).overlayError = 'old error'
    ;(wrapper.vm as any).lastOverlaySession = { session: { session_id: 'old-session' } }

    await (wrapper.vm as any).onScopeChange('project')
    await flushPromises()

    expect((wrapper.vm as any).overlayDrawerVisible).toBe(false)
    expect((wrapper.vm as any).overlayError).toBe('')
    expect((wrapper.vm as any).lastOverlaySession).toBeNull()
  })

  it('clears stale overlay session when session id is removed', async () => {
    routeState.query = { sessionId: 'sess-001' }
    const wrapper = mountKnowledge()
    await flushPromises()

    expect((wrapper.vm as any).lastOverlaySession.session.session_id).toBe('sess-001')

    routeState.query = {}
    await (wrapper.vm as any).syncRequestedOverlaySession(null)
    await flushPromises()

    expect((wrapper.vm as any).overlayDrawerVisible).toBe(false)
    expect((wrapper.vm as any).lastOverlaySession).toBeNull()
  })

  it('restores overlay extraction session from deep link without writes', async () => {
    routeState.query = { sessionId: 'sess-001', nodeId: 'po:project-001:n:test' }

    const wrapper = mountKnowledge()
    await flushPromises()

    expect(graphGetOverlayExtractionSessionMock).toHaveBeenCalledWith('project-001', 'sess-001')
    expect(graphCreateOverlaySourceMock).not.toHaveBeenCalled()
    expect(graphCreateOverlayExtractionSessionMock).not.toHaveBeenCalled()
    expect((wrapper.vm as any).overlayDrawerVisible).toBe(true)
    expect((wrapper.vm as any).lastOverlaySession.session.session_id).toBe('sess-001')
  })

  it('opens goal extension draft entry from route without writes until confirmation', async () => {
    routeState.query = {
      scope: 'project',
      goalDraft: '1',
      resolutionSessionId: 'resolution-001',
    }
    graphCreateGoalExtensionDraftMock.mockResolvedValue({
      session: {
        session_id: 'sess-001',
        project_id: 'project-001',
        mode: 'default',
        session_status: 'validated',
        source_ids: ['src-001'],
        warnings: ['goal_extension_draft_requires_review'],
        created_at: '2026-04-22T09:00:00Z',
        updated_at: '2026-04-22T09:00:00Z',
      },
      sources: [],
      nodes: [],
      edges: [],
      resources: [],
      warnings: ['goal_extension_draft_requires_review'],
      missing_concepts: ['随机森林'],
      gap_analysis: {
        user_goal: '我想学习随机森林',
        missing_concepts: ['随机森林'],
        why_current_graph_is_insufficient: '当前机器学习基础图谱尚未覆盖“随机森林”，不能直接把该目标映射为正式路径节点。',
        recommended_review_focus: ['确认新增概念是否确实属于本次学习目标。'],
      },
      review_notes: ['正式路径仍由图算法基于已审核图谱生成。'],
      draft_metadata: {
        draft_engine: 'rules',
        prompt_version: 'goal-extension-draft-v1',
        requires_user_review: true,
        can_directly_plan: false,
      },
    })

    const wrapper = mountKnowledge()
    await flushPromises()

    expect((wrapper.vm as any).overlayDrawerVisible).toBe(true)
    expect(graphGetGoalExtensionDraftProposalMock).toHaveBeenCalledWith('project-001', 'resolution-001')
    expect(graphCreateGoalExtensionDraftMock).not.toHaveBeenCalled()
    expect(graphCreateOverlayExtractionSessionMock).not.toHaveBeenCalled()

    await (wrapper.vm as any).submitOverlayDraft()
    await flushPromises()

    expect(graphCreateGoalExtensionDraftMock).toHaveBeenCalledWith('project-001', 'resolution-001')
    expect(graphCreateOverlayExtractionSessionMock).not.toHaveBeenCalled()
    expect(replaceMock).toHaveBeenLastCalledWith({
      name: 'Knowledge',
      query: {
        scope: 'project',
        sessionId: 'sess-001',
      },
    })
    expect(wrapper.text()).toContain('目标缺口分析')
    expect(wrapper.text()).toContain('随机森林')
    expect(wrapper.text()).toContain('当前机器学习基础图谱尚未覆盖')
    expect(wrapper.text()).toContain('系统推荐草稿收件箱')
    expect(wrapper.text()).not.toContain('rules / goal-extension-draft-v1')
    expect(wrapper.text()).not.toContain('需人工审核：是；可直接规划：否')
  })

  it('keeps project graph usable when custom extension readiness is blocked', async () => {
    graphCreateOverlayExtractionSessionMock.mockRejectedValue({
      response: { data: { error: 'SEARCH_NOT_READY' } },
    })
    const wrapper = mountKnowledge()
    await flushPromises()

    ;(wrapper.vm as any).overlayForm.rawText = '逻辑回归扩展资料'
    ;(wrapper.vm as any).overlayForm.mode = 'custom_extension'
    await (wrapper.vm as any).submitOverlayDraft()

    expect((wrapper.vm as any).overlayError).toContain('领域基线图谱浏览不受影响')
    expect((wrapper.vm as any).graphState).toBe('empty')
  })

  it('bridges saved search results before creating extraction session with source ids only', async () => {
    searchListPersistedResultsMock.mockResolvedValue([
      {
        result_id: 'result-001',
        query: '逻辑回归',
        provider: 'tavily',
        url: 'https://example.com/logistic',
        title: '逻辑回归资料',
        is_selected: true,
        binding_count: 0,
        created_at: '2026-04-22T09:00:00Z',
      },
    ])
    const wrapper = mountKnowledge()
    await flushPromises()

    ;(wrapper.vm as any).overlayForm.sourceType = 'saved_search'
    ;(wrapper.vm as any).overlayForm.selectedResultIds = ['result-001']
    await (wrapper.vm as any).submitOverlayDraft()

    expect(searchBridgeOverlaySourcesMock).toHaveBeenCalledWith('project-001', ['result-001'])
    expect(graphCreateOverlaySourceMock).not.toHaveBeenCalled()
    expect(graphPreviewOverlayExtractionPayloadMock).toHaveBeenCalledWith('project-001', {
      source_ids: ['src-saved-001'],
      mode: 'default',
    })
    expect(graphCreateOverlayExtractionSessionMock).toHaveBeenCalledWith('project-001', {
      source_ids: ['src-saved-001'],
      mode: 'default',
      extraction_payload: {
        nodes: [],
        edges: [],
        resources: [],
        warnings: ['llm_generated'],
      },
      session_provenance: {
        draft_origin: 'llm_overlay_extraction',
        prompt_version: 'overlay-extraction-v1',
        selected_counts: { nodes: 0, edges: 0, resources: 0 },
        filtered_by_user: true,
      },
    })
    expect(graphCreateOverlayExtractionSessionMock.mock.calls[0][1]).not.toHaveProperty('result_ids')
  })

  it('binds overlay resource and reloads session detail', async () => {
    const resourceSession = {
      session: {
        session_id: 'sess-resource',
        project_id: 'project-001',
        mode: 'default',
        session_status: 'validated',
        source_ids: ['src-001'],
        warnings: [],
        created_at: '2026-04-22T09:00:00Z',
        updated_at: '2026-04-22T09:00:00Z',
      },
      sources: [],
      nodes: [],
      edges: [],
      resources: [{ resource_id: 'res-001', title: '资源候选', bindings: [], binding_summary: { count: 0 } }],
      warnings: [],
    }
    graphGetOverlayExtractionSessionMock.mockResolvedValue(resourceSession)
    const wrapper = mountKnowledge()
    await flushPromises()

    ;(wrapper.vm as any).lastOverlaySession = resourceSession
    ;(wrapper.vm as any).resourceBinding = { resourceId: 'res-001', targetType: 'project_node', targetId: 'ml_c01' }
    await (wrapper.vm as any).bindOverlayResource()

    expect(resourceBindProjectResourceMock).toHaveBeenCalledWith('project-001', {
      resource_id: 'res-001',
      target_type: 'project_node',
      target_id: 'ml_c01',
      binding_source: 'overlay',
    })
    expect(graphGetOverlayExtractionSessionMock).toHaveBeenCalledWith('project-001', 'sess-resource')
  })

  it('previews and commits promotion without persisting admin secret', async () => {
    routeState.query = { scope: 'project' }
    const wrapper = mountKnowledge()
    await flushPromises()

    await (wrapper.vm as any).previewPromotion()
    ;(wrapper.vm as any).promotionSecret = 'secret-value'
    await (wrapper.vm as any).commitPromotion()

    expect(graphPreviewOverlayPromotionMock).toHaveBeenCalledWith('project-001')
    expect(graphCommitOverlayPromotionMock).toHaveBeenCalledWith('project-001', {
      admin_secret: 'secret-value',
      requested_by: 'frontend',
    })
    expect((wrapper.vm as any).promotionSecret).toBe('')
    expect(graphGetGraphMock).toHaveBeenLastCalledWith('project-001', { scope: 'project' })
  })

  it('updates overlay planning independently from review status', async () => {
    graphSetOverlayPlanningMock.mockResolvedValue({
      element_id: 'po:project-001:n:test',
      element_type: 'node',
      validation_status: 'valid',
      review_status: 'confirmed',
      planning_enabled: false,
      promotion_status: 'not_promoted',
    })
    const wrapper = mountKnowledge()
    await flushPromises()

    await (wrapper.vm as any).onSetOverlayPlanning({
      id: 'po:project-001:n:test',
      origin: 'overlay',
      label: '扩展节点',
    }, false)

    expect(confirmMock).not.toHaveBeenCalled()
    expect(graphSetOverlayPlanningMock).toHaveBeenCalledWith(
      'project-001',
      'nodes',
      'po:project-001:n:test',
      false,
    )
  })

  it('confirms before enabling overlay planning', async () => {
    graphSetOverlayPlanningMock.mockResolvedValue({
      element_id: 'po:project-001:n:test',
      element_type: 'node',
      validation_status: 'valid',
      review_status: 'confirmed',
      planning_enabled: true,
      promotion_status: 'not_promoted',
    })
    const wrapper = mountKnowledge()
    await flushPromises()

    await (wrapper.vm as any).onSetOverlayPlanning({
      id: 'po:project-001:n:test',
      origin: 'overlay',
      label: '扩展节点',
    }, true)

    expect(confirmMock).toHaveBeenCalledWith(
      expect.stringContaining('增强图谱预检和路径对比'),
      '纳入增强图谱规划',
      expect.objectContaining({ confirmButtonText: '纳入规划' }),
    )
    expect(graphSetOverlayPlanningMock).toHaveBeenCalledWith(
      'project-001',
      'nodes',
      'po:project-001:n:test',
      true,
    )
  })

  it('skips enabling overlay planning when confirmation is cancelled', async () => {
    confirmMock.mockRejectedValueOnce('cancel')
    const wrapper = mountKnowledge()
    await flushPromises()

    await (wrapper.vm as any).onSetOverlayPlanning({
      id: 'po:project-001:n:test',
      origin: 'overlay',
      label: '扩展节点',
    }, true)

    expect(graphSetOverlayPlanningMock).not.toHaveBeenCalled()
  })

  it('confirms overlay candidate before marking it confirmed', async () => {
    graphGetGraphMock.mockResolvedValue({
      scope: 'path',
      is_empty: false,
      elements: [{
        group: 'nodes',
        data: {
          id: 'po:project-001:n:test',
          label: '扩展节点',
          origin: 'overlay',
          review_status: 'pending',
          planning_enabled: false,
        },
      }],
    })
    graphReviewOverlayElementMock.mockResolvedValue({
      element_id: 'po:project-001:n:test',
      element_type: 'node',
      validation_status: 'valid',
      review_status: 'confirmed',
      planning_enabled: false,
      promotion_status: 'not_promoted',
    })
    const wrapper = mountKnowledge()
    await flushPromises()
    ;(wrapper.vm as any).graphRef = { setNodeReviewStatus: vi.fn() }

    await (wrapper.vm as any).onReviewNode('po:project-001:n:test', 'confirmed')

    expect(confirmMock).toHaveBeenCalledWith(
      expect.stringContaining('规划开关控制'),
      '确认扩展候选有效',
      expect.objectContaining({ confirmButtonText: '确认有效' }),
    )
    expect(graphReviewOverlayElementMock).toHaveBeenCalledWith(
      'project-001',
      'nodes',
      'po:project-001:n:test',
      'confirmed',
    )
  })

  it('renders overlay preflight usage status', async () => {
    const wrapper = mountKnowledge()
    await flushPromises()

    expect(graphGetOverlayPreflightMock).toHaveBeenCalledWith('project-001')
    expect(wrapper.text()).toContain('增强图谱使用状态')
    expect(wrapper.text()).toContain('可进入增强图谱 1 节点 / 1 关系')
    expect(wrapper.text()).toContain('当前路径命中 1 节点 / 0 关系')
  })

  it('manually prepares a goal extension draft inbox from the current project goal', async () => {
    const wrapper = mountKnowledge()
    await flushPromises()

    await (wrapper.vm as any).openOverlayDrawer()
    await (wrapper.vm as any).prepareGoalDraftFromCurrentProject()
    await flushPromises()

    expect(projectPreviewForProjectMock).toHaveBeenCalledWith('project-001', {
      goal_text: '我想系统学习机器学习基础',
      requested_goal_type: 'domain',
      domain: 'machine_learning',
    })
    expect(graphGetGoalExtensionDraftProposalMock).toHaveBeenCalledWith('project-001', 'resolution-001')
    expect((wrapper.vm as any).overlayDraftMode).toBe('goal_draft')
    expect(wrapper.text()).toContain('系统推荐草稿收件箱')
  })

  it.each([
    ['missing', 'warning'],
    ['empty', 'warning'],
    ['ok', 'success'],
    ['drifted', 'warning'],
    ['error', 'warning'],
  ])('maps overlay projection status %s without treating drift as success', async (status, alertType) => {
    const wrapper = mountKnowledge()
    await flushPromises()

    ;(wrapper.vm as any).projectionStatus = {
      project_id: 'project-001',
      status,
      ready: true,
      in_sync: status === 'ok',
      reason: `${status}_reason`,
    }
    await wrapper.vm.$nextTick()

    expect((wrapper.vm as any).projectionAlertType).toBe(alertType)
  })
})
