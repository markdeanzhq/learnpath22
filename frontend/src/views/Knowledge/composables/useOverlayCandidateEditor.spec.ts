import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useOverlayCandidateEditor } from './useOverlayCandidateEditor'
import type { OverlaySessionView } from './useOverlayCandidateWorkflow'

const {
  updateOverlayNodeCandidateMock,
  updateOverlayEdgeCandidateMock,
  updateOverlayResourceCandidateMock,
} = vi.hoisted(() => ({
  updateOverlayNodeCandidateMock: vi.fn(),
  updateOverlayEdgeCandidateMock: vi.fn(),
  updateOverlayResourceCandidateMock: vi.fn(),
}))

vi.mock('@/api/modules/graph', () => ({
  graphApi: {
    updateOverlayNodeCandidate: updateOverlayNodeCandidateMock,
    updateOverlayEdgeCandidate: updateOverlayEdgeCandidateMock,
    updateOverlayResourceCandidate: updateOverlayResourceCandidateMock,
  },
}))

function createEditor() {
  const projectId = ref<string | undefined>('project-001')
  const lastOverlaySession = ref<OverlaySessionView | null>(null)
  const overlayError = ref('')
  const refreshAfterSave = vi.fn().mockResolvedValue(undefined)
  const notifySuccess = vi.fn()
  const editor = useOverlayCandidateEditor({
    projectId,
    lastOverlaySession,
    overlayError,
    refreshAfterSave,
    getErrorMessage: () => '保存失败',
    notifySuccess,
  })
  return { projectId, lastOverlaySession, overlayError, refreshAfterSave, notifySuccess, editor }
}

describe('useOverlayCandidateEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('opens node candidates and applies validation quick fixes', () => {
    const { editor } = createEditor()

    editor.openNodeCandidateEditor({
      node_id: 'po:node-001',
      name: '扩展节点',
      summary: '',
      difficulty_final: 7,
      req_coding: 9,
      theory_weight: 1.4,
      practice_weight: -0.2,
      validation_status: 'invalid',
      validation_errors: ['missing_summary', 'invalid_req_coding', 'invalid_weight_sum'],
      review_status: 'pending',
    } as any)

    expect(editor.candidateEditor.value.title).toBe('编辑节点候选：扩展节点')
    expect(editor.candidateEditorIssueSummary.value).toContain('缺少摘要')
    expect(editor.candidateEditorFieldIssue('req_coding')).toContain('编程基础要求必须是 1~5 的整数')
    expect(editor.candidateEditorQuickFixErrors.value).toEqual(['missing_summary', 'invalid_req_coding', 'invalid_weight_sum'])
    expect(editor.quickFixLabel('missing_fields:difficulty_final,req_ml')).toBe('补齐规划字段')

    editor.applyCandidateQuickFix('missing_summary')
    editor.applyCandidateQuickFix('invalid_req_coding')
    editor.applyCandidateQuickFix('invalid_weight_sum')

    expect(editor.candidateEditor.value.form.summary).toContain('扩展节点')
    expect(editor.candidateEditor.value.form.req_coding).toBe(5)
    expect(editor.candidateEditor.value.form.theory_weight).toBe(0.6)
    expect(editor.candidateEditor.value.form.practice_weight).toBe(0.4)
  })

  it('saves node candidate patches and refreshes derived overlay state', async () => {
    const repairedSession = { session: { session_id: 'sess-001' }, nodes: [], edges: [], resources: [] } as unknown as OverlaySessionView
    updateOverlayNodeCandidateMock.mockResolvedValue(repairedSession)
    const { editor, lastOverlaySession, overlayError, refreshAfterSave, notifySuccess } = createEditor()

    editor.openNodeCandidateEditor({
      node_id: 'po:node-001',
      name: '  扩展节点  ',
      validation_status: 'invalid',
      validation_errors: [],
      review_status: 'pending',
    } as any)
    editor.candidateEditor.value.form.summary = '  新摘要  '
    editor.candidateEditor.value.form.group = ''

    await editor.saveCandidateEditor()

    expect(updateOverlayNodeCandidateMock).toHaveBeenCalledWith('project-001', 'po:node-001', expect.objectContaining({
      summary: '新摘要',
      group: null,
    }))
    expect(lastOverlaySession.value).toEqual(repairedSession)
    expect(editor.candidateEditor.value.visible).toBe(false)
    expect(refreshAfterSave).toHaveBeenCalled()
    expect(notifySuccess).toHaveBeenCalledWith('候选已保存并重新校验')
    expect(overlayError.value).toBe('')
  })

  it('routes edge and resource saves to their candidate endpoints', async () => {
    const { editor } = createEditor()
    updateOverlayEdgeCandidateMock.mockResolvedValue({ session: { session_id: 'sess-edge' }, nodes: [], edges: [], resources: [] })
    updateOverlayResourceCandidateMock.mockResolvedValue({ session: { session_id: 'sess-resource' }, nodes: [], edges: [], resources: [] })

    editor.openEdgeCandidateEditor({
      edge_id: 'po:edge-001',
      source_name_or_id: '来源',
      target_name_or_id: '目标',
      relation_type: 'BAD',
      validation_errors: ['invalid_relation_type'],
    } as any)
    editor.applyCandidateQuickFix('invalid_relation_type')
    await editor.saveCandidateEditor()

    expect(updateOverlayEdgeCandidateMock).toHaveBeenCalledWith('project-001', 'po:edge-001', expect.objectContaining({
      relation_type: 'RELATED_TO',
    }))

    editor.openResourceCandidateEditor({
      resource_id: 'po:resource-001',
      title: '资料',
      source_ids: ['src-001'],
      validation_errors: ['missing_resource_type'],
    } as any)
    editor.candidateEditor.value.form.resource_type = ''
    editor.applyCandidateQuickFix('missing_resource_type')
    await editor.saveCandidateEditor()

    expect(updateOverlayResourceCandidateMock).toHaveBeenCalledWith('project-001', 'po:resource-001', expect.objectContaining({
      resource_type: 'article',
      evidence_source_id: 'src-001',
    }))
  })

  it('maps save failures into overlay error state', async () => {
    updateOverlayNodeCandidateMock.mockRejectedValue(new Error('boom'))
    const { editor, overlayError, notifySuccess } = createEditor()

    editor.openNodeCandidateEditor({ node_id: 'po:node-001', validation_errors: [] } as any)
    await editor.saveCandidateEditor()

    expect(overlayError.value).toBe('保存失败')
    expect(editor.candidateEditor.value.saving).toBe(false)
    expect(notifySuccess).not.toHaveBeenCalled()
  })
})
