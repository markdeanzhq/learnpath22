import request from '../request'
import type { RequestConfig } from '../request'
import type { PersistedSearchResult } from './search'

export type GraphScope = 'domain' | 'project' | 'path'
export const DEFAULT_GRAPH_SCOPE: GraphScope = 'path'
export const GRAPH_PATH_ID_LATEST = 'latest'
export type GraphEmptyReason = 'project_latest_plan_missing' | string
export type ReviewStatus = 'pending' | 'confirmed' | 'removed' | 'rejected'
export type OverlayReviewStatus = ReviewStatus
export type OverlayValidationStatus = 'valid' | 'invalid' | 'needs_review' | string
export type OverlayPromotionStatus = 'not_promoted' | 'promotion_ready' | 'promoted' | 'archived' | string
export type OverlayElementGroup = 'nodes' | 'edges' | 'resources'
export type OverlaySourceType = 'pasted_text' | 'search_url'

export interface OverlayLifecycleData {
  origin?: 'baseline' | 'overlay' | string
  scope?: GraphScope | string
  validation_status?: OverlayValidationStatus
  review_status?: ReviewStatus | OverlayReviewStatus
  planning_enabled?: boolean
  promotion_status?: OverlayPromotionStatus
  source_ids?: string[]
  provenance?: Record<string, unknown>
  validation_errors?: string[]
  confidence?: number | null
}

export interface GraphNodeData extends OverlayLifecycleData {
  id: string
  label?: string
  category?: string
  group_id?: string
  difficulty?: number
  importance?: number
  estimated_hours?: number
  is_main_path?: boolean
  [key: string]: any
}

export interface GraphEdgeData extends OverlayLifecycleData {
  id: string
  source: string
  target: string
  type?: string
  reason?: string
  [key: string]: any
}

export type GraphElement =
  | {
      group: 'nodes'
      data: GraphNodeData
    }
  | {
      group: 'edges'
      data: GraphEdgeData
    }

export interface GetGraphParams {
  scope?: GraphScope
  path_id?: string
  nodeId?: string
}

export type GraphRouteQuery = Record<string, string>

export interface GraphData {
  scope: GraphScope
  elements: GraphElement[]
  is_empty: boolean
  empty_reason?: GraphEmptyReason
  message?: string
  node_ids?: string[]
  missing_node_ids?: string[]
  path_id?: string | null
}

export interface GraphWorkspaceParams extends GetGraphParams {
  include_persisted_search_results?: boolean
  session_id?: string | null
  goal_draft_resolution_session_id?: string | null
}

export type OverlayProjectionStatus = 'missing' | 'empty' | 'ok' | 'drifted' | 'error'

export interface OverlayProjectionStatusResponse {
  project_id: string
  status: OverlayProjectionStatus
  ready: boolean
  in_sync: boolean
  overlay_hash?: string | null
  projected_hash?: string | null
  reason?: string | null
  projected_at?: string | null
}

export type OverlayPreflightStatus = 'ok' | 'warning' | 'blocked'

export interface OverlayCandidateCounts {
  total: number
  valid: number
  confirmed: number
  pending_review: number
  planning_disabled: number
  invalid: number
}

export interface OverlayPreflightCounts {
  active_nodes: number
  active_edges: number
  planner_visible_nodes?: number
  planner_visible_edges?: number
  visible_overlay_nodes: number
  visible_overlay_edges: number
  path_overlay_nodes: number
  path_overlay_edges: number
  ignored_overlay_edges?: number
  shadowed_edges?: number
  cycle_edges?: number
  blocking_items: number
  warning_items: number
  nodes: OverlayCandidateCounts
  edges: OverlayCandidateCounts
}

export interface OverlayPreflightItem {
  kind: string
  message: string
  edge_ids?: string[]
  node_ids?: string[]
  [key: string]: unknown
}

export interface OverlayPreflightResponse {
  project_id: string
  status: OverlayPreflightStatus
  summary: string
  counts: OverlayPreflightCounts
  visible_overlay_node_ids: string[]
  visible_overlay_edge_ids: string[]
  path_overlay_node_ids: string[]
  path_overlay_edge_ids: string[]
  ignored_overlay_edge_ids: string[]
  shadowed_edge_ids: string[]
  cycle_edge_ids: string[]
  blocking_items: OverlayPreflightItem[]
  warning_items: OverlayPreflightItem[]
  project_graph_hash?: string | null
}

