import request from '../request'

export type GraphScope = 'domain' | 'project' | 'path'
export const DEFAULT_GRAPH_SCOPE: GraphScope = 'project'
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

export interface GraphSyncResponse {
  domain: string
  version: string
  pack_hash: string
  synced: boolean
  forced?: boolean
  reason: 'unchanged' | 'changed' | 'forced' | string
  nodes: number
  edges: number
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

export interface CreateOverlayExtractionSessionRequest {
  source_ids: string[]
  mode?: 'default' | 'custom_extension'
  extraction_payload?: unknown
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
  const scope = params.scope === 'domain' || params.scope === 'path' ? params.scope : DEFAULT_GRAPH_SCOPE
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
  if (nextValue === 'domain' || nextValue === 'path') {
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
  getGraph: (projectId: string, params?: GetGraphParams): Promise<GraphData> =>
    request.get(`/projects/${projectId}/graph`, {
      params: buildGraphQuery(params),
    }),
  syncGraph: (projectId: string): Promise<GraphSyncResponse> =>
    request.post(`/projects/${projectId}/graph/sync`),
  getGraphEntities: (projectId: string): Promise<GraphEntityMetadata> =>
    request.get(`/projects/${projectId}/graph/entities`),
  getOverlayProjectionStatus: (projectId: string): Promise<OverlayProjectionStatusResponse> =>
    request.get(`/projects/${projectId}/graph/overlay/projection/status`),
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
  createOverlayExtractionSession: (
    projectId: string,
    payload: CreateOverlayExtractionSessionRequest,
  ): Promise<OverlayExtractionSessionResponse> =>
    request.post(`/projects/${projectId}/graph/overlay/extraction-sessions`, payload),
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
