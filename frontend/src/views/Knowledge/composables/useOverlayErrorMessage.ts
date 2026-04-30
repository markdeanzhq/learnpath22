import { formatServiceReason } from '@/utils/displayLabels'

const SEARCH_NOT_READY = 'SEARCH_NOT_READY'
const SEARCH_NOT_READY_MESSAGE = '搜索服务尚未就绪，自定义扩展暂不可用；领域基线图谱浏览不受影响。'
const DEFAULT_OVERLAY_ERROR_MESSAGE = '扩展草稿创建失败'

type OverlayServiceError = {
  response?: {
    data?: {
      error?: unknown
    }
  }
  message?: unknown
}

export function getOverlayErrorMessage(error: unknown) {
  const serviceError = error as OverlayServiceError | undefined
  const code = serviceError?.response?.data?.error
  const errorCode = typeof code === 'string' ? code : ''
  const message = typeof serviceError?.message === 'string' ? serviceError.message : ''

  if (errorCode === SEARCH_NOT_READY) {
    return SEARCH_NOT_READY_MESSAGE
  }

  return formatServiceReason(errorCode) || errorCode || message || DEFAULT_OVERLAY_ERROR_MESSAGE
}