export interface GraphSyncResponse {
  domain: string
  version: string
  pack_hash?: string
  synced?: boolean
  forced?: boolean
  reason: 'unchanged' | 'changed' | 'forced' | string
  nodes: number
  edges: number
  message?: string
  overlay_projection?: OverlayProjectionStatusResponse | Record<string, unknown>
}

export interface OverlaySourceRequest {
  source_type: OverlaySourceType
  raw_text?: string | null
  raw_text_excerpt?: string | null
  url?: string | null
  title?: string | null
  snippet?: string | null
  provider?: string | null
  query?: string | null
  result_rank?: number | null
  retrieved_at?: string | null
  summary?: string | null
  quality_status?: string | null
  metadata_json?: string | null
}

export interface OverlaySource extends Omit<OverlaySourceRequest, 'raw_text'> {
  source_id: string
  project_id: string
  content_hash?: string | null
  created_at: string
}

export interface OverlayCandidateBase {
  project_id: string
  session_id: string
  validation_status: OverlayValidationStatus
  review_status: OverlayReviewStatus
  planning_enabled: boolean
  promotion_status: OverlayPromotionStatus
  source_ids: string[]
  provenance: Record<string, unknown>
  duplicate_candidates: Record<string, unknown>
  validation_errors: string[]
  legality_rationale?: string | null
  confidence?: number | null
  canonical_payload_hash?: string | null
  created_at: string
  updated_at: string
}

export interface OverlayNodeCandidate extends OverlayCandidateBase {
  node_id: string
  name: string
  summary?: string | null
  group?: string | null
  category?: string | null
  difficulty_final?: number | null
  importance_final?: number | null
  estimated_hours?: number | null
  req_math?: number | null
  req_coding?: number | null
  req_ml?: number | null
  theory_weight?: number | null
  practice_weight?: number | null
}

export interface OverlayEdgeCandidate extends OverlayCandidateBase {
  edge_id: string
  source_node_id: string
  target_node_id: string
  source_name_or_id?: string | null
  target_name_or_id?: string | null
  relation_type: string
}

export interface OverlayResourceBinding {
  id: string
  project_id: string
  resource_id: string
  target_type: string
  target_id: string
  source_result_id?: string | null
  binding_source: string
  created_at: string
  updated_at?: string
}

export interface OverlayResourceCandidate extends OverlayCandidateBase {
  resource_id: string
  title: string
  url?: string | null
  resource_type?: string | null
  summary?: string | null
  quality_score?: number | null
  evidence_source_id?: string | null
  source_evidence?: OverlaySource | null
  bindings?: OverlayResourceBinding[]
  binding_summary?: {
    count: number
    project_node_ids: string[]
    path_stage_ids: string[]
  }
}

export interface OverlaySessionSummary {
  session_id: string
  project_id: string
  mode: 'default' | 'custom_extension' | string
  session_status: string
  source_ids: string[]
  warnings: string[]
  provenance?: Record<string, unknown>
  error_message?: string | null
  created_at: string
  updated_at: string
}

export interface OverlayExtractionSessionResponse {
  session: OverlaySessionSummary
  sources: OverlaySource[]
  nodes: OverlayNodeCandidate[]
  edges: OverlayEdgeCandidate[]
  resources: OverlayResourceCandidate[]
  warnings: string[]
}

export interface PreviewOverlayExtractionPayloadRequest {
  source_ids: string[]
  mode?: 'default' | 'custom_extension'
  expansion_topic?: string | null
  constraint_note?: string | null
}

export interface OverlayExtractionPayloadPreviewResponse {
  source_ids: string[]
  mode: 'default' | 'custom_extension' | string
  extraction_payload: unknown
  warnings: string[]
  counts: {
    nodes: number
    edges: number
    resources: number
  }
  provenance: Record<string, unknown>
}

export interface ValidateOverlayExtractionPayloadRequest extends CreateOverlayExtractionSessionRequest {}

export interface OverlayCandidateValidationCounts {
  total: number
  valid: number
  invalid: number
  needs_review: number
}

export interface OverlayValidationSummary {
  has_blocking_errors: boolean
  needs_review: boolean
  invalid_count: number
  needs_review_count: number
}

