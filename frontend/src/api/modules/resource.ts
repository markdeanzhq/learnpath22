import request from '../request'

export interface ResourceItem {
  id: string
  title: string
  url: string
  snippet?: string | null
  score?: number | null
  source_type: 'static' | 'tavily_auto' | 'manual' | string
  stage_name?: string | null
  node_id?: string | null
  created_at?: string | null
}

export interface StageResourceGroup {
  stage_name: string
  resources: ResourceItem[]
}

export interface PlanResourcesResponse {
  path_id: string
  stages: StageResourceGroup[]
}

export const resourceApi = {
  getPlanResources: (projectId: string, pathId: string): Promise<PlanResourcesResponse> =>
    request.get(`/projects/${projectId}/plans/${pathId}/resources`),
  recommendPlanResources: (projectId: string, pathId: string): Promise<PlanResourcesResponse> =>
    request.post(`/projects/${projectId}/plans/${pathId}/resources/recommend`),
  bindManualResource: (
    projectId: string,
    pathId: string,
    payload: { stage_name?: string; node_id?: string; title: string; url: string; snippet?: string }
  ): Promise<ResourceItem> =>
    request.post(`/projects/${projectId}/plans/${pathId}/resources/bind`, payload),
}
