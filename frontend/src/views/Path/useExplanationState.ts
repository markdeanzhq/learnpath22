import { onBeforeUnmount, ref, type Ref } from 'vue'
import {
  planApi,
  type ExplanationAskRequest,
  type ExplanationAskResponse,
  type ExplanationResponse,
} from '@/api/modules/plan'

export interface ExplanationAiAvailability {
  llmApiKeySet: boolean
  polishEnabled: boolean
  polishAvailable: boolean
}

const MAX_EXPLANATION_MEMORY_CACHE_SIZE = 12
const explanationMemoryCache = new Map<string, ExplanationResponse>()

function rememberExplanation(cacheKey: string, data: ExplanationResponse) {
  if (!cacheKey) return
  explanationMemoryCache.delete(cacheKey)
  explanationMemoryCache.set(cacheKey, data)
  while (explanationMemoryCache.size > MAX_EXPLANATION_MEMORY_CACHE_SIZE) {
    const oldestKey = explanationMemoryCache.keys().next().value
    if (!oldestKey) break
    explanationMemoryCache.delete(oldestKey)
  }
}

function buildExplanationCacheKey(
  projectId: string | undefined,
  scopeId: string | undefined,
  polish: boolean,
) {
  if (!projectId || !scopeId) return ''
  return `${projectId}:${scopeId}:${polish ? 'polished' : 'rule'}`
}

function shouldRememberExplanation(data: ExplanationResponse, polish: boolean) {
  return !polish || data.meta?.polish?.applied === true
}

function isCanceledRequest(error: unknown) {
  if (!error || typeof error !== 'object') {
    return false
  }
  const maybeError = error as { code?: string; name?: string }
  return maybeError.code === 'ERR_CANCELED' || maybeError.name === 'CanceledError' || maybeError.name === 'AbortError'
}

function isTimeoutRequest(error: unknown) {
  if (!error || typeof error !== 'object') {
    return false
  }
  const maybeError = error as { code?: string; message?: string }
  const message = maybeError.message?.toLowerCase() || ''
  return maybeError.code === 'ECONNABORTED' || message.includes('timeout') || message.includes('exceeded')
}

function explanationLoadErrorMessage(error: any, polish: boolean, hasExplanation: boolean) {
  const backendMessage = error?.response?.data?.error || error?.response?.data?.detail
  if (backendMessage) {
    return backendMessage
  }
  if (isTimeoutRequest(error)) {
    if (!polish) {
      return '规划解释加载超时，请稍后重试。'
    }
    return hasExplanation
      ? 'AI 润色超时，已保留当前可用的规则解释；可关闭 AI 润色后重试。'
      : 'AI 润色超时，请关闭 AI 润色后先加载规则解释。'
  }
  return '加载解释失败'
}

export function useExplanationState(projectId: Ref<string | undefined>, scopeId?: Ref<string | undefined>) {
  const explanation = ref<ExplanationResponse | null>(null)
  const polishRequested = ref(false)
  const loading = ref(false)
  const error = ref('')
  const askResponse = ref<ExplanationAskResponse | null>(null)
  const askLoading = ref(false)
  const askError = ref('')
  const requestId = ref(0)
  const askRequestId = ref(0)
  const controller = ref<AbortController | null>(null)

  function abortCurrentRequest() {
    controller.value?.abort()
    controller.value = null
  }

  function clearAskState() {
    askRequestId.value += 1
    askResponse.value = null
    askLoading.value = false
    askError.value = ''
  }

  function clear() {
    requestId.value += 1
    abortCurrentRequest()
    explanation.value = null
    polishRequested.value = false
    loading.value = false
    error.value = ''
    clearAskState()
  }

  async function load(polish = polishRequested.value) {
    polishRequested.value = polish
    clearAskState()

    if (!projectId.value) {
      clear()
      return
    }

    const cacheKey = buildExplanationCacheKey(projectId.value, scopeId?.value, polish)
    const cached = cacheKey ? explanationMemoryCache.get(cacheKey) : null
    if (cached) {
      explanation.value = cached
      error.value = ''
    }

    const nextRequestId = requestId.value + 1
    requestId.value = nextRequestId
    abortCurrentRequest()

    const nextController = typeof AbortController !== 'undefined' ? new AbortController() : null
    controller.value = nextController
    loading.value = true
    error.value = ''

    try {
      const data = await planApi.getExplanation(projectId.value, polish, nextController?.signal)
      if (requestId.value !== nextRequestId) {
        return
      }
      explanation.value = data
      if (cacheKey && shouldRememberExplanation(data, polish)) {
        rememberExplanation(cacheKey, data)
      }
    } catch (e: any) {
      if (requestId.value !== nextRequestId || isCanceledRequest(e)) {
        return
      }
      if (e?.response?.status === 404) {
        explanation.value = null
        return
      }
      error.value = explanationLoadErrorMessage(e, polish, Boolean(explanation.value))
    } finally {
      if (requestId.value === nextRequestId) {
        loading.value = false
        if (controller.value === nextController) {
          controller.value = null
        }
      }
    }
  }

  async function ask(payload: ExplanationAskRequest) {
    if (!projectId.value) {
      askResponse.value = null
      askError.value = '请先选择项目'
      return
    }

    const nextRequestId = askRequestId.value + 1
    askRequestId.value = nextRequestId
    askLoading.value = true
    askError.value = ''

    try {
      const data = await planApi.askExplanation(projectId.value, payload)
      if (askRequestId.value !== nextRequestId) {
        return
      }
      askResponse.value = data
    } catch (e: any) {
      if (askRequestId.value !== nextRequestId) {
        return
      }
      askError.value = e?.response?.data?.error || e?.response?.data?.detail || 'AI 辅助解释失败'
    } finally {
      if (askRequestId.value === nextRequestId) {
        askLoading.value = false
      }
    }
  }

  onBeforeUnmount(() => {
    abortCurrentRequest()
  })

  return {
    explanation,
    polishRequested,
    loading,
    error,
    askResponse,
    askLoading,
    askError,
    load,
    ask,
    clear,
  }
}