export interface OverlayValidationCandidatePreview {
  index: number
  validation_status: OverlayValidationStatus
  validation_errors: string[]
  duplicate_candidates: { indexes?: number[]; [key: string]: unknown }
  [key: string]: unknown
}

export interface OverlayExtractionPayloadValidationResponse {
  source_ids: string[]
  warnings: string[]
  counts: {
    nodes: OverlayCandidateValidationCounts
    edges: OverlayCandidateValidationCounts
    resources: OverlayCandidateValidationCounts
  }
  summary: OverlayValidationSummary
  nodes: OverlayValidationCandidatePreview[]
  edges: OverlayValidationCandidatePreview[]
  resources: OverlayValidationCandidatePreview[]
}

export interface CreateOverlayExtractionSessionRequest {
  source_ids: string[]
  mode?: 'default' | 'custom_extension'
  extraction_payload?: unknown
  session_provenance?: Record<string, unknown> | null
  expansion_topic?: string | null
  constraint_note?: string | null
}

export interface CreateOverlayAutoDraftRequest {
  query?: string | null
  max_results?: number
  mode?: 'default' | 'custom_extension'
  constraint_note?: string | null
}

export type OverlayAutoDraftExtractionStatus = 'extracted' | 'empty_extraction' | 'extraction_failed'

export interface OverlayAutoDraftMetadata {
  query: string
  search_result_count: number
  selected_result_count: number
  selected_result_ids: string[]
  source_ids: string[]
  reused_source_count: number
  preview_counts: {
    nodes?: number
    edges?: number
    resources?: number
    [key: string]: unknown
  }
  validation_summary: Record<string, unknown>
  extraction_status?: OverlayAutoDraftExtractionStatus
  extraction_error?: string | null
  extraction_error_hint?: string | null
  expansion_context?: Record<string, unknown> | null
}

export interface OverlayAutoDraftResponse extends OverlayExtractionSessionResponse {
  auto_draft: OverlayAutoDraftMetadata
}

export interface OverlayNodeCandidatePatchRequest {
  name?: string | null
  group?: string | null
  category?: string | null
  summary?: string | null
  difficulty_final?: number | null
  importance_final?: number | null
  estimated_hours?: number | null
  req_math?: number | null
  req_coding?: number | null
  req_ml?: number | null
  theory_weight?: number | null
  practice_weight?: number | null
  confidence?: number | null
  legality_rationale?: string | null
  evidence_spans?: Array<Record<string, unknown>> | null
  provenance?: Record<string, unknown> | null
}

export interface OverlayEdgeCandidatePatchRequest {
  source_node_id?: string | null
  target_node_id?: string | null
  source_name_or_id?: string | null
  target_name_or_id?: string | null
  relation_type?: string | null
  confidence?: number | null
  legality_rationale?: string | null
}

export interface OverlayResourceCandidatePatchRequest {
  title?: string | null
  url?: string | null
  resource_type?: string | null
  summary?: string | null
  quality_score?: number | null
  confidence?: number | null
  evidence_source_id?: string | null
}

export interface GoalExtensionGapAnalysis {
  schema_version?: string
  draft_origin?: string
  user_goal?: string
  coverage_status?: string
  target_concepts?: string[]
  covered_by_current_graph?: {
    target_node_ids?: string[]
    target_node_names?: string[]
  }
  missing_concepts?: string[]
  why_current_graph_is_insufficient?: string
  recommended_review_focus?: string[]
}

export interface GoalExtensionDraftMetadata {
  schema_version?: string
  draft_origin?: string
  draft_engine?: string
  prompt_version?: string
  model?: string | null
  resolution_session_id?: string
  requires_user_review?: boolean
  can_directly_plan?: boolean
  requires_planning_enabled?: boolean
  safety_policy?: Record<string, unknown>
}

export interface GoalExtensionDraftProposal {
  schema_version?: string
  draft_origin?: string
  draft_engine?: string
  prompt_version?: string
  model?: string | null
  source_id?: string
  source_ids?: string[]
  goal_trace?: Record<string, unknown>
  missing_concepts?: string[]
  gap_analysis?: GoalExtensionGapAnalysis
  review_notes?: string[]
  draft_metadata?: GoalExtensionDraftMetadata
  extraction_payload?: unknown
  nodes?: Array<Record<string, unknown>>
  edges?: Array<Record<string, unknown>>
  resources?: Array<Record<string, unknown>>
  warnings?: string[]
  counts?: {
    nodes: number
    edges: number
    resources: number
  }
  requires_user_review?: boolean
  writes_formal_graph?: boolean
  writes_formal_path?: boolean
}

