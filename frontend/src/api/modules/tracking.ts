import request from '../request'

export interface TrackingEvent {
  node_id: string
  event_type: 'start' | 'complete' | 'skip'
  note?: string
}

export interface TrackingEventResponse {
  id: string
  project_id: string
  node_id: string
  event_type: string
  note: string | null
  created_at: string
}

export interface TrackingSummary {
  total_nodes: number
  completed: number
  in_progress: number
  skipped: number
  pending: number
  completion_rate: number
}

export const trackingApi = {
  addEvent: (projectId: string, data: TrackingEvent): Promise<TrackingEventResponse> =>
    request.post(`/projects/${projectId}/tracking/events`, data),
  getEvents: (projectId: string): Promise<TrackingEventResponse[]> =>
    request.get(`/projects/${projectId}/tracking/events`),
  getSummary: (projectId: string): Promise<TrackingSummary> =>
    request.get(`/projects/${projectId}/tracking/summary`),
}
