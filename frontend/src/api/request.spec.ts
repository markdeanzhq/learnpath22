import { beforeEach, describe, expect, it, vi } from 'vitest'

const errorMock = vi.fn()
const successHandlerRef: { current: ((value: unknown) => unknown) | null } = { current: null }
const errorHandlerRef: { current: ((error: any) => Promise<never>) | null } = { current: null }

const requestInstance = {
  interceptors: {
    response: {
      use: vi.fn((onSuccess, onError) => {
        successHandlerRef.current = onSuccess
        errorHandlerRef.current = onError
      }),
    },
  },
}

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => requestInstance),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    error: errorMock,
  },
}))

describe('request interceptor', () => {
  beforeEach(async () => {
    vi.resetModules()
    errorMock.mockReset()
    successHandlerRef.current = null
    errorHandlerRef.current = null
    await import('./request')
  })

  it('prefers reason_text and keeps backend error code visible', async () => {
    await expect(
      errorHandlerRef.current?.({
        response: {
          data: {
            error: 'EMPTY_CANDIDATES',
            reason_code: 'negative_patterns_excluded_all',
            reason_text: '目标文本命中了排除词，请改写描述后重试',
          },
        },
        config: {},
        message: 'Request failed',
      }),
    ).rejects.toBeTruthy()

    expect(errorMock).toHaveBeenCalledWith('未找到可确认的目标候选：目标文本命中了排除词，请改写描述后重试（追溯：目标文本被排除规则过滤）')
  })

  it('falls back to backend reason when reason_text is absent', async () => {
    await expect(
      errorHandlerRef.current?.({
        response: {
          data: {
            error: 'GOAL_DEFAULT_TARGETS_UNAVAILABLE',
            reason: 'No effective target nodes available for goal_type=domain after applying pack default policy',
          },
        },
        config: {},
        message: 'Request failed',
      }),
    ).rejects.toBeTruthy()

    expect(errorMock).toHaveBeenCalledWith('默认目标节点不可用：No effective target nodes available for goal_type=domain after applying pack default policy')
  })

  it('falls back to backend error when neither reason_text nor reason is present', async () => {
    await expect(
      errorHandlerRef.current?.({
        response: {
          data: {
            error: 'INVALID_DOMAIN',
          },
        },
        config: {},
        message: 'Request failed',
      }),
    ).rejects.toBeTruthy()

    expect(errorMock).toHaveBeenCalledWith('当前仅支持默认机器学习领域')
  })

  it('does not show canceled request errors', async () => {
    const canceled = { code: 'ERR_CANCELED', name: 'CanceledError', message: 'canceled' }

    await expect(errorHandlerRef.current?.(canceled)).rejects.toBe(canceled)

    expect(errorMock).not.toHaveBeenCalled()
  })
})
