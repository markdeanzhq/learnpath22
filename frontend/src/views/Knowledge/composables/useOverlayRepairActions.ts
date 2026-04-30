import type { Ref } from 'vue'
import type { OverlayRepairTarget } from './useOverlayCandidateWorkflow'

type NodeRepairTarget = Extract<OverlayRepairTarget, { kind: 'node' }>
type EdgeRepairTarget = Extract<OverlayRepairTarget, { kind: 'edge' }>
type ResourceRepairTarget = Extract<OverlayRepairTarget, { kind: 'resource' }>

type UseOverlayRepairActionsOptions = {
  overlayCandidateRepairTarget: Readonly<Ref<OverlayRepairTarget | null>>
  openNodeCandidateEditor: (candidate: NodeRepairTarget['candidate']) => void
  openEdgeCandidateEditor: (candidate: EdgeRepairTarget['candidate']) => void
  openResourceCandidateEditor: (candidate: ResourceRepairTarget['candidate']) => void
}

export function useOverlayRepairActions({
  overlayCandidateRepairTarget,
  openNodeCandidateEditor,
  openEdgeCandidateEditor,
  openResourceCandidateEditor,
}: UseOverlayRepairActionsOptions) {
  function openOverlayRepairTarget(target: OverlayRepairTarget) {
    if (target.kind === 'node') {
      openNodeCandidateEditor(target.candidate)
    } else if (target.kind === 'edge') {
      openEdgeCandidateEditor(target.candidate)
    } else {
      openResourceCandidateEditor(target.candidate)
    }
  }

  function openFirstRepairableCandidate() {
    const target = overlayCandidateRepairTarget.value
    if (target) openOverlayRepairTarget(target)
  }

  return {
    openOverlayRepairTarget,
    openFirstRepairableCandidate,
  }
}
