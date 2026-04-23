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

export interface ExplanationResponse {
  node_explanations: NodeExplanation[]
  ordering_explanations: OrderExplanation[]
  stage_explanations: StageExplanation[]
  budget_explanation: BudgetExplanation | null
  reinforcement_explanations: ReinforcementExplanation[]
  dependency_chain_explanations: DependencyChainExplanation[]
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
  getExplanation: (projectId: string, polish = false): Promise<ExplanationResponse> =>
    request.get(`/projects/${projectId}/explanation`, { params: { polish } }),
  replan: (projectId: string, mode: string, reason?: string): Promise<ReplanResult> =>
    request.post(`/projects/${projectId}/replans`, {
      mode,
      reason: reason || (mode === 'progress_aware' ? '进度感知重规划' : '画像更新后重规划'),
    }),
}
