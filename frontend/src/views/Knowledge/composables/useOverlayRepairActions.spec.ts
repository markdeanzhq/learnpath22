import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useOverlayRepairActions } from './useOverlayRepairActions'
import type { OverlayRepairTarget } from './useOverlayCandidateWorkflow'

function createActions(initialTarget: OverlayRepairTarget | null = null) {
  const overlayCandidateRepairTarget = ref<OverlayRepairTarget | null>(initialTarget)
  const openNodeCandidateEditor = vi.fn()
  const openEdgeCandidateEditor = vi.fn()
  const openResourceCandidateEditor = vi.fn()
  const actions = useOverlayRepairActions({
    overlayCandidateRepairTarget,
    openNodeCandidateEditor,
    openEdgeCandidateEditor,
    openResourceCandidateEditor,
  })
  return {
    overlayCandidateRepairTarget,
    openNodeCandidateEditor,
    openEdgeCandidateEditor,
    openResourceCandidateEditor,
    actions,
  }
}

const nodeTarget = { kind: 'node', candidate: { node_id: 'n1', label: '节点候选' } } as unknown as OverlayRepairTarget
const edgeTarget = { kind: 'edge', candidate: { source_id: 'n1', target_id: 'n2', relation_type: 'REQUIRES' } } as unknown as OverlayRepairTarget
const resourceTarget = { kind: 'resource', candidate: { target_id: 'n1', title: '资料候选' } } as unknown as OverlayRepairTarget

describe('useOverlayRepairActions', () => {
  it('dispatches repair target to the matching candidate editor', () => {
    const { actions, openNodeCandidateEditor, openEdgeCandidateEditor, openResourceCandidateEditor } = createActions()

    actions.openOverlayRepairTarget(nodeTarget)
    actions.openOverlayRepairTarget(edgeTarget)
    actions.openOverlayRepairTarget(resourceTarget)

    expect(openNodeCandidateEditor).toHaveBeenCalledWith(nodeTarget.candidate)
    expect(openEdgeCandidateEditor).toHaveBeenCalledWith(edgeTarget.candidate)
    expect(openResourceCandidateEditor).toHaveBeenCalledWith(resourceTarget.candidate)
  })

  it('opens the first repairable candidate when one exists', () => {
    const { actions, openNodeCandidateEditor } = createActions(nodeTarget)

    actions.openFirstRepairableCandidate()

    expect(openNodeCandidateEditor).toHaveBeenCalledWith(nodeTarget.candidate)
  })

  it('does nothing when there is no repairable candidate', () => {
    const { actions, openNodeCandidateEditor, openEdgeCandidateEditor, openResourceCandidateEditor } = createActions()

    actions.openFirstRepairableCandidate()

    expect(openNodeCandidateEditor).not.toHaveBeenCalled()
    expect(openEdgeCandidateEditor).not.toHaveBeenCalled()
    expect(openResourceCandidateEditor).not.toHaveBeenCalled()
  })
})
