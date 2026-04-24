import axios from 'axios'
import { ElMessage } from 'element-plus'
import type { AxiosRequestConfig } from 'axios'

export interface RequestConfig extends AxiosRequestConfig {
  silent?: boolean
}

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

request.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const data = error.response?.data
    const errorCode = typeof data?.error === 'string' ? data.error : ''
    const detailMessage = typeof data?.detail === 'string' ? data.detail : ''
    const reasonText = typeof data?.reason_text === 'string' ? data.reason_text : ''
    const reasonCode = typeof data?.reason_code === 'string' ? data.reason_code : ''
    const reasonFallback = typeof data?.reason === 'string' ? data.reason : ''
    const resolvedReason = reasonText || reasonFallback
    const message = resolvedReason
      ? `${errorCode ? `${errorCode}：` : ''}${resolvedReason}${reasonCode ? `（${reasonCode}）` : ''}`
      : errorCode || detailMessage || error.message || '请求失败'
    const silent = Boolean((error.config as RequestConfig | undefined)?.silent)

    if (!silent) {
      ElMessage.error(message)
    }

    return Promise.reject(error)
  },
)

export default request
