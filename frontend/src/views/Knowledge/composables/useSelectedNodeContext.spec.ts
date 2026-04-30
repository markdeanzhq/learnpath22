import { ref } from 'vue'
import { describe, expect, it } from 'vitest'
import { useSelectedNodeContext } from './useSelectedNodeContext'
import type { GraphEdgeData, GraphNodeData } from '@/api/modules/graph'

function createContext() {
  const nodes = ref<GraphNodeData[]>([
    { id: 'ml_c01', label: '机器学习导论' },
    { id: 'ml_c02', label: '监督学习' },
    { id: 'ml_c03', label: '线性回归' },
  ])
  const edges = ref<GraphEdgeData[]>([
    { id: 'ml_c01->ml_c02', source: 'ml_c01', target: 'ml_c02', type: 'REQUIRES' },
    { id: 'ml_c02->ml_c03', source: 'ml_c02', target: 'ml_c03', type: 'REQUIRES' },
    { id: 'ml_c01->ml_c03', source: 'ml_c01', target: 'ml_c03', type: 'RELATED_TO' },
  ])
  const selectedNodeId = ref<string | null>(null)
  const context = useSelectedNodeContext({ nodes, edges, selectedNodeId })
  return { nodes, edges, selectedNodeId, context }
}

describe('useSelectedNodeContext', () => {
  it('returns null when no node is selected', () => {
    const { context } = createContext()

    expect(context.selectedNode.value).toBeNull()
  })

  it('returns null when selected node no longer exists', () => {
    const { selectedNodeId, context } = createContext()

    selectedNodeId.value = 'missing-node'

    expect(context.selectedNode.value).toBeNull()
  })

  it('builds incoming, outgoing and adjacent edge context', () => {
    const { selectedNodeId, context } = createContext()

    selectedNodeId.value = 'ml_c02'

    expect(context.selectedNode.value?.id).toBe('ml_c02')
    expect(context.selectedNode.value?.adjacent_edges.map((edge) => edge.id)).toEqual([
      'ml_c01->ml_c02',
      'ml_c02->ml_c03',
    ])
    expect(context.selectedNode.value?.incoming_edges).toMatchObject([
      {
        id: 'ml_c01->ml_c02',
        direction: 'incoming',
        source_label: '机器学习导论',
        target_label: '监督学习',
      },
    ])
    expect(context.selectedNode.value?.outgoing_edges).toMatchObject([
      {
        id: 'ml_c02->ml_c03',
        direction: 'outgoing',
        source_label: '监督学习',
        target_label: '线性回归',
      },
    ])
  })

  it('updates when graph edges change', () => {
    const { selectedNodeId, edges, context } = createContext()
    selectedNodeId.value = 'ml_c02'

    edges.value = []

    expect(context.selectedNode.value?.adjacent_edges).toEqual([])
    expect(context.selectedNode.value?.incoming_edges).toEqual([])
    expect(context.selectedNode.value?.outgoing_edges).toEqual([])
  })
})
