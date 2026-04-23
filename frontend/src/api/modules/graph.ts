import request from '../request'

export type GraphScope = 'domain' | 'project'
export type GraphEmptyReason = 'project_latest_plan_missing' | string
export type ReviewStatus = 'pending' | 'confirmed' | 'removed'

export interface GraphNodeData {
  id: string
  label?: string
  category?: string
  group_id?: string
  difficulty?: number
  importance?: number
  estimated_hours?: number
  is_main_path?: boolean
  review_status?: ReviewStatus
  [key: string]: any
}

export interface GraphEdgeData {
  id: string
  source: string
  target: string
  type?: string
  reason?: string
  review_status?: ReviewStatus
  [key: string]: any
}

export type GraphElement =
  | {
      group: 'nodes'
      data: GraphNodeData
    }
  | {
      group: 'edges'
      data: GraphEdgeData
    }

export interface GetGraphParams {
  scope?: GraphScope
}

export interface GraphData {
  scope: GraphScope
  elements: GraphElement[]
  is_empty: boolean
  empty_reason?: GraphEmptyReason
  message?: string
  node_ids?: string[]
}

export interface GraphSyncResponse {
  domain: string
  version: string
  pack_hash: string
  synced: boolean
  forced?: boolean
  reason: 'unchanged' | 'changed' | 'forced' | string
  nodes: number
  edges: number
}

export interface GraphEntityStage {
  id: string
  name: string
  order: number
  description: string
  category_keys: string[]
  node_ids: string[]
  resource_ids: string[]
}

export interface GraphEntityResource {
  id: string
  title: string
  resource_type: string
  description: string
  stage_ids: string[]
  node_ids: string[]
}

export interface GraphEntityMetadata {
  domain: string
  stages: GraphEntityStage[]
  resources: GraphEntityResource[]
  relationships: {
    stage_sequences: Array<{ source: string; target: string; type: 'PRECEDES' | string }>
    stage_nodes: Array<{ stage_id: string; node_id: string; type: 'CONTAINS' | string }>
    stage_resources: Array<{ stage_id: string; resource_id: string; type: 'HAS_RESOURCE' | string }>
    resource_nodes: Array<{ resource_id: string; node_id: string; type: 'COVERS' | string }>
  }
  is_empty: boolean
}

export const graphApi = {
  getGraph: (projectId: string, params?: GetGraphParams): Promise<GraphData> =>
    request.get(`/projects/${projectId}/graph`, {
      params: {
        scope: params?.scope,
      },
    }),
  syncGraph: (projectId: string): Promise<GraphSyncResponse> =>
    request.post(`/projects/${projectId}/graph/sync`),
  getGraphEntities: (projectId: string): Promise<GraphEntityMetadata> =>
    request.get(`/projects/${projectId}/graph/entities`),
  reviewNode: (projectId: string, nodeId: string, status: ReviewStatus): Promise<any> =>
    request.patch(`/projects/${projectId}/graph/nodes/${nodeId}`, { status }),
  reviewEdge: (projectId: string, edgeId: GraphEdgeData['id'], status: ReviewStatus): Promise<any> =>
    request.patch(`/projects/${projectId}/graph/edges/${encodeURIComponent(edgeId)}`, { status }),
}
