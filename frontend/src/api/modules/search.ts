import request from '../request'

export interface SearchResultItem {
  title: string
  url: string
  snippet: string
  score: number
  provider?: string
}

export interface SearchResponse {
  query: string
  results: SearchResultItem[]
  count: number
  source: string
}

export interface PersistSearchResultRequest {
  query: string
  provider?: string
  url: string
  title: string
  snippet?: string | null
  result_rank?: number | null
  retrieved_at?: string | null
  summary?: string | null
  quality_status?: string | null
  is_selected?: boolean
  metadata_json?: string | null
}

export interface PersistedSearchResult {
  result_id: string
  source_id?: string | null
  query: string
  provider: string
  url: string
  title: string
  snippet?: string | null
  result_rank?: number | null
  retrieved_at?: string | null
  summary?: string | null
  quality_status?: string | null
  is_selected: boolean
  binding_count: number
  created_at: string
}

export interface BridgedSearchResult {
  result_id: string
  source_id: string
  source_type: 'search_url' | string
  reused: boolean
  repaired: boolean
}

export interface BridgeSearchResultsResponse {
  source_ids: string[]
  results: BridgedSearchResult[]
}

export const searchApi = {
  search: (projectId: string, query: string, maxResults = 5): Promise<SearchResponse> =>
    request.post(`/projects/${projectId}/search`, {
      query,
      max_results: maxResults,
    }),
  persistResult: (projectId: string, payload: PersistSearchResultRequest): Promise<PersistedSearchResult> =>
    request.post(`/projects/${projectId}/search-results`, payload),
  listPersistedResults: (projectId: string): Promise<PersistedSearchResult[]> =>
    request.get(`/projects/${projectId}/search-results`),
  bridgeOverlaySources: (projectId: string, resultIds: string[]): Promise<BridgeSearchResultsResponse> =>
    request.post(`/projects/${projectId}/search-results/bridge-overlay-sources`, {
      result_ids: resultIds,
    }),
}
