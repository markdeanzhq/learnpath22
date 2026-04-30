import { computed, ref, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import {
  graphApi,
  type GoalExtensionDraftProposal,
  type GoalExtensionDraftProposalResponse,
  type GoalExtensionDraftResponse,
  type OverlayExtractionPayloadPreviewResponse,
  type OverlayExtractionPayloadValidationResponse,
  type OverlaySourceRequest,
} from '@/api/modules/graph'
import { projectApi, type GoalResolutionPreviewResponse, type ReviewExtensionDraftCoverageResponse } from '@/api/modules/project'
import { searchApi, type SearchResultItem } from '@/api/modules/search'
import type { OverlaySessionView } from './useOverlayCandidateWorkflow'

export type OverlaySourceType = 'pasted_text' | 'search_url' | 'saved_search'
export type OverlayExtractionMode = 'default' | 'custom_extension'
export type OverlayDraftMode = 'goal_draft' | 'manual'
export type OverlayPreviewGroup = 'nodes' | 'edges' | 'resources'

type CurrentProjectLike = {
  goal_text?: string | null
  goal_type?: string | null
  domain?: string | null
} | null | undefined

export type PreviewPayload = {
  nodes: Array<Record<string, any>>
  edges: Array<Record<string, any>>
  resources: Array<Record<string, any>>
  warnings: string[]
}

export type OverlayFormState = ReturnType<typeof createOverlayForm>

type UseOverlayDraftInputOptions = {
  projectId: Readonly<Ref<string | undefined>>
  currentProject: Readonly<Ref<CurrentProjectLike>>
  routeGoalDraftResolutionSessionId: Readonly<Ref<string | null>>
  overlayDrawerVisible: Ref<boolean>
  overlayError: Ref<string>
  lastOverlaySession: Ref<OverlaySessionView | null>
  loadPersistedSearchResults: () => Promise<void>
  onDraftCreated: (session: OverlaySessionView) => Promise<void>
  getErrorMessage: (error: unknown) => string
  notifySuccess?: (message: string) => void
}

export function createOverlayForm() {
  return {
    sourceType: 'pasted_text' as OverlaySourceType,
    selectedResultIds: [] as string[],
    rawText: '',
    url: '',
    title: '',
    snippet: '',
    summary: '',
    mode: 'default' as OverlayExtractionMode,
  }
}

export function useOverlayDraftInput({
  projectId,
  currentProject,
  routeGoalDraftResolutionSessionId,
  overlayDrawerVisible,
  overlayError,
  lastOverlaySession,
  loadPersistedSearchResults,
  onDraftCreated,
  getErrorMessage,
  notifySuccess,
}: UseOverlayDraftInputOptions) {
  const overlaySubmitting = ref(false)
  const overlayExtractionPreviewLoading = ref(false)
  const overlayAutoDraftLoading = ref(false)
  const overlayBridgeMessage = ref('')
  const overlaySearchQuery = ref('')
  const overlaySearchResults = ref<SearchResultItem[]>([])
  const overlaySearchLoading = ref(false)
  const overlaySearchError = ref('')
  const overlayAddingSearchUrl = ref('')
  const overlayForm = ref(createOverlayForm())
  const overlayDraftMode = ref<OverlayDraftMode>('manual')
  const overlayExtractionPreview = ref<OverlayExtractionPayloadPreviewResponse | null>(null)
  const overlayCandidateValidation = ref<OverlayExtractionPayloadValidationResponse | null>(null)
  const selectedPreviewCandidates = ref<Record<OverlayPreviewGroup, number[]>>({ nodes: [], edges: [], resources: [] })
  const goalDraftProposal = ref<GoalExtensionDraftProposalResponse | null>(null)
  const goalDraftProposalLoading = ref(false)
  const manualGoalDraftLoading = ref(false)
  const manualGoalDraftResolutionSessionId = ref<string | null>(null)
  const goalDraftProposalDismissed = ref(false)
  const activeGoalDraftResolutionSessionId = computed(() => routeGoalDraftResolutionSessionId.value || manualGoalDraftResolutionSessionId.value)
  const goalExtensionDraftDetails = computed(() => {
    const session = lastOverlaySession.value
    if (!session?.gap_analysis && !session?.review_notes?.length && !session?.draft_metadata) {
      return null
    }
    return session
  })
  const goalDraftMissingConcepts = computed(() => (
    goalExtensionDraftDetails.value?.gap_analysis?.missing_concepts
    || goalExtensionDraftDetails.value?.missing_concepts
    || []
  ))
  const goalDraftReviewNotes = computed(() => goalExtensionDraftDetails.value?.review_notes || [])
  const goalDraftReviewFocus = computed(() => goalExtensionDraftDetails.value?.gap_analysis?.recommended_review_focus || [])
  const manualOverlayMode = computed(() => !activeGoalDraftResolutionSessionId.value || overlayDraftMode.value === 'manual')
  const goalDraftInboxProposal = computed<GoalExtensionDraftProposal | null>(() => goalDraftProposal.value?.draft_proposal || null)
  const goalDraftInboxCounts = computed(() => goalDraftInboxProposal.value?.counts || { nodes: 0, edges: 0, resources: 0 })
  const goalDraftInboxMissingConcepts = computed(() => goalDraftInboxProposal.value?.missing_concepts || goalDraftMissingConcepts.value)
  const goalDraftInboxNodes = computed(() => goalDraftInboxProposal.value?.nodes || [])
  const goalDraftInboxEdges = computed(() => goalDraftInboxProposal.value?.edges || [])
  const goalDraftInboxResources = computed(() => goalDraftInboxProposal.value?.resources || [])
  const normalizedPreviewPayload = computed(() => normalizePreviewPayload(overlayExtractionPreview.value?.extraction_payload))
  const selectedPreviewCounts = computed(() => ({
    nodes: selectedPreviewCandidates.value.nodes.length,
    edges: selectedPreviewCandidates.value.edges.length,
    resources: selectedPreviewCandidates.value.resources.length,
  }))

  watch(overlayForm, () => {
    clearPreviewSelection()
  }, { deep: true })

  watch(overlayDraftMode, (nextMode) => {
    overlayError.value = ''
    clearPreviewSelection()
    if (nextMode === 'goal_draft') {
      goalDraftProposalDismissed.value = false
    }
  })

  async function openOverlayDrawer() {
    overlayDrawerVisible.value = true
    overlayDraftMode.value = activeGoalDraftResolutionSessionId.value ? overlayDraftMode.value : 'manual'
    overlayError.value = ''
    overlayBridgeMessage.value = ''
    overlaySearchError.value = ''
    await loadPersistedSearchResults()
  }

  async function prepareGoalDraftFromCurrentProject() {
    const project = currentProject.value
    if (!projectId.value || !project?.goal_text) return
    manualGoalDraftLoading.value = true
    overlayError.value = ''
    goalDraftProposalDismissed.value = false
    try {
      const preview = await projectApi.previewForProject(projectId.value, {
        goal_text: project.goal_text,
        requested_goal_type: normalizePreviewGoalType(project.goal_type),
        domain: project.domain || undefined,
      })
      if (!isReviewExtensionDraftResponse(preview) || !preview.session_id || !preview.draft_proposal) {
        overlayDraftMode.value = 'manual'
        overlayError.value = '当前目标已被现有图谱覆盖，暂不需要生成自动扩展草稿。'
        return
      }
      manualGoalDraftResolutionSessionId.value = preview.session_id
      goalDraftProposal.value = {
        resolution_session_id: preview.session_id,
        project_id: projectId.value,
        session_status: 'draft_previewed',
        expires_at: preview.expires_at || undefined,
        draft_proposal: preview.draft_proposal,
      }
      overlayDraftMode.value = 'goal_draft'
      overlayDrawerVisible.value = true
    } catch (error: unknown) {
      overlayError.value = getErrorMessage(error)
    } finally {
      manualGoalDraftLoading.value = false
    }
  }

  async function openGoalDraftEntry({ refreshPersistedSearchResults = true }: { refreshPersistedSearchResults?: boolean } = {}) {
    if (!activeGoalDraftResolutionSessionId.value) return
    overlayDrawerVisible.value = true
    overlayDraftMode.value = 'goal_draft'
    overlayError.value = ''
    overlayBridgeMessage.value = ''
    overlayForm.value = createOverlayForm()
    if (refreshPersistedSearchResults) {
      await loadPersistedSearchResults()
    }
    await loadGoalDraftProposal()
  }

  async function loadGoalDraftProposal() {
    const currentProjectId = projectId.value
    const currentResolutionSessionId = activeGoalDraftResolutionSessionId.value
    if (!currentProjectId || !currentResolutionSessionId) return
    goalDraftProposalLoading.value = true
    try {
      const proposal = await graphApi.getGoalExtensionDraftProposal(
        currentProjectId,
        currentResolutionSessionId,
      )
      if (projectId.value === currentProjectId && activeGoalDraftResolutionSessionId.value === currentResolutionSessionId) {
        goalDraftProposal.value = proposal
      }
    } catch (error: unknown) {
      if (projectId.value === currentProjectId && activeGoalDraftResolutionSessionId.value === currentResolutionSessionId) {
        overlayError.value = getErrorMessage(error)
      }
    } finally {
      if (projectId.value === currentProjectId && activeGoalDraftResolutionSessionId.value === currentResolutionSessionId) {
        goalDraftProposalLoading.value = false
      }
    }
  }

  function dismissGoalDraftProposal() {
    goalDraftProposalDismissed.value = true
    overlayDraftMode.value = 'manual'
  }

  function togglePreviewCandidate(group: OverlayPreviewGroup, index: number, checked: boolean) {
    const current = new Set(selectedPreviewCandidates.value[group])
    if (checked) {
      current.add(index)
    } else {
      current.delete(index)
    }
    selectedPreviewCandidates.value = {
      ...selectedPreviewCandidates.value,
      [group]: [...current].sort((a, b) => a - b),
    }
  }

  function isPreviewCandidateSelected(group: OverlayPreviewGroup, index: number) {
    return selectedPreviewCandidates.value[group].includes(index)
  }

  async function searchOverlayResults() {
    const currentProjectId = projectId.value
    const query = overlaySearchQuery.value.trim()
    if (!currentProjectId) return
    if (!query) {
      overlaySearchError.value = '请输入搜索关键词，例如“随机森林 机器学习 入门”。'
      return
    }

    overlaySearchLoading.value = true
    overlaySearchError.value = ''
    try {
      const response = await searchApi.search(currentProjectId, query, 6)
      overlaySearchResults.value = response.results || []
      if (!overlaySearchResults.value.length) {
        overlaySearchError.value = '未找到可用资料，请换用更具体的关键词，或改用粘贴文本。'
      }
    } catch (error: any) {
      overlaySearchError.value = error?.response?.data?.error || '资料搜索失败，请检查搜索配置或稍后重试。'
    } finally {
      overlaySearchLoading.value = false
    }
  }

  async function addSearchResultToOverlay(result: SearchResultItem, index: number) {
    const currentProjectId = projectId.value
    if (!currentProjectId) return

    overlayAddingSearchUrl.value = result.url
    overlaySearchError.value = ''
    try {
      const saved = await searchApi.persistResult(currentProjectId, {
        query: overlaySearchQuery.value.trim() || currentProject.value?.goal_text || '项目扩展资料',
        provider: result.provider || 'tavily',
        url: result.url,
        title: result.title,
        snippet: result.snippet,
        result_rank: index + 1,
        is_selected: true,
      })
      const nextSelectedIds = new Set(overlayForm.value.selectedResultIds)
      nextSelectedIds.add(saved.result_id)
      overlayForm.value = {
        ...overlayForm.value,
        sourceType: 'saved_search',
        selectedResultIds: [...nextSelectedIds],
      }
      const bridged = await searchApi.bridgeOverlaySources(currentProjectId, [saved.result_id])
      overlayBridgeMessage.value = bridged.results[0]?.reused ? '已复用该资料作为项目扩展来源，可生成候选预览。' : '已加入项目扩展来源，可生成候选预览。'
      await loadPersistedSearchResults()
      notifySuccess?.('资料已加入扩展草稿来源')
    } catch (error: any) {
      overlaySearchError.value = error?.response?.data?.error || '资料加入扩展草稿失败'
    } finally {
      overlayAddingSearchUrl.value = ''
    }
  }

  async function createAutoOverlayDraft() {
    const currentProjectId = projectId.value
    if (!currentProjectId) return

    const query = overlaySearchQuery.value.trim()
    if (!query) {
      overlaySearchError.value = '请输入想扩展的主题，例如“随机森林 机器学习 入门”。'
      return
    }

    overlayAutoDraftLoading.value = true
    overlayError.value = ''
    overlaySearchError.value = ''
    overlayBridgeMessage.value = ''
    try {
      const session = await graphApi.createOverlayAutoDraft(currentProjectId, {
        query,
        max_results: 5,
        mode: overlayForm.value.mode,
      })
      lastOverlaySession.value = session
      overlaySearchQuery.value = session.auto_draft?.query || query
      overlayDraftMode.value = 'manual'
      overlayForm.value = createOverlayForm()
      clearPreviewSelection()
      const selectedCount = session.auto_draft?.selected_result_count || 0
      const extractionStatus = session.auto_draft?.extraction_status || 'extracted'
      if (extractionStatus === 'extracted') {
        overlayBridgeMessage.value = `自动草稿已基于 ${selectedCount} 条资料创建，请审核候选后再启用规划。`
        notifySuccess?.('自动扩展草稿已创建，请审核候选节点、关系和资源')
      } else {
        const reason = session.auto_draft?.extraction_error ? `（${session.auto_draft.extraction_error}）` : ''
        overlayBridgeMessage.value = `已保存 ${selectedCount} 条资料，但 AI 抽取未生成候选${reason}。请在已保存搜索中重试生成候选预览，或改用手动资料补充。`
        notifySuccess?.('资料已保存，可重试抽取或手动补充候选')
      }
      await loadPersistedSearchResults()
      await onDraftCreated(session)
    } catch (error: unknown) {
      overlayError.value = getErrorMessage(error)
    } finally {
      overlayAutoDraftLoading.value = false
    }
  }

  async function previewOverlayExtractionPayload() {
    if (!projectId.value || !manualOverlayMode.value) return null

    overlayExtractionPreviewLoading.value = true
    overlayError.value = ''
    overlayBridgeMessage.value = ''

    try {
      const sourceIds = await resolveOverlaySourceIds()
      if (!sourceIds) return null
      const preview = await graphApi.previewOverlayExtractionPayload(projectId.value, {
        source_ids: sourceIds,
        mode: overlayForm.value.mode,
      })
      overlayExtractionPreview.value = preview
      selectAllPreviewCandidates(normalizePreviewPayload(preview.extraction_payload))
      notifySuccess?.('AI 抽取预览已生成，创建草稿时仍会经过校验。')
      return preview
    } catch (error: unknown) {
      overlayError.value = getErrorMessage(error)
      return null
    } finally {
      overlayExtractionPreviewLoading.value = false
    }
  }

  async function submitOverlayDraft() {
    if (!projectId.value) return

    overlaySubmitting.value = true
    overlayError.value = ''
    overlayBridgeMessage.value = ''

    try {
      if (activeGoalDraftResolutionSessionId.value && overlayDraftMode.value === 'goal_draft') {
        lastOverlaySession.value = await graphApi.createGoalExtensionDraft(
          projectId.value,
          activeGoalDraftResolutionSessionId.value,
        ) as GoalExtensionDraftResponse & OverlaySessionView
      } else {
        const preview = overlayExtractionPreview.value || await previewOverlayExtractionPayload()
        if (!preview) return
        const extractionPayload = await validateSelectedOverlayPayload(preview)
        if (!extractionPayload) return
        lastOverlaySession.value = await graphApi.createOverlayExtractionSession(projectId.value, {
          source_ids: preview.source_ids,
          mode: overlayForm.value.mode,
          extraction_payload: extractionPayload,
          session_provenance: {
            ...preview.provenance,
            selected_counts: selectedPreviewCounts.value,
            filtered_by_user: true,
            pre_validation_summary: overlayCandidateValidation.value?.summary,
          },
        })
      }
      overlayForm.value = createOverlayForm()
      clearPreviewSelection()
      goalDraftProposalDismissed.value = Boolean(activeGoalDraftResolutionSessionId.value)
      notifySuccess?.('扩展草稿已创建，请在项目图谱中审核候选节点和关系')
      if (lastOverlaySession.value) {
        await onDraftCreated(lastOverlaySession.value)
      }
    } catch (error: unknown) {
      if (isMessageBoxCancel(error)) return
      overlayError.value = getErrorMessage(error)
    } finally {
      overlaySubmitting.value = false
    }
  }

  function resetOverlayDraftInput(nextMode: OverlayDraftMode) {
    overlayDrawerVisible.value = false
    overlaySubmitting.value = false
    overlayExtractionPreviewLoading.value = false
    overlayAutoDraftLoading.value = false
    overlayError.value = ''
    overlayBridgeMessage.value = ''
    overlaySearchError.value = ''
    overlaySearchResults.value = []
    overlayAddingSearchUrl.value = ''
    overlayForm.value = createOverlayForm()
    overlayDraftMode.value = nextMode
    clearPreviewSelection()
    goalDraftProposal.value = null
    goalDraftProposalLoading.value = false
    goalDraftProposalDismissed.value = false
  }

  function applyWorkspaceGoalDraftProposal(proposal: GoalExtensionDraftProposalResponse | null | undefined) {
    goalDraftProposal.value = proposal ?? null
  }

  function prepareWorkspaceGoalDraftLoading() {
    overlayDrawerVisible.value = true
    overlayDraftMode.value = 'goal_draft'
    overlayError.value = ''
    overlayBridgeMessage.value = ''
    overlayForm.value = createOverlayForm()
    overlaySearchError.value = ''
    if (!overlaySearchQuery.value.trim() && currentProject.value?.goal_text) {
      overlaySearchQuery.value = currentProject.value.goal_text
    }
    goalDraftProposalLoading.value = true
  }

  async function resolveOverlaySourceIds() {
    const form = overlayForm.value
    if (form.sourceType === 'saved_search') {
      if (!projectId.value || !form.selectedResultIds.length) {
        overlayError.value = '请选择已保存搜索结果'
        return null
      }
      const bridged = await searchApi.bridgeOverlaySources(projectId.value, form.selectedResultIds)
      overlayBridgeMessage.value = `已解析 ${bridged.source_ids.length} 个项目扩展来源，${bridged.results.filter((item) => item.reused).length} 个复用。`
      return bridged.source_ids
    }

    const sourcePayload = buildOverlaySourcePayload()
    if (!sourcePayload || !projectId.value) return null
    const source = await graphApi.createOverlaySource(projectId.value, sourcePayload)
    return [source.source_id]
  }

  function buildOverlaySourcePayload(): OverlaySourceRequest | null {
    const form = overlayForm.value
    if (form.sourceType === 'pasted_text') {
      const rawText = form.rawText.trim()
      if (!rawText) {
        overlayError.value = '请先粘贴资料文本'
        return null
      }
      return {
        source_type: 'pasted_text',
        raw_text: rawText,
        raw_text_excerpt: rawText.slice(0, 12000),
        summary: form.summary.trim() || null,
      }
    }

    if (form.sourceType === 'search_url') {
      const url = form.url.trim()
      if (!url) {
        overlayError.value = '请填写搜索结果 URL'
        return null
      }

      return {
        source_type: 'search_url',
        url,
        title: form.title.trim() || url,
        snippet: form.snippet.trim() || null,
        summary: form.summary.trim() || null,
        provider: 'manual',
      }
    }

    return null
  }

  async function validateSelectedOverlayPayload(preview: OverlayExtractionPayloadPreviewResponse) {
    if (!projectId.value) return null
    const extractionPayload = filteredPreviewPayload(preview)
    const validation = await graphApi.validateOverlayExtractionPayload(projectId.value, {
      source_ids: preview.source_ids,
      mode: overlayForm.value.mode,
      extraction_payload: extractionPayload,
    })
    overlayCandidateValidation.value = validation
    if (validation.summary.has_blocking_errors) {
      await ElMessageBox.confirm(
        `预校验发现 ${validation.summary.invalid_count} 个校验失败候选。仍可创建草稿并在下方“编辑修复”，是否继续？`,
        '候选需要修复',
        {
          type: 'warning',
          confirmButtonText: '继续创建草稿',
          cancelButtonText: '返回调整',
        },
      )
    }
    return extractionPayload
  }

  function filteredPreviewPayload(preview: OverlayExtractionPayloadPreviewResponse) {
    const payload = normalizePreviewPayload(preview.extraction_payload)
    return {
      nodes: payload.nodes.filter((_, index) => selectedPreviewCandidates.value.nodes.includes(index)),
      edges: payload.edges.filter((_, index) => selectedPreviewCandidates.value.edges.includes(index)),
      resources: payload.resources.filter((_, index) => selectedPreviewCandidates.value.resources.includes(index)),
      warnings: payload.warnings,
    }
  }

  function selectAllPreviewCandidates(payload: PreviewPayload) {
    selectedPreviewCandidates.value = {
      nodes: payload.nodes.map((_, index) => index),
      edges: payload.edges.map((_, index) => index),
      resources: payload.resources.map((_, index) => index),
    }
  }

  function clearPreviewSelection() {
    overlayExtractionPreview.value = null
    overlayCandidateValidation.value = null
    selectedPreviewCandidates.value = { nodes: [], edges: [], resources: [] }
  }

  return {
    overlaySubmitting,
    overlayExtractionPreviewLoading,
    overlayAutoDraftLoading,
    overlayBridgeMessage,
    overlaySearchQuery,
    overlaySearchResults,
    overlaySearchLoading,
    overlaySearchError,
    overlayAddingSearchUrl,
    overlayForm,
    overlayDraftMode,
    overlayExtractionPreview,
    overlayCandidateValidation,
    selectedPreviewCandidates,
    goalDraftProposal,
    goalDraftProposalLoading,
    manualGoalDraftLoading,
    manualGoalDraftResolutionSessionId,
    goalDraftProposalDismissed,
    activeGoalDraftResolutionSessionId,
    goalExtensionDraftDetails,
    goalDraftMissingConcepts,
    goalDraftReviewNotes,
    goalDraftReviewFocus,
    manualOverlayMode,
    goalDraftInboxProposal,
    goalDraftInboxCounts,
    goalDraftInboxMissingConcepts,
    goalDraftInboxNodes,
    goalDraftInboxEdges,
    goalDraftInboxResources,
    normalizedPreviewPayload,
    selectedPreviewCounts,
    openOverlayDrawer,
    prepareGoalDraftFromCurrentProject,
    openGoalDraftEntry,
    loadGoalDraftProposal,
    dismissGoalDraftProposal,
    togglePreviewCandidate,
    isPreviewCandidateSelected,
    searchOverlayResults,
    addSearchResultToOverlay,
    createAutoOverlayDraft,
    previewOverlayExtractionPayload,
    submitOverlayDraft,
    resetOverlayDraftInput,
    applyWorkspaceGoalDraftProposal,
    prepareWorkspaceGoalDraftLoading,
    candidateTitle,
    edgeCandidateSummary,
  }
}

function normalizePreviewPayload(payload: unknown): PreviewPayload {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return { nodes: [], edges: [], resources: [], warnings: [] }
  }
  const record = payload as Record<string, unknown>
  return {
    nodes: Array.isArray(record.nodes) ? record.nodes.filter((item): item is Record<string, any> => Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : [],
    edges: Array.isArray(record.edges) ? record.edges.filter((item): item is Record<string, any> => Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : [],
    resources: Array.isArray(record.resources) ? record.resources.filter((item): item is Record<string, any> => Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : [],
    warnings: Array.isArray(record.warnings) ? record.warnings.filter((item): item is string => typeof item === 'string') : [],
  }
}

function candidateTitle(candidate: Record<string, any>, fallback: string) {
  return candidate.name || candidate.title || candidate.relation_type || fallback
}

function edgeCandidateSummary(candidate: Record<string, any>) {
  const source = candidate.source_name_or_id || candidate.source_node_id || '未知来源'
  const target = candidate.target_name_or_id || candidate.target_node_id || '未知目标'
  return `${source} → ${target}`
}

function isReviewExtensionDraftResponse(response: GoalResolutionPreviewResponse): response is ReviewExtensionDraftCoverageResponse {
  return response.result_type === 'review_extension_draft' && response.coverage_status === 'in_domain_uncovered'
}

function normalizePreviewGoalType(value: unknown): 'domain' | 'concept' | 'problem' | undefined {
  return value === 'domain' || value === 'concept' || value === 'problem' ? value : undefined
}

function isMessageBoxCancel(error: unknown): boolean {
  if (typeof error === 'string') {
    return error === 'cancel' || error === 'close'
  }
  if (error && typeof error === 'object') {
    const action = (error as { action?: unknown }).action
    return action === 'cancel' || action === 'close'
  }
  return false
}
