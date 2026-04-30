import { describe, expect, it } from 'vitest'
import {
  auditSourceLabel,
  formatErrorCode,
  promotionPreviewStatusMeta,
  promotionStatusMeta,
  resolveSourceMeta,
  sessionStatusMeta,
} from './displayLabels'

describe('displayLabels', () => {
  it('maps public-facing enum labels and keeps raw values as details for unknown states', () => {
    expect(resolveSourceMeta('template').label).toBe('目标模板')
    expect(promotionStatusMeta('promotion_failed').label).toBe('推广失败')
    expect(promotionPreviewStatusMeta('ready').label).toBe('预览通过')
    expect(sessionStatusMeta('drafted').label).toBe('草稿已生成')

    expect(sessionStatusMeta('legacy_state')).toEqual({
      label: '未识别抽取状态',
      tagType: 'warning',
      detail: 'legacy_state',
    })
  })

  it('maps audit sources and backend error codes to readable Chinese labels', () => {
    expect(auditSourceLabel('audit.ordering_logs').label).toBe('排序审计记录')
    expect(formatErrorCode('EMPTY_CANDIDATES')).toBe('未找到可确认的目标候选')
    expect(formatErrorCode('negative_patterns_excluded_all')).toBe('目标文本被排除规则过滤')
    expect(formatErrorCode('INVALID_LLM_EXTRACTION_JSON')).toContain('重新生成预览')
    expect(formatErrorCode('LLM_NOT_READY')).toBe('LLM 尚未配置，无法生成扩展抽取预览')
    expect(formatErrorCode('UNKNOWN_CODE')).toBe('UNKNOWN_CODE')
  })

  it('maps optional enhancement and projection reason codes without exposing raw backend terms', () => {
    expect(formatErrorCode('projection_missing')).toContain('普通浏览和路径预检不受影响')
    expect(formatErrorCode('overlay_projection_drifted')).toContain('等待重新同步')
    expect(formatErrorCode('source_context_sparse')).toContain('资料内容较少')
    expect(formatErrorCode('neo4j_unavailable')).toContain('本地图谱浏览不受影响')
  })
})