export interface GoalExtensionDraftProposalResponse {
  resolution_session_id: string
  project_id: string
  session_status: string
  expires_at?: string
  draft_proposal: GoalExtensionDraftProposal
}

export interface GraphWorkspaceErrorDetail {
  code: string
  message: string
  source: string
  recoverable: boolean
  detail?: Record<string, unknown>
}

export interface GraphWorkspaceData {
  project_id: string
  graph: GraphData
  projection_status: OverlayProjectionStatusResponse
  overlay_preflight?: OverlayPreflightResponse | null
  overlay_preflight_error?: string | null
  overlay_preflight_error_detail?: GraphWorkspaceErrorDetail | null
  persisted_search_results?: PersistedSearchResult[] | null
  persisted_search_results_error?: string | null
  persisted_search_results_error_detail?: GraphWorkspaceErrorDetail | null
  overlay_session?: OverlayExtractionSessionResponse | null
  overlay_session_error?: string | null
  overlay_session_error_detail?: GraphWorkspaceErrorDetail | null
  goal_draft_proposal?: GoalExtensionDraftProposalResponse | null
  goal_draft_error?: string | null
  goal_draft_error_detail?: GraphWorkspaceErrorDetail | null
}

export interface GraphCacheCounterStats {
  hits: number
  misses: number
  stores: number
  clears: number
  size: number
  max_size: number
  hit_rate: number
}

export interface GraphCacheStatsData {
  pack_graph_elements: GraphCacheCounterStats
  project_graph_snapshot: GraphCacheCounterStats
}

export interface GoalExtensionDraftResponse extends OverlayExtractionSessionResponse {
  goal_trace?: Record<string, unknown>
  missing_concepts?: string[]
  gap_analysis?: GoalExtensionGapAnalysis
  review_notes?: string[]
  draft_metadata?: GoalExtensionDraftMetadata
  draft_proposal?: GoalExtensionDraftProposal
}

export interface OverlayStatusResponse {
  element_type: 'node' | 'edge' | 'resource' | string
  element_id: string
  validation_status: OverlayValidationStatus
  review_status: OverlayReviewStatus
  planning_enabled: boolean
  promotion_status: OverlayPromotionStatus
}

export interface OverlayPromotionRequest {
  element_ids?: string[] | null
}

export interface OverlayPromotionCommitRequest extends OverlayPromotionRequest {
  admin_secret?: string | null
  requested_by?: string | null
}

export interface OverlayPromotionResourcePreview {
  id: string
  title: string
  resource_type: string
  description?: string
  node_ids: string[]
  stage_ids: string[]
  binding_decisions?: unknown[]
  lineage?: Record<string, unknown>
}

export interface OverlayPromotionBatchSummary {
  batch_id: string
  status: string
  requested_by?: string | null
  baseline_pack_hash?: string | null
  resulting_pack_hash?: string | null
}

export interface OverlayPromotionResponse {
  project_id?: string
  domain?: string
  valid?: boolean
  status?: string
  candidate_count?: number
  baseline_pack_hash?: string | null
  resulting_pack_hash?: string | null
  errors?: string[]
  warnings?: string[]
  nodes?: Array<Record<string, unknown>>
  edges?: Array<Record<string, unknown>>
  resources?: OverlayPromotionResourcePreview[]
  would_write?: string[]
  synced?: boolean
  reason?: string
  batch?: OverlayPromotionBatchSummary | null
  sync?: unknown
  [key: string]: unknown
}

export interface GraphEntityStage {
  id: string
  name: string
  order: number
  description: string
  category_keys: string[]
  node_ids: string[]
  resource_ids: string[]
}

export interface GraphEntityResource {
  id: string
  title: string
  resource_type: string
  description: string
  stage_ids: string[]
  node_ids: string[]
}

