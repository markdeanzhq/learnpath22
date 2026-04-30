import { computed, type Ref } from 'vue'
import type { GraphEdgeData, GraphNodeData } from '@/api/modules/graph'

export type SelectedAdjacentEdge = GraphEdgeData & {
  direction: 'incoming' | 'outgoing'
  source_label?: string
  target_label?: string
}

export type SelectedNodeContext = GraphNodeData & {
  adjacent_edges: SelectedAdjacentEdge[]
  incoming_edges: SelectedAdjacentEdge[]
  outgoing_edges: SelectedAdjacentEdge[]
}

type UseSelectedNodeContextOptions = {
  nodes: Readonly<Ref<GraphNodeData[]>>
  edges: Readonly<Ref<GraphEdgeData[]>>
  selectedNodeId: Readonly<Ref<string | null>>
}

export function useSelectedNodeContext({
  nodes,
  edges,
  selectedNodeId,
}: UseSelectedNodeContextOptions) {
  const selectedNode = computed<SelectedNodeContext | null>(() => {
    const nodeId = selectedNodeId.value
    if (!nodeId) return null

    const node = nodes.value.find((item) => item.id === nodeId)
    if (!node) return null

    const nodeLabelMap = new Map(nodes.value.map((item) => [item.id, item.label]))
    const adjacentEdges = edges.value
      .filter((edge) => edge.source === nodeId || edge.target === nodeId)
      .map<SelectedAdjacentEdge>((edge) => ({
        ...edge,
        direction: edge.source === nodeId ? 'outgoing' : 'incoming',
        source_label: nodeLabelMap.get(edge.source),
        target_label: nodeLabelMap.get(edge.target),
      }))

    return {
      ...node,
      adjacent_edges: adjacentEdges,
      incoming_edges: adjacentEdges.filter((edge) => edge.direction === 'incoming'),
      outgoing_edges: adjacentEdges.filter((edge) => edge.direction === 'outgoing'),
    }
  })

  return {
    selectedNode,
  }
}
