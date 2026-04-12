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
    const message = data?.error || data?.detail || error.message || '请求失败'
    const silent = Boolean((error.config as RequestConfig | undefined)?.silent)

    if (!silent) {
      ElMessage.error(message)
    }

    return Promise.reject(error)
  },
)

export default request
