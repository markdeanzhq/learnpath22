import request from '../request'

export interface SearchResultItem {
  title: string
  url: string
  snippet: string
  score: number
}

export interface SearchResponse {
  query: string
  results: SearchResultItem[]
  count: number
  source: string
}

export const searchApi = {
  search: (projectId: string, query: string, maxResults = 5): Promise<SearchResponse> =>
    request.post(`/projects/${projectId}/search`, {
      query,
      max_results: maxResults,
    }),
}
