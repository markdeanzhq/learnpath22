import request from '../request'

export interface PathTask {
  node_id: string
  name: string
  order_in_stage: number
  difficulty: number
  importance: number
  estimated_hours: number
}

export interface PathStage {
  stage_index: number
  stage_name: string
  tasks: PathTask[]
  estimated_hours: number | null
}

export interface BudgetSummary {
  status: string
  total_hours: number
  weekly_hours: number
  estimated_weeks: number
  suggestion: string
}

export interface PlanAudit {
  goal_result: {
    goal_type: string
    target_node_ids: string[]
    mode: string
    [key: string]: any
  }
  profile_snapshot: {
    math_level: number
    coding_level: number
    ml_level: number
    theory_weight: number
    practice_weight: number
    weekly_hours: number
    deadline_weeks: number
  }
  budget_summary: BudgetSummary
  reinforcement_logs: Record<string, {
    decision_type: string
    gap: Record<string, number>
    [key: string]: any
  }>
  ordering_logs: Record<string, any>
  stage_logs: Record<string, {
    decision_type: string
    assigned_stage: string
    reasons: string[]
  }>
}

export interface NodeExplanation {
  node_id: string
  node_name: string
  reason: string
  gap?: Record<string, number> | null
  decision_type: string
  raw_reason?: string | null
}

export interface OrderExplanation {
  node_id: string
  node_name: string
  priority_score: number
  goal_relevance: number
  factors: string[]
}

export interface StageExplanation {
  node_id: string
  node_name: string
  assigned_stage: string
  reasons: string[]
  rationale?: string | null
  raw_rationale?: string | null
}

export interface BudgetExplanation {
  total_hours: number
  weekly_hours: number
  estimated_weeks: number
  status: string
  suggestion: string
}

export interface ReinforcementExplanation {
  node_id: string
  node_name: string
  gap: Record<string, number>
  reinforce_score: number
  reasons: string[]
}

export interface DependencyChainExplanation {
  target_node_id: string
  target_node_name: string
  chain_node_ids: string[]
  chain_node_names: string[]
  reason: string
}

export interface ExplanationProvenance {
  truth_source: 'plan_audit_snapshot'
  fallback_used: boolean
  fallback_reasons: string[]
  live_pack_fields: string[]
}

export interface PolishMeta {
  requested: boolean
  applied: boolean
  scope: string[]
  fallback_reason?: string | null
}

export interface OverviewSummary {
  headline: string
  goal_names: string[]
  node_count: number
  total_hours?: number | null
  budget_status?: string | null
  path_mode?: string | null
  notes: string[]
}

export interface GoalResolutionSummary {
  final_goal_text?: string | null
  goal_type?: string | null
  mode?: string | null
  resolve_source?: string | null
  target_node_ids: string[]
  target_node_names: string[]
  source_breakdown: Record<string, unknown>
  warnings: string[]
}

export interface GenerationStep {
  step_id: string
  title: string
  summary: string
  evidence_items: string[]
  node_ids: string[]
}

export type ExplanationNodeGroupId = 'target' | 'prerequisite' | 'reinforced'

export interface NodeGroupSummary {
  group_id: ExplanationNodeGroupId
  title: string
  summary: string
  node_ids: string[]
  nodes: Array<Record<string, unknown>>
}

export interface OrderingSummary {
  summary: string
  mode?: string | null
  ordered_node_ids: string[]
  key_factors: string[]
}

export interface StageSummary {
  summary: string
  stage_count: number
  stages: Array<Record<string, unknown>>
}

export interface ReadableBudgetSummary {
  summary: string
  total_hours?: number | null
  weekly_hours?: number | null
  estimated_weeks?: number | null
  status?: string | null
  path_mode?: string | null
  compressed_dependency_note?: string | null
}

export interface TraceSummary {
  pack_version?: string | null
  project_graph_hash?: string | null
  overlay_node_count: number
  overlay_edge_count: number
  overlay_lineage_items: Array<Record<string, unknown>>
  fallback_used: boolean
  fallback_reasons: string[]
  live_pack_fields: string[]
}

export interface AuditHighlight {
  key: string
  title: string
  summary: string
  value?: unknown
  source?: string | null
}

export interface ExplanationReadability {
  overview_summary: OverviewSummary
  goal_resolution_summary: GoalResolutionSummary
  generation_steps: GenerationStep[]
  node_groups: NodeGroupSummary[]
  ordering_summary: OrderingSummary
  stage_summary: StageSummary
  budget_summary?: ReadableBudgetSummary | null
  trace_summary: TraceSummary
  audit_highlights: AuditHighlight[]
}

export interface ExplanationMeta {
  plan_version?: number | null
  pack_version?: string | null
  project_graph_hash?: string | null
  provenance: ExplanationProvenance
  polish: PolishMeta
}

export interface ExplanationResponse {
  node_explanations: NodeExplanation[]
  ordering_explanations: OrderExplanation[]
  stage_explanations: StageExplanation[]
  budget_explanation: BudgetExplanation | null
  reinforcement_explanations: ReinforcementExplanation[]
  dependency_chain_explanations: DependencyChainExplanation[]
  readability?: ExplanationReadability | null
  meta?: ExplanationMeta | null
}

export type ExplanationQuestionId =
  | 'why_path_order'
  | 'why_include_node'
  | 'why_stage_assignment'
  | 'budget_feasibility'
  | 'what_if_time_limited'

export interface EvidenceRef {
  source: string
  key?: string | null
  node_id?: string | null
  summary?: string | null
}

export interface ExplanationAskRequest {
  question_id: ExplanationQuestionId
  node_id?: string | null
}

export interface ExplanationAskResponse {
  question_id: ExplanationQuestionId
  answer: string
  evidence_refs: EvidenceRef[]
  limitations: string[]
  ai_used: boolean
  fallback_reason?: string | null
}

export interface LearningPlan {
  id: string
  project_id: string
  version: number
  stages: PathStage[]
  budget_status: string | null
  total_hours: number | null
  audit: PlanAudit | null
  node_count?: number
  reinforced_ids?: string[]
  text_output?: string
}

export interface ReplanDiff {
  added?: string[]
  removed?: string[]
  unchanged?: string[]
  completed?: string[]
  skipped?: string[]
  pending?: string[]
}

export interface ReplanDiffDetailItem {
  node_id: string
  node_name: string
}

export interface ReplanResult {
  id: string
  version: number
  mode: string
  stages: PathStage[]
  budget_status: string
  total_hours: number
  diff: ReplanDiff | null
  diff_details?: Partial<Record<keyof ReplanDiff, ReplanDiffDetailItem[]>> | null
  reason: string
}

export const planApi = {
  generate: (projectId: string): Promise<LearningPlan> =>
    request.post(`/projects/${projectId}/plans`),
  getLatest: (projectId: string): Promise<LearningPlan> =>
    request.get(`/projects/${projectId}/plans/latest`),
  getExplanation: (projectId: string, polish = false, signal?: AbortSignal): Promise<ExplanationResponse> =>
    request.get(`/projects/${projectId}/explanation`, { params: { polish }, signal }),
  askExplanation: (projectId: string, payload: ExplanationAskRequest): Promise<ExplanationAskResponse> =>
    request.post(`/projects/${projectId}/explanation/ask`, payload),
  replan: (projectId: string, mode: string, reason?: string): Promise<ReplanResult> =>
    request.post(`/projects/${projectId}/replans`, {
      mode,
      reason: reason || (mode === 'progress_aware' ? '进度感知重规划' : '画像更新后重规划'),
    }),
}
