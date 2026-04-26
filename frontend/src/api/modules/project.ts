import request from '../request'

export type GoalType = 'domain' | 'concept' | 'problem'
export type GoalTypeSelection = 'auto' | GoalType

export interface GoalResolutionPreviewRequestDto {
  goal_text: string
  requested_goal_type?: GoalType
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

export interface GoalResolutionPreviewResponse {
  session_id: string
  expires_at: string
  auto_detected_goal_type: GoalType
  effective_goal_type: GoalType
  recommended_candidate_id: string
  candidates: GoalResolutionCandidate[]
}

export interface CreateProjectDto {
  title: string
  goal_text: string
  resolution_session_id: string
  selected_candidate_id: string
  goal_type?: GoalType
}

export interface UpdateProjectGoalResolutionDto {
  goal_text: string
  resolution_session_id: string
  selected_candidate_id: string
  goal_type?: GoalType
}

export interface ProjectGoalResolutionSummary {
  requested_goal_type?: GoalType | null
  auto_detected_goal_type?: GoalType | null
  selected_candidate_id: string
  confirmed_target_node_ids: string[]
}

export interface Project {
  id: string
  title: string
  goal_text: string
  goal_type: GoalType | string
  domain: string
  status: string
  created_at: string
  updated_at: string
  goal_resolution?: ProjectGoalResolutionSummary | null
}

export const projectApi = {
  preview: (data: GoalResolutionPreviewRequestDto): Promise<GoalResolutionPreviewResponse> =>
    request.post('/goal-resolution/preview', data),
  create: (data: CreateProjectDto): Promise<Project> => request.post('/projects', data),
  previewForProject: (projectId: string, data: GoalResolutionPreviewRequestDto): Promise<GoalResolutionPreviewResponse> =>
    request.post(`/projects/${projectId}/goal-resolution/preview`, data),
  confirmGoalResolution: (projectId: string, data: UpdateProjectGoalResolutionDto): Promise<Project> =>
    request.put(`/projects/${projectId}/goal-resolution`, data),
  get: (id: string): Promise<Project> => request.get(`/projects/${id}`),
  list: (): Promise<Project[]> => request.get('/projects'),
  delete: (id: string): Promise<void> => request.delete(`/projects/${id}`),
}