export interface GraphEntityMetadata {
  domain: string
  stages: GraphEntityStage[]
  resources: GraphEntityResource[]
  relationships: {
    stage_sequences: Array<{ source: string; target: string; type: 'PRECEDES' | string }>
    stage_nodes: Array<{ stage_id: string; node_id: string; type: 'CONTAINS' | string }>
    stage_resources: Array<{ stage_id: string; resource_id: string; type: 'HAS_RESOURCE' | string }>
    resource_nodes: Array<{ resource_id: string; node_id: string; type: 'COVERS' | string }>
  }
  is_empty: boolean
}

export function buildGraphQuery(params: GetGraphParams = {}): GetGraphParams {
  const scope = params.scope === 'domain' || params.scope === 'project' || params.scope === 'path' ? params.scope : DEFAULT_GRAPH_SCOPE
  const query: GetGraphParams = { scope }

  if (scope === 'path') {
    query.path_id = params.path_id || GRAPH_PATH_ID_LATEST
  }

  if (params.nodeId) {
    query.nodeId = params.nodeId
  }

  return query
}

export function buildPathGraphQuery(nodeId?: string | null): GraphRouteQuery {
  const query = buildGraphQuery({
    scope: 'path',
    path_id: GRAPH_PATH_ID_LATEST,
    nodeId: nodeId || undefined,
  })
  return Object.fromEntries(
    Object.entries(query).filter((entry): entry is [string, string] => typeof entry[1] === 'string'),
  )
}

export function normalizeGraphScope(value: unknown): GraphScope {
  const nextValue = Array.isArray(value) ? value[0] : value
  if (nextValue === 'domain' || nextValue === 'project' || nextValue === 'path') {
    return nextValue
  }
  return DEFAULT_GRAPH_SCOPE
}

export function normalizeGraphPathId(scope: GraphScope, value: unknown): string | undefined {
  const nextValue = Array.isArray(value) ? value[0] : value
  if (scope !== 'path') {
    return undefined
  }
  return typeof nextValue === 'string' && nextValue.trim() ? nextValue.trim() : GRAPH_PATH_ID_LATEST
}

