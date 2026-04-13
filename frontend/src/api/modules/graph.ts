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

export const graphApi = {
  getGraph: (projectId: string, params?: GetGraphParams): Promise<GraphData> =>
    request.get(`/projects/${projectId}/graph`, {
      params: {
        scope: params?.scope,
      },
    }),
  syncGraph: (projectId: string): Promise<GraphSyncResponse> =>
    request.post(`/projects/${projectId}/graph/sync`),
  reviewNode: (projectId: string, nodeId: string, status: ReviewStatus): Promise<any> =>
    request.patch(`/projects/${projectId}/graph/nodes/${nodeId}`, { status }),
  reviewEdge: (projectId: string, edgeId: GraphEdgeData['id'], status: ReviewStatus): Promise<any> =>
    request.patch(`/projects/${projectId}/graph/edges/${encodeURIComponent(edgeId)}`, { status }),
}
