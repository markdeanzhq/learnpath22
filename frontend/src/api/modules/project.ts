import request from '../request'

export interface CreateProjectDto {
  title: string
  goal_text: string
  goal_type: 'domain' | 'concept' | 'problem'
  domain?: string
}

export interface Project {
  id: string
  title: string
  goal_text: string
  goal_type: string
  domain: string
  status: string
  created_at: string
}

export const projectApi = {
  create: (data: CreateProjectDto): Promise<Project> => request.post('/projects', data),
  get: (id: string): Promise<Project> => request.get(`/projects/${id}`),
  list: (): Promise<Project[]> => request.get('/projects'),
  delete: (id: string): Promise<void> => request.delete(`/projects/${id}`),
}
