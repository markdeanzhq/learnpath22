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

function isCanceledRequest(error: unknown) {
  if (!error || typeof error !== 'object') {
    return false
  }
  const maybeError = error as { code?: string; name?: string }
  return maybeError.code === 'ERR_CANCELED' || maybeError.name === 'CanceledError' || maybeError.name === 'AbortError'
}

export function useExplanationState(projectId: Ref<string | undefined>) {
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
    } catch (e: any) {
      if (requestId.value !== nextRequestId || isCanceledRequest(e)) {
        return
      }
      if (e?.response?.status === 404) {
        explanation.value = null
        return
      }
      error.value = e?.response?.data?.error || '加载解释失败'
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
