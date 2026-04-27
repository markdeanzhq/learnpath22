import request from '../request'

export type GoalType = 'domain' | 'concept' | 'problem'
export type GoalTypeSelection = 'auto' | GoalType
export type PathMode = 'standard' | 'compressed' | 'theory_first' | 'practice_first'
export type CoverageStatus = 'covered' | 'partial' | 'in_domain_uncovered' | 'adjacent_domain' | 'cross_domain' | 'out_of_domain' | 'ambiguous'
export type CoverageResultType = 'select_candidate' | 'confirm_partial' | 'answer_clarification' | 'review_extension_draft' | 'boundary_reject'
export type DomainDecision = 'in_domain' | 'cross_domain' | 'out_of_domain' | 'ambiguous'
export type MlRelevance = 'core' | 'prerequisite' | 'application' | 'none' | 'unclear'

export interface GoalResolutionPreviewRequestDto {
  goal_text: string
  requested_goal_type?: GoalType
  domain?: string
}

export interface GoalResolutionNodeRef {
  node_id: string
  node_name: string
}

export interface GoalResolutionCandidate {
  candidate_id: string
  goal_type: GoalType
  target_node_ids: string[]
  target_node_names?: string[]
  target_nodes?: GoalResolutionNodeRef[]
  mode: string
  description: string
  template_id?: string | null
  resolve_source: string
  source_breakdown: Record<string, number>
  score: number
  score_breakdown: Record<string, unknown>
  explanation: string
  warnings: string[]
}

export interface GoalFramePlannerParameters {
  path_mode?: PathMode | null
  theory_weight?: number | null
  practice_weight?: number | null
  weekly_hours?: number | null
  deadline_weeks?: number | null
  explanation_focus: string[]
}

export interface GoalFrameSource {
  source: 'rules' | 'llm' | 'fallback'
  evidence: string
  confidence?: number | null
}

export interface GoalFrameV1 {
  schema_version: 'v1'
  raw_text: string
  domain: string
  goal_type?: GoalType | null
  target_concepts: string[]
  target_node_ids: string[]
  constraints: Record<string, unknown>
  preferences: Record<string, unknown>
  planner_parameters: GoalFramePlannerParameters
  uncertainties: string[]
  confidence: number
  sources: GoalFrameSource[]
}

export interface GoalUnderstandingEvidence {
  span: string
  label: string
  reason: string
}

export interface GoalUnderstandingV1 {
  schema_version: 'v1'
  raw_text: string
  domain_decision: DomainDecision
  primary_domain: string
  ml_relevance: MlRelevance
  goal_type?: GoalType | null
  target_concepts: string[]
  constraints: Record<string, unknown>
  preferences: Record<string, unknown>
  uncertainties: string[]
  clarification_question?: string | null
  confidence: number
  evidence: GoalUnderstandingEvidence[]
  prompt_version?: string | null
  model?: string | null
  warnings: string[]
}

export interface AuditTraceRef {
  trace_type: 'goal_resolution' | 'clarification' | 'variant_preview' | 'feedback_preview' | 'known_node_draft'
  trace_id: string
  pack_hash?: string | null
  project_graph_hash?: string | null
}

interface CoverageResponseBase {
  result_type: CoverageResultType
  coverage_status: CoverageStatus
  goal_frame: GoalFrameV1
  goal_understanding: GoalUnderstandingV1
  pack_hash?: string | null
  project_graph_hash?: string | null
  audit_trace?: AuditTraceRef | null
}

export interface SelectCandidateCoverageResponse extends CoverageResponseBase {
  result_type: 'select_candidate'
  coverage_status: 'covered' | 'adjacent_domain'
  session_id: string
  expires_at: string
  recommended_candidate_id: string
  candidates: GoalResolutionCandidate[]
  auto_detected_goal_type: GoalType
  effective_goal_type: GoalType
  warnings: string[]
}

export interface ConfirmPartialCoverageResponse extends CoverageResponseBase {
  result_type: 'confirm_partial'
  coverage_status: 'partial'
  session_id: string
  expires_at: string
  covered_target_node_ids: string[]
  missing_concepts: string[]
  candidates: GoalResolutionCandidate[]
}

export interface ClarificationQuestionOption {
  option_id: string
  label: string
  value: Record<string, unknown>
}

