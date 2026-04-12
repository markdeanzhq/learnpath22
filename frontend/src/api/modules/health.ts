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
}

export interface PutConfigPayload {
  llm_base_url?: string
  llm_model?: string
  llm_api_key?: string
  search_api_key?: string
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

const silentRequestConfig: RequestConfig = {
  silent: true,
}

export const healthApi = {
  checkHealth: (): Promise<HealthStatus> => request.get('/health'),
  getConfig: (): Promise<ConfigStatus> => request.get('/health/config'),
  updateConfig: (payload: PutConfigPayload): Promise<PutConfigResponse> => request.put('/health/config', payload),
  updateConfigSilently: (payload: PutConfigPayload): Promise<PutConfigResponse> => request.put('/health/config', payload, silentRequestConfig),
  testLlm: (): Promise<LlmTestResponse> => request.get('/health/llm'),
}
