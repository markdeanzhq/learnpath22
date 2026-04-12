import request from '../request'

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
}

export interface SubmitProfileDto {
  math_level: number
  coding_level: number
  ml_level: number
  theory_weight: number
  practice_weight: number
  weekly_hours: number
  deadline_weeks?: number
  raw_answers_json?: string
}

export interface QuestionOption {
  label: string
  value: number
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

export const profileApi = {
  submit: (projectId: string, data: SubmitProfileDto): Promise<LearnerProfile> =>
    request.post(`/projects/${projectId}/profiles`, data),
  getLatest: (projectId: string): Promise<LearnerProfile> =>
    request.get(`/projects/${projectId}/profiles/latest`),
  getQuestions: (projectId: string): Promise<QuestionResponse> =>
    request.post(`/projects/${projectId}/collector/questions`),
  submitAnswers: (projectId: string, data: { answers: Array<{ question_id: string; field: string; value: number }> }): Promise<LearnerProfile> =>
    request.post(`/projects/${projectId}/collector/submit`, data),
}