export const graphApi = {
  getGraph: (projectId: string, params?: GetGraphParams, config?: RequestConfig): Promise<GraphData> =>
    request.get(`/projects/${projectId}/graph`, {
      ...config,
      params: buildGraphQuery(params),
    }),
  getGraphWorkspace: (projectId: string, params?: GraphWorkspaceParams, config?: RequestConfig): Promise<GraphWorkspaceData> =>
    request.get(`/projects/${projectId}/graph/workspace`, {
      ...config,
      params: {
        ...buildGraphQuery(params),
        include_persisted_search_results: params?.include_persisted_search_results || undefined,
        session_id: params?.session_id || undefined,
        goal_draft_resolution_session_id: params?.goal_draft_resolution_session_id || undefined,
      },
    }),
  getGraphCacheStats: (): Promise<GraphCacheStatsData> =>
    request.get('/graph/cache/stats'),
  seedGraph: (): Promise<GraphSyncResponse> =>
    request.post('/graph/seed'),
  syncGraph: (projectId: string): Promise<GraphSyncResponse> =>
    request.post(`/projects/${projectId}/graph/sync`),
  getGraphEntities: (projectId: string): Promise<GraphEntityMetadata> =>
    request.get(`/projects/${projectId}/graph/entities`),
  getOverlayProjectionStatus: (projectId: string): Promise<OverlayProjectionStatusResponse> =>
    request.get(`/projects/${projectId}/graph/overlay/projection/status`),
  getOverlayPreflight: (projectId: string): Promise<OverlayPreflightResponse> =>
    request.get(`/projects/${projectId}/graph/overlay/preflight`),
  reviewNode: (projectId: string, nodeId: string, status: ReviewStatus): Promise<any> =>
    request.patch(`/projects/${projectId}/graph/nodes/${nodeId}`, { status }),
  reviewEdge: (projectId: string, edgeId: GraphEdgeData['id'], status: ReviewStatus): Promise<any> =>
    request.patch(`/projects/${projectId}/graph/edges/${encodeURIComponent(edgeId)}`, { status }),
  createOverlaySource: (projectId: string, payload: OverlaySourceRequest): Promise<OverlaySource> =>
    request.post(`/projects/${projectId}/graph/overlay/sources`, payload),
  updateOverlaySource: (
    projectId: string,
    sourceId: string,
    payload: Partial<OverlaySourceRequest>,
  ): Promise<OverlaySource> =>
    request.patch(`/projects/${projectId}/graph/overlay/sources/${sourceId}`, payload),
  previewOverlayExtractionPayload: (
    projectId: string,
    payload: PreviewOverlayExtractionPayloadRequest,
  ): Promise<OverlayExtractionPayloadPreviewResponse> =>
    request.post(`/projects/${projectId}/graph/overlay/extraction-payload/preview`, payload),
  validateOverlayExtractionPayload: (
    projectId: string,
    payload: ValidateOverlayExtractionPayloadRequest,
  ): Promise<OverlayExtractionPayloadValidationResponse> =>
    request.post(`/projects/${projectId}/graph/overlay/extraction-payload/validate`, payload),
  createOverlayExtractionSession: (
    projectId: string,
    payload: CreateOverlayExtractionSessionRequest,
  ): Promise<OverlayExtractionSessionResponse> =>
    request.post(`/projects/${projectId}/graph/overlay/extraction-sessions`, payload),
  createOverlayAutoDraft: (
    projectId: string,
    payload: CreateOverlayAutoDraftRequest,
  ): Promise<OverlayAutoDraftResponse> =>
    request.post(`/projects/${projectId}/graph/overlay/auto-drafts`, payload),
  getGoalExtensionDraftProposal: (
    projectId: string,
    resolutionSessionId: string,
  ): Promise<GoalExtensionDraftProposalResponse> =>
    request.get(`/projects/${projectId}/goal-resolution/extension-drafts/${resolutionSessionId}/proposal`),
  createGoalExtensionDraft: (projectId: string, resolutionSessionId: string): Promise<GoalExtensionDraftResponse> =>
    request.post(`/projects/${projectId}/goal-resolution/extension-drafts`, {
      resolution_session_id: resolutionSessionId,
    }),
  getOverlayExtractionSession: (
    projectId: string,
    sessionId: string,
  ): Promise<OverlayExtractionSessionResponse> =>
    request.get(`/projects/${projectId}/graph/overlay/extraction-sessions/${sessionId}`),
  reviewOverlayElement: (
    projectId: string,
    elementGroup: OverlayElementGroup,
    elementId: string,
    reviewStatus: OverlayReviewStatus,
  ): Promise<OverlayStatusResponse> =>
    request.patch(`/projects/${projectId}/graph/overlay/${elementGroup}/${encodeURIComponent(elementId)}/review`, {
      review_status: reviewStatus,
    }),
  setOverlayPlanning: (
    projectId: string,
    elementGroup: OverlayElementGroup,
    elementId: string,
    planningEnabled: boolean,
  ): Promise<OverlayStatusResponse> =>
    request.patch(`/projects/${projectId}/graph/overlay/${elementGroup}/${encodeURIComponent(elementId)}/planning`, {
      planning_enabled: planningEnabled,
    }),
  updateOverlayNodeCandidate: (
    projectId: string,
    nodeId: string,
    payload: OverlayNodeCandidatePatchRequest,
  ): Promise<OverlayExtractionSessionResponse> =>
    request.patch(`/projects/${projectId}/graph/overlay/nodes/${encodeURIComponent(nodeId)}/candidate`, payload),
  updateOverlayEdgeCandidate: (
    projectId: string,
    edgeId: string,
    payload: OverlayEdgeCandidatePatchRequest,
  ): Promise<OverlayExtractionSessionResponse> =>
    request.patch(`/projects/${projectId}/graph/overlay/edges/${encodeURIComponent(edgeId)}/candidate`, payload),
  updateOverlayResourceCandidate: (
    projectId: string,
    resourceId: string,
    payload: OverlayResourceCandidatePatchRequest,
  ): Promise<OverlayExtractionSessionResponse> =>
    request.patch(`/projects/${projectId}/graph/overlay/resources/${encodeURIComponent(resourceId)}/candidate`, payload),
  previewOverlayPromotion: (
    projectId: string,
    payload?: OverlayPromotionRequest,
  ): Promise<OverlayPromotionResponse> =>
    request.post(`/projects/${projectId}/graph/overlay/promotion/preview`, payload ?? {}),
  commitOverlayPromotion: (
    projectId: string,
    payload: OverlayPromotionCommitRequest,
  ): Promise<OverlayPromotionResponse> =>
    request.post(`/projects/${projectId}/graph/overlay/promotion/commit`, payload),
}
