import request from '../request'
import type { RequestConfig } from '../request'

export interface HealthStatus {
  status: string
  project: string
  version: string
}

export interface ConfigStatus {
  llm_base_url: string
  llm_model: string
  llm_api_key_set: boolean
  search_api_key_set: boolean
  llm_explanation_polish: boolean
}

export interface PutConfigPayload {
  llm_base_url?: string
  llm_model?: string
  llm_api_key?: string
  search_api_key?: string
  llm_explanation_polish?: boolean
}

export interface PutConfigResponse extends ConfigStatus {
  message: string
}

export interface LlmTestResponse {
  status: 'ok' | 'skipped' | 'error'
  base_url?: string
  model?: string
  reason?: string
}

export type HealthServiceStatus = 'ok' | 'skipped' | 'error' | 'blocked' | 'missing' | 'unknown'

export interface SearchHealthResponse {
  status: 'ok' | 'skipped' | 'error'
  ready: boolean
  provider: string
  reason?: string
}

export interface ReadinessServiceStatus {
  status: HealthServiceStatus
  ready: boolean
  reason?: string
  provider?: string
  base_url?: string
  model?: string
  in_sync?: boolean
  domain?: string
  version?: string
  pack_hash?: string
  main_graph_synced?: boolean
  entity_graph_synced?: boolean
  nodes?: number
  edges?: number
}

interface ReadinessResponsePayload {
  status: 'ready' | 'degraded'
  ready: boolean
  core_ready?: boolean
  demo_ready?: boolean
  enhanced_ready?: boolean
  services: Partial<{
    sqlite: ReadinessServiceStatus
    neo4j: ReadinessServiceStatus
    graph_sync: ReadinessServiceStatus
    llm: ReadinessServiceStatus
    search: ReadinessServiceStatus
  }>
}

export interface ReadinessResponse {
  status: 'ready' | 'degraded'
  ready: boolean
  core_ready: boolean
  demo_ready: boolean
  enhanced_ready: boolean
  services: {
    sqlite: ReadinessServiceStatus
    neo4j: ReadinessServiceStatus
    graph_sync: ReadinessServiceStatus
    llm: ReadinessServiceStatus
    search: ReadinessServiceStatus
  }
}

const silentRequestConfig: RequestConfig = {
  silent: true,
}

function ensureServiceStatus(
  service: ReadinessServiceStatus | undefined,
  fallback: ReadinessServiceStatus,
): ReadinessServiceStatus {
  return service ?? fallback
}

function normalizeReadiness(payload: ReadinessResponsePayload): ReadinessResponse {
  const sqlite = ensureServiceStatus(payload.services.sqlite, { status: 'error', ready: false, reason: 'SQLite 状态缺失' })
  const neo4j = ensureServiceStatus(payload.services.neo4j, { status: 'error', ready: false, reason: 'Neo4j 状态缺失' })
  const llm = ensureServiceStatus(payload.services.llm, { status: 'skipped', ready: false, reason: 'LLM 状态缺失' })
  const search = ensureServiceStatus(payload.services.search, { status: 'skipped', ready: false, reason: '搜索状态缺失' })
  const graphSync = ensureServiceStatus(payload.services.graph_sync, {
    status: sqlite.ready && neo4j.ready ? 'unknown' : 'blocked',
    ready: sqlite.ready && neo4j.ready,
    domain: 'machine_learning',
    reason: sqlite.ready && neo4j.ready
      ? '联调接口未单独返回图谱同步状态，当前按论文主链依赖兼容估算'
      : '联调接口未返回图谱同步状态，且论文主链基础依赖未全部就绪',
  })
  const coreReady = payload.core_ready ?? (sqlite.ready && neo4j.ready && graphSync.ready)
  const demoReady = payload.demo_ready ?? coreReady
  const enhancedReady = payload.enhanced_ready ?? (llm.ready && search.ready)
  const ready = demoReady && enhancedReady

  return {
    status: ready ? 'ready' : 'degraded',
    ready,
    core_ready: coreReady,
    demo_ready: demoReady,
    enhanced_ready: enhancedReady,
    services: {
      sqlite,
      neo4j,
      graph_sync: graphSync,
      llm,
      search,
    },
  }
}

export const healthApi = {
  checkHealth: (): Promise<HealthStatus> => request.get('/health'),
  getConfig: (): Promise<ConfigStatus> => request.get('/health/config'),
  getConfigSilently: (): Promise<ConfigStatus> => request.get('/health/config', silentRequestConfig),
  updateConfig: (payload: PutConfigPayload): Promise<PutConfigResponse> => request.put('/health/config', payload),
  updateConfigSilently: (payload: PutConfigPayload): Promise<PutConfigResponse> => request.put('/health/config', payload, silentRequestConfig),
  testLlm: (): Promise<LlmTestResponse> => request.get('/health/llm'),
  getSearchReadiness: (): Promise<SearchHealthResponse> => request.get('/health/search', silentRequestConfig),
  getReadiness: (): Promise<ReadinessResponse> => (request.get('/health/readiness', silentRequestConfig) as Promise<ReadinessResponsePayload>).then(normalizeReadiness),
}
