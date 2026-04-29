import axios from 'axios'
import { ElMessage } from 'element-plus/es/components/message/index'
import type { AxiosRequestConfig } from 'axios'
import { formatErrorCode } from '@/utils/displayLabels'

export interface RequestConfig extends AxiosRequestConfig {
  silent?: boolean
}

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

function isCanceledRequest(error: unknown) {
  if (!error || typeof error !== 'object') {
    return false
  }
  const maybeError = error as { code?: string; name?: string; message?: string }
  return maybeError.code === 'ERR_CANCELED'
    || maybeError.name === 'CanceledError'
    || maybeError.name === 'AbortError'
    || maybeError.message === 'canceled'
}

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (isCanceledRequest(error)) {
      return Promise.reject(error)
    }

    const data = error.response?.data
    const errorCode = typeof data?.error === 'string' ? data.error : ''
    const detailMessage = typeof data?.detail === 'string' ? data.detail : ''
    const reasonText = typeof data?.reason_text === 'string' ? data.reason_text : ''
    const reasonCode = typeof data?.reason_code === 'string' ? data.reason_code : ''
    const reasonFallback = typeof data?.reason === 'string' ? data.reason : ''
    const resolvedReason = reasonText || reasonFallback
    const displayError = formatErrorCode(errorCode)
    const displayReasonCode = formatErrorCode(reasonCode)
    const message = resolvedReason
      ? `${displayError ? `${displayError}：` : ''}${resolvedReason}${displayReasonCode ? `（追溯：${displayReasonCode}）` : ''}`
      : displayError || detailMessage || error.message || '请求失败'
    const silent = Boolean((error.config as RequestConfig | undefined)?.silent)

    if (!silent) {
      ElMessage.error(message)
    }

    return Promise.reject(error)
  },
)

export default request
