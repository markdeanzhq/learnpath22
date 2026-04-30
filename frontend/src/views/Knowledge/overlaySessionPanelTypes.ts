import type {
  CandidateIssueFilter,
  OverlayCandidateDiagnosticItem,
  OverlayCandidateDiagnosticSummary,
} from './composables/useOverlayCandidateWorkflow'

export type { OverlayCandidateDiagnosticItem, OverlayCandidateDiagnosticSummary }

export type OverlaySessionStats = {
  invalid: number
  needsReview: number
  valid: number
  pendingReview: number
}

export type OverlayCandidateFilterOption = {
  value: CandidateIssueFilter
  label: string
}

export type OverlayCandidateFilterCounts = Record<CandidateIssueFilter, number>

export type ResourceTargetOption = {
  id: string
  label: string
}
