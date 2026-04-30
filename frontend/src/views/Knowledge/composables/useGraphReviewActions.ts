import { type Ref } from 'vue'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import {
  graphApi,
  type GraphEdgeData,
  type GraphElement,
  type GraphNodeData,
  type OverlayElementGroup,
  type OverlayReviewStatus,
  type ReviewStatus,
} from '@/api/modules/graph'

type UseGraphReviewActionsOptions = {
  projectId: Readonly<Ref<string | undefined>>
  nodes: Readonly<Ref<GraphNodeData[]>>
  edges: Readonly<Ref<GraphEdgeData[]>>
  elements: Ref<GraphElement[]>
  selectedNodeId: Ref<string | null>
  refreshOverlayPreflight: () => Promise<void>
  setCanvasNodeReviewStatus: (nodeId: string, status: string) => void
  setCanvasEdgeReviewStatus: (edgeId: string, status: string) => void
  notifySuccess: (message: string) => void
  notifyError: (message: string) => void
}

export function useGraphReviewActions({
  projectId,
  nodes,
  edges,
  elements,
  selectedNodeId,
  refreshOverlayPreflight,
  setCanvasNodeReviewStatus,
  setCanvasEdgeReviewStatus,
  notifySuccess,
  notifyError,
}: UseGraphReviewActionsOptions) {
  function getElementGroup(data: GraphNodeData | GraphEdgeData): OverlayElementGroup {
    return 'source' in data && 'target' in data ? 'edges' : 'nodes'
  }

  function normalizeOverlayReviewStatus(status: string): OverlayReviewStatus {
    return status === 'rejected' ? 'rejected' : status as OverlayReviewStatus
  }

  function overlayElementLabel(group: OverlayElementGroup): string {
    return group === 'nodes' ? '节点' : '关系'
  }

  async function confirmOverlayReview(group: OverlayElementGroup, status: OverlayReviewStatus): Promise<boolean> {
    if (status !== 'confirmed') {
      return true
    }

    try {
      await ElMessageBox.confirm(
        `确认该扩展${overlayElementLabel(group)}有效后，它会进入“已确认候选”；是否参与增强图谱规划仍由规划开关控制。`,
        '确认扩展候选有效',
        {
          type: 'warning',
          confirmButtonText: '确认有效',
          cancelButtonText: '取消',
        },
      )
      return true
    } catch (error) {
      if (isMessageBoxCancel(error)) {
        return false
      }
      throw error
    }
  }

  async function confirmOverlayPlanning(data: GraphNodeData | GraphEdgeData, enabled: boolean): Promise<boolean> {
    if (!enabled) {
      return true
    }

    const label = data.label ? `「${data.label}」` : '该扩展候选'
    try {
      await ElMessageBox.confirm(
        `${label}开启规划后会进入增强图谱预检和路径对比，但不会直接保存为正式学习路径。`,
        '纳入增强图谱规划',
        {
          type: 'warning',
          confirmButtonText: '纳入规划',
          cancelButtonText: '取消',
        },
      )
      return true
    } catch (error) {
      if (isMessageBoxCancel(error)) {
        return false
      }
      throw error
    }
  }

  function patchElementLifecycle(
    elementId: string,
    lifecycle: {
      review_status?: string
      planning_enabled?: boolean
      validation_status?: string
      promotion_status?: string
    },
  ) {
    elements.value = elements.value.map((element) => {
      if (element.data.id !== elementId) {
        return element
      }

      return {
        ...element,
        data: {
          ...element.data,
          ...lifecycle,
        },
      } as GraphElement
    })
  }

  function updateNodeReviewStatus(nodeId: string, status: ReviewStatus) {
    elements.value = elements.value.map((element) => {
      if (element.group !== 'nodes' || element.data.id !== nodeId) {
        return element
      }

      return {
        ...element,
        data: {
          ...element.data,
          review_status: status,
        },
      }
    })
  }

  function updateEdgeReviewStatus(edgeId: string, status: ReviewStatus) {
    elements.value = elements.value.map((element) => {
      if (element.group !== 'edges' || element.data.id !== edgeId) {
        return element
      }

      return {
        ...element,
        data: {
          ...element.data,
          review_status: status,
        },
      }
    })
  }

  async function onReviewNode(nodeId: string, status: string) {
    if (!projectId.value) return
    const node = nodes.value.find((item) => item.id === nodeId)
    try {
      if (node?.origin === 'overlay') {
        const nextStatus = normalizeOverlayReviewStatus(status)
        if (!(await confirmOverlayReview('nodes', nextStatus))) {
          return
        }
        const result = await graphApi.reviewOverlayElement(
          projectId.value,
          'nodes',
          nodeId,
          nextStatus,
        )
        selectedNodeId.value = nodeId
        patchElementLifecycle(nodeId, result)
        setCanvasNodeReviewStatus(nodeId, result.review_status)
        await refreshOverlayPreflight()
      } else {
        const nextStatus = status as ReviewStatus
        await graphApi.reviewNode(projectId.value, nodeId, nextStatus)
        selectedNodeId.value = nodeId
        updateNodeReviewStatus(nodeId, nextStatus)
        setCanvasNodeReviewStatus(nodeId, nextStatus)
      }
      notifySuccess('节点审核状态已更新')
    } catch (e: any) {
      notifyError(e?.response?.data?.error || '节点审核失败')
    }
  }

  async function onReviewEdge(edgeId: string, status: string) {
    if (!projectId.value) return
    const edge = edges.value.find((item) => item.id === edgeId)
    try {
      if (edge?.origin === 'overlay') {
        const nextStatus = normalizeOverlayReviewStatus(status)
        if (!(await confirmOverlayReview('edges', nextStatus))) {
          return
        }
        const result = await graphApi.reviewOverlayElement(
          projectId.value,
          'edges',
          edgeId,
          nextStatus,
        )
        patchElementLifecycle(edgeId, result)
        setCanvasEdgeReviewStatus(edgeId, result.review_status)
        await refreshOverlayPreflight()
      } else {
        const nextStatus = status as ReviewStatus
        await graphApi.reviewEdge(projectId.value, edgeId, nextStatus)
        updateEdgeReviewStatus(edgeId, nextStatus)
        setCanvasEdgeReviewStatus(edgeId, nextStatus)
      }
      notifySuccess('边审核状态已更新')
    } catch (e: any) {
      notifyError(e?.response?.data?.error || '边审核失败')
    }
  }

  async function onSetOverlayPlanning(data: GraphNodeData | GraphEdgeData, enabled: boolean) {
    if (!projectId.value || data.origin !== 'overlay') return
    try {
      if (!(await confirmOverlayPlanning(data, enabled))) {
        return
      }
      const result = await graphApi.setOverlayPlanning(
        projectId.value,
        getElementGroup(data),
        data.id,
        enabled,
      )
      patchElementLifecycle(data.id, result)
      await refreshOverlayPreflight()
      notifySuccess(enabled ? '已允许参与规划' : '已从规划中排除')
    } catch (e: any) {
      notifyError(e?.response?.data?.error || '规划开关更新失败')
    }
  }

  return {
    onReviewNode,
    onReviewEdge,
    onSetOverlayPlanning,
  }
}

function isMessageBoxCancel(error: unknown): boolean {
  if (typeof error === 'string') {
    return error === 'cancel' || error === 'close'
  }
  if (error && typeof error === 'object' && 'action' in error) {
    const action = (error as { action?: unknown }).action
    return action === 'cancel' || action === 'close'
  }
  return false
}
