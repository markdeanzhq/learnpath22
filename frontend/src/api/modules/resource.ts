import request from '../request'

export interface ResourceItem {
  id: string
  title: string
  url: string
  snippet?: string | null
  score?: number | null
  source_type: 'static' | 'tavily_auto' | 'manual' | string
  preference_match?: 'mixed' | 'preferred' | 'available' | string | null
  preference_reason?: string | null
  stage_name?: string | null
  node_id?: string | null
  created_at?: string | null
}

export interface NodeResourceGroup {
  node_id: string
  node_name: string
  resources: ResourceItem[]
}

export interface StageResourceGroup {
  stage_name: string
  stage_resources: ResourceItem[]
  nodes: NodeResourceGroup[]
}

export interface PlanResourcesResponse {
  path_id: string
  stages: StageResourceGroup[]
}

export interface ProjectResourceBindingRequest {
  resource_id: string
  target_type: 'project_node' | 'path_stage'
  target_id: string
  source_result_id?: string | null
  binding_source?: string
}

export interface ProjectResourceBindingResponse {
  id: string
  project_id: string
  resource_id: string
  target_type: string
  target_id: string
  source_result_id?: string | null
  binding_source: string
  created_at: string
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
  bindProjectResource: (
    projectId: string,
    payload: ProjectResourceBindingRequest,
  ): Promise<ProjectResourceBindingResponse> =>
    request.post(`/projects/${projectId}/resources/bindings`, payload),
}
