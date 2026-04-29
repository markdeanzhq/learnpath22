import request from '../request'

export type LearningGoalOrientation = 'foundation' | 'exam' | 'project' | 'research' | 'career'
export type ResourcePreference = 'mixed' | 'text' | 'video' | 'code' | 'paper'

export interface LearnerProfile {
  id: string
  project_id: string
  math_level: number
  coding_level: number
  ml_level: number
  theory_weight: number
  practice_weight: number
  weekly_hours: number
  deadline_weeks: number | null
  path_mode_preference?: string | null
  learning_goal_orientation?: LearningGoalOrientation | null
  resource_preference?: ResourcePreference | null
  practice_intensity?: number
  persona_label?: string | null
  persona_summary?: string | null
  persona_evidence?: string | null
}

export interface SubmitProfileDto {
  math_level: number
  coding_level: number
  ml_level: number
  theory_weight: number
  practice_weight: number
  weekly_hours: number
  deadline_weeks?: number
  path_mode_preference?: string | null
  learning_goal_orientation?: LearningGoalOrientation | null
  resource_preference?: ResourcePreference | null
  practice_intensity?: number
  raw_answers_json?: string
}

export interface QuestionOption {
  label: string
  value: number | string
}

export interface QuestionItem {
  id: string
  field: string
  question: string
  options: QuestionOption[]
}

export interface QuestionResponse {
  questions: QuestionItem[]
  source: string
}

export interface SubmitAnswersDto {
  source?: string
  answers: Array<{ question_id: string; field: string; value: number | string }>
}

export const profileApi = {
  submit: (projectId: string, data: SubmitProfileDto): Promise<LearnerProfile> =>
    request.post(`/projects/${projectId}/profiles`, data),
  getLatest: (projectId: string): Promise<LearnerProfile> =>
    request.get(`/projects/${projectId}/profiles/latest`),
  getQuestions: (projectId: string): Promise<QuestionResponse> =>
    request.post(`/projects/${projectId}/collector/questions`),
  submitAnswers: (projectId: string, data: SubmitAnswersDto): Promise<LearnerProfile> =>
    request.post(`/projects/${projectId}/collector/submit`, data),
}
