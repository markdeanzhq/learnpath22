import { describe, expect, it } from 'vitest'
import { getOverlayErrorMessage } from './useOverlayErrorMessage'

describe('getOverlayErrorMessage', () => {
  it('returns the contextual search readiness message', () => {
    const message = getOverlayErrorMessage({ response: { data: { error: 'SEARCH_NOT_READY' } } })

    expect(message).toBe('搜索服务尚未就绪，自定义扩展暂不可用；领域基线图谱浏览不受影响。')
  })

  it('formats known service reasons', () => {
    const message = getOverlayErrorMessage({ response: { data: { error: 'projection_missing' } } })

    expect(message).toBe('已有扩展草稿，但尚未同步为 Neo4j 投影；普通浏览和路径预检不受影响，需要显式同步时再点击同步图谱')
  })

  it('falls back to raw code, error message and default message', () => {
    expect(getOverlayErrorMessage({ response: { data: { error: 'UNKNOWN_CODE' } } })).toBe('UNKNOWN_CODE')
    expect(getOverlayErrorMessage({ message: 'network down' })).toBe('network down')
    expect(getOverlayErrorMessage({})).toBe('扩展草稿创建失败')
  })
})