export interface ClarificationQuestion {
  question_id: string
  field: string
  prompt: string
  options: ClarificationQuestionOption[]
  allow_free_text: boolean
}

export interface AnswerClarificationCoverageResponse extends CoverageResponseBase {
  result_type: 'answer_clarification'
  coverage_status: 'ambiguous' | 'cross_domain'
  clarification_session_id: string
  expires_at: string
  turn_count: number
  max_turns: number
  questions: ClarificationQuestion[]
}

export interface ReviewExtensionDraftCoverageResponse extends CoverageResponseBase {
  result_type: 'review_extension_draft'
  coverage_status: 'in_domain_uncovered'
  missing_concepts: string[]
  draft_entry: Record<string, unknown>
  session_id?: string | null
  expires_at?: string | null
}

export interface BoundaryRejectCoverageResponse extends CoverageResponseBase {
  result_type: 'boundary_reject'
  coverage_status: 'out_of_domain' | 'adjacent_domain'
  reason_code: string
  reason_text: string
  rewrite_suggestions: string[]
}

export type GoalResolutionPreviewResponse =
  | SelectCandidateCoverageResponse
  | ConfirmPartialCoverageResponse
  | AnswerClarificationCoverageResponse
  | ReviewExtensionDraftCoverageResponse
  | BoundaryRejectCoverageResponse

export interface ClarificationAnswerDto {
  question_id: string
  selected_option_id?: string | null
  free_text?: string | null
}

export interface ClarificationAnswerRequestDto {
  answers: ClarificationAnswerDto[]
}

export interface ClarificationSessionResponse {
  clarification_session_id: string
  status: 'active' | 'resolved' | 'rejected' | 'expired' | 'stale'
  expires_at: string
  turn_count: number
  max_turns: number
  questions: ClarificationQuestion[]
  goal_frame?: GoalFrameV1 | null
  coverage_response?: GoalResolutionPreviewResponse | null
}

export interface CreateProjectDto {
  title: string
  goal_text: string
  resolution_session_id: string
  selected_candidate_id: string
  goal_type?: GoalType
  accept_partial?: boolean
  path_mode?: PathMode
}

export interface UpdateProjectGoalResolutionDto {
  goal_text: string
  resolution_session_id: string
  selected_candidate_id: string
  goal_type?: GoalType
  accept_partial?: boolean
  path_mode?: PathMode
}

export interface ProjectGoalResolutionSummary {
  requested_goal_type?: GoalType | null
  auto_detected_goal_type?: GoalType | null
  selected_candidate_id: string
  confirmed_target_node_ids: string[]
  partial_accepted: boolean
  missing_concepts: string[]
}

export interface Project {
  id: string
  title: string
  goal_text: string
  goal_type: GoalType | string
  domain: string
  status: string
  path_mode?: PathMode | string
  created_at: string
  updated_at: string
  goal_resolution?: ProjectGoalResolutionSummary | null
}

export const projectApi = {
  preview: (data: GoalResolutionPreviewRequestDto): Promise<GoalResolutionPreviewResponse> =>
    request.post('/goal-resolution/preview', data),
  answerClarification: (sessionId: string, data: ClarificationAnswerRequestDto): Promise<ClarificationSessionResponse> =>
    request.post(`/goal-resolution/clarifications/${sessionId}/answers`, data),
  create: (data: CreateProjectDto): Promise<Project> => request.post('/projects', data),
  previewForProject: (projectId: string, data: GoalResolutionPreviewRequestDto): Promise<GoalResolutionPreviewResponse> =>
    request.post(`/projects/${projectId}/goal-resolution/preview`, data),
  answerProjectClarification: (projectId: string, sessionId: string, data: ClarificationAnswerRequestDto): Promise<ClarificationSessionResponse> =>
    request.post(`/projects/${projectId}/goal-resolution/clarifications/${sessionId}/answers`, data),
  confirmGoalResolution: (projectId: string, data: UpdateProjectGoalResolutionDto): Promise<Project> =>
    request.put(`/projects/${projectId}/goal-resolution`, data),
  get: (id: string): Promise<Project> => request.get(`/projects/${id}`),
  list: (): Promise<Project[]> => request.get('/projects'),
  delete: (id: string): Promise<void> => request.delete(`/projects/${id}`),
}
