<template>
  <div ref="containerRef" class="graph-canvas" @contextmenu.prevent>
    <div ref="cyContainerRef" class="graph-canvas-surface"></div>
    <ReviewContextMenu
      :visible="menuState.visible"
      :x="menuState.x"
      :y="menuState.y"
      :container-width="menuState.containerWidth"
      :container-height="menuState.containerHeight"
      :target-type="menuState.targetType"
      :target-data="menuState.targetData"
      @close="closeContextMenu"
      @review="handleMenuReview"
      @viewDetail="handleViewNodeDetail"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import ReviewContextMenu from './ReviewContextMenu.vue'
import { CATEGORY_COLORS } from './graphMeta'

const BASELINE_REVIEW_STATUSES = new Set(['pending', 'confirmed', 'removed'])
const OVERLAY_REVIEW_STATUSES = new Set(['pending', 'confirmed', 'removed', 'rejected'])
const REVIEW_ACTIONABLE_STATUSES = OVERLAY_REVIEW_STATUSES
const UNKNOWN_LIFECYCLE = 'unknown'
const PLANNING_DISABLED_CLASS = 'planning-disabled'

const props = withDefaults(defineProps<{
  elements: any[]
  layout?: 'cose' | 'breadthfirst'
  highlightNodes?: string[]
  masteredNodes?: string[]
  reviewMode?: boolean
}>(), {
  layout: 'cose',
  highlightNodes: () => [],
  masteredNodes: () => [],
  reviewMode: false,
})

const emit = defineEmits<{
  nodeClick: [data: any]
  nodeHover: [data: any]
  reviewNode: [nodeId: string, status: string]
  reviewEdge: [edgeId: string, status: string]
}>()

const containerRef = ref<HTMLDivElement>()
const cyContainerRef = ref<HTMLDivElement>()
let cy: any = null
let isMounted = false
let initRequestId = 0
let cytoscapeFactoryPromise: Promise<any> | null = null

type MenuTargetType = 'node' | 'edge'
type MenuTarget = {
  id: string
  type: MenuTargetType
}

function createClosedMenuState() {
  return {
    visible: false,
    x: 0,
    y: 0,
    containerWidth: 0,
    containerHeight: 0,
    targetType: null as MenuTargetType | null,
    targetData: null as Record<string, any> | null,
  }
}

let activeMenuElement: any = null
let activeMenuTarget: MenuTarget | null = null

const menuState = ref(createClosedMenuState())

const cytoscapeStyle: any[] = [
  {
    selector: 'node',
    style: {
      'label': 'data(label)',
      'text-valign': 'center',
      'text-halign': 'center',
      'font-size': '11px',
      'text-wrap': 'wrap',
      'text-max-width': '80px',
      'width': 'mapData(importance, 1, 5, 40, 70)',
      'height': 'mapData(importance, 1, 5, 40, 70)',
      'background-color': '#409EFF',
      'color': '#fff',
      'text-outline-color': '#333',
      'text-outline-width': 1,
      'border-width': 2,
      'border-color': '#ddd',
      'shape': 'round-rectangle',
    },
  },
  ...Object.entries(CATEGORY_COLORS).map(([cat, color]) => ({
    selector: `node[category = "${cat}"]`,
    style: { 'background-color': color },
  })),
  {
    selector: 'edge[type = "REQUIRES"]',
    style: {
      'width': 3,
      'line-color': '#aaa',
      'target-arrow-color': '#aaa',
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
      'arrow-scale': 1.2,
      'line-outline-width': 1,
      'line-outline-color': '#f2f3f5',
    },
  },
  {
    selector: 'edge[type = "RELATED_TO"]',
    style: {
      'width': 2.5,
      'line-color': '#ccc',
      'line-style': 'dashed',
      'target-arrow-shape': 'none',
      'curve-style': 'bezier',
      'line-outline-width': 1,
      'line-outline-color': '#f5f7fa',
    },
  },
  {
    selector: 'edge.review-hover',
    style: {
      'width': 4.5,
      'line-color': '#79bbff',
      'target-arrow-color': '#79bbff',
      'line-outline-width': 4,
      'line-outline-color': '#d9ecff',
      'z-index': 18,
    },
  },
  {
    selector: 'node.highlighted',
    style: {
      'border-color': '#E6A23C',
      'border-width': 4,
    },
  },
  {
    selector: 'node.mastered',
    style: {
      'background-color': '#67C23A',
      'border-color': '#4CAF50',
      'border-width': 3,
    },
  },
  {
    selector: 'node.search-match',
    style: {
      'border-color': '#F56C6C',
      'border-width': 4,
      'z-index': 10,
    },
  },
  {
    selector: 'node[review_status = "confirmed"]',
    style: {
      'border-color': '#67C23A',
      'border-width': 3,
    },
  },
  {
    selector: 'node[origin = "overlay"]',
    style: {
      'border-style': 'dashed',
      'border-color': '#E6A23C',
      'border-width': 4,
    },
  },
  {
    selector: 'node[origin = "overlay"][validation_status = "unknown"], node[origin = "overlay"][review_status = "unknown"]',
    style: {
      'border-color': '#909399',
      'border-width': 5,
    },
  },
  {
    selector: 'node.planning-disabled',
    style: {
      'opacity': 0.45,
    },
  },
  {
    selector: 'node[review_status = "removed"], node[review_status = "rejected"]',
    style: {
      'background-color': '#C0C4CC',
      'border-color': '#909399',
      'border-width': 2,
      'opacity': 0.5,
    },
  },
  {
    selector: 'edge[review_status = "confirmed"]',
    style: {
      'width': 3,
      'line-color': '#67C23A',
      'target-arrow-color': '#67C23A',
      'opacity': 1,
    },
  },
  {
    selector: 'edge[origin = "overlay"]',
    style: {
      'line-style': 'dotted',
      'line-color': '#E6A23C',
      'target-arrow-color': '#E6A23C',
    },
  },
  {
    selector: 'edge[origin = "overlay"][validation_status = "unknown"], edge[origin = "overlay"][review_status = "unknown"]',
    style: {
      'line-color': '#909399',
      'target-arrow-color': '#909399',
      'width': 4,
    },
  },
  {
    selector: 'edge.planning-disabled',
    style: {
      'opacity': 0.35,
    },
  },
  {
    selector: 'edge[review_status = "removed"], edge[review_status = "rejected"]',
    style: {
      'line-color': '#C0C4CC',
      'target-arrow-color': '#C0C4CC',
      'opacity': 0.3,
    },
  },
  {
    selector: 'node.review-menu-active',
    style: {
      'overlay-opacity': 0.12,
      'overlay-color': '#409EFF',
      'border-width': 4,
      'border-color': '#409EFF',
      'z-index': 20,
    },
  },
  {
    selector: 'edge.review-menu-active',
    style: {
      'width': 5,
      'line-color': '#409EFF',
      'target-arrow-color': '#409EFF',
      'line-outline-width': 6,
      'line-outline-color': '#d9ecff',
      'z-index': 20,
    },
  },
]

function getLayoutConfig(layoutName: string) {
  if (layoutName === 'breadthfirst') {
    return {
      name: 'breadthfirst',
      directed: true,
      spacingFactor: 1.5,
      animate: true,
      animationDuration: 500,
    }
  }
  return {
    name: 'cose',
    animate: true,
    animationDuration: 500,
    nodeOverlap: 20,
    idealEdgeLength: () => 100,
    nodeRepulsion: () => 4000,
  }
}

function getReviewStatus(status?: string) {
  return REVIEW_ACTIONABLE_STATUSES.has(status || '') ? status : UNKNOWN_LIFECYCLE
}

function getElementOrigin(data?: Record<string, any> | null) {
  return data && Object.prototype.hasOwnProperty.call(data, 'origin') ? data.origin : 'unknown'
}

function hasKnownOrigin(data?: Record<string, any> | null) {
  const origin = getElementOrigin(data)
  return origin === 'baseline' || origin === 'overlay'
}

function isKnownReviewStatusForOrigin(data?: Record<string, any> | null) {
  const origin = getElementOrigin(data)
  const status = data?.review_status
  if (origin === 'overlay') return OVERLAY_REVIEW_STATUSES.has(status)
  if (origin === 'baseline') return BASELINE_REVIEW_STATUSES.has(status)
  return false
}

function canEmitReview(data: Record<string, any> | null | undefined, status: string) {
  const origin = getElementOrigin(data)
  const statusAllowed = origin === 'overlay'
    ? OVERLAY_REVIEW_STATUSES.has(status)
    : origin === 'baseline' && BASELINE_REVIEW_STATUSES.has(status)
  return hasKnownOrigin(data) && isKnownReviewStatusForOrigin(data) && statusAllowed
}

function normalizeLifecycleValue(value: unknown) {
  if (value === undefined || value === null || value === '') {
    return UNKNOWN_LIFECYCLE
  }
  return value
}

function isPlanningDisabled(data?: Record<string, any> | null) {
  return data?.planning_enabled === false || data?.planning_enabled === 0
}

function getSingleMenuElement(target: any, targetType?: MenuTargetType | null) {
  if (!target || target === cy || typeof target.isNode !== 'function' || typeof target.isEdge !== 'function') {
    return null
  }

  const isNode = target.isNode()
  const isEdge = target.isEdge()
  if (!isNode && !isEdge) {
    return null
  }

  if (targetType === 'node' && !isNode) {
    return null
  }

  if (targetType === 'edge' && !isEdge) {
    return null
  }

  if (typeof target.first === 'function') {
    const first = target.first()
    return first?.length ? first : null
  }

  return target.length ? target : null
}

function isActiveMenuTarget(targetType: MenuTargetType, targetId?: string | null) {
  return Boolean(
    targetId
    && activeMenuTarget
    && activeMenuTarget.type === targetType
    && activeMenuTarget.id === targetId,
  )
}

function updateActiveMenuTarget(element: any, targetType: MenuTargetType) {
  clearMenuHighlight()

  if (!element?.length) {
    return
  }

  element.addClass('review-menu-active')
  activeMenuElement = element
  activeMenuTarget = {
    id: element.id(),
    type: targetType,
  }
}

function clearMenuHighlight() {
  if (activeMenuElement?.length) {
    activeMenuElement.removeClass('review-menu-active')
  }
  activeMenuElement = null
  activeMenuTarget = null
}

function closeContextMenu() {
  menuState.value = createClosedMenuState()
  clearMenuHighlight()
}

function getMenuPosition(evt: any) {
  const container = containerRef.value
  if (!container) {
    return { x: 0, y: 0, containerWidth: 0, containerHeight: 0 }
  }

  const bounds = container.getBoundingClientRect()
  const originalEvent = evt.originalEvent as MouseEvent | PointerEvent | TouchEvent | undefined
  const touchEvent = originalEvent instanceof TouchEvent ? originalEvent : null
  const pointerEvent = originalEvent && !(originalEvent instanceof TouchEvent)
    ? originalEvent as MouseEvent | PointerEvent
    : null
  const touchPoint = touchEvent?.touches[0] || touchEvent?.changedTouches[0] || null

  const clientX = touchPoint?.clientX ?? pointerEvent?.clientX
  const clientY = touchPoint?.clientY ?? pointerEvent?.clientY

  const x = typeof clientX === 'number'
    ? clientX - bounds.left
    : evt.renderedPosition?.x ?? evt.position?.x ?? 0
  const y = typeof clientY === 'number'
    ? clientY - bounds.top
    : evt.renderedPosition?.y ?? evt.position?.y ?? 0

  return {
    x,
    y,
    containerWidth: bounds.width,
    containerHeight: bounds.height,
  }
}

function openContextMenu(evt: any, targetType: MenuTargetType) {
  if (!props.reviewMode || !containerRef.value || !containerRef.value.isConnected) return

  evt.originalEvent?.preventDefault?.()

  const element = getSingleMenuElement(evt.target, targetType)
  if (!element?.length) {
    closeContextMenu()
    return
  }

  const data = { ...element.data() }
  const { x, y, containerWidth, containerHeight } = getMenuPosition(evt)

  updateActiveMenuTarget(element, targetType)

  menuState.value = {
    visible: true,
    x,
    y,
    containerWidth,
    containerHeight,
    targetType,
    targetData: {
      ...data,
      review_status: getReviewStatus(data.review_status),
    },
  }
}

function normalizeElementLifecycleData(elements: any[]) {
  return elements.map((element) => {
    const classes = new Set(String(element.classes || '').split(/\s+/).filter(Boolean))
    if (isPlanningDisabled(element.data)) {
      classes.add(PLANNING_DISABLED_CLASS)
    } else {
      classes.delete(PLANNING_DISABLED_CLASS)
    }

    return {
      ...element,
      classes: Array.from(classes).join(' '),
      data: {
        ...element.data,
        origin: getElementOrigin(element.data),
        validation_status: normalizeLifecycleValue(element.data?.validation_status),
        review_status: getReviewStatus(element.data?.review_status),
        promotion_status: normalizeLifecycleValue(element.data?.promotion_status),
      },
    }
  })
}

function loadCytoscape() {
  if (!cytoscapeFactoryPromise) {
    cytoscapeFactoryPromise = import('cytoscape').then((module) => module.default)
  }
  return cytoscapeFactoryPromise
}

function hasSameElementStructure(target: any, element: any) {
  if (element.group === 'nodes') {
    return typeof target.isNode === 'function' && target.isNode()
  }

  if (element.group !== 'edges' || typeof target.isEdge !== 'function' || !target.isEdge()) {
    return false
  }

  const currentData = target.data()
  return currentData.source === element.data.source && currentData.target === element.data.target
}

function applyElementDataUpdates(nextElements: any[]) {
  if (!cy) return false

  const currentElements = cy.elements()
  if (currentElements.length !== nextElements.length) return false

  for (const element of nextElements) {
    const elementId = element.data?.id
    if (!elementId) return false
    const target = cy.getElementById(elementId)
    if (!target.length || !hasSameElementStructure(target, element)) {
      return false
    }
  }

  cy.batch(() => {
    nextElements.forEach((element) => {
      const target = cy.getElementById(element.data.id)
      target.data(element.data)
      if (typeof target.toggleClass === 'function') {
        target.toggleClass(PLANNING_DISABLED_CLASS, isPlanningDisabled(element.data))
      }
    })
  })
  return true
}

async function initCytoscape() {
  const requestId = ++initRequestId
  if (!containerRef.value || !cyContainerRef.value || !props.elements.length) return

  const cytoscape = await loadCytoscape()
  if (
    requestId !== initRequestId
    || !isMounted
    || !containerRef.value
    || !cyContainerRef.value
    || !props.elements.length
  ) {
    return
  }

  if (cy) {
    cy.destroy()
    cy = null
  }
  closeContextMenu()

  cy = cytoscape({
    container: cyContainerRef.value,
    elements: normalizeElementLifecycleData(props.elements),
    style: cytoscapeStyle,
    layout: getLayoutConfig(props.layout),
    minZoom: 0.3,
    maxZoom: 3,
  })

  cy.on('tap', 'node', (evt: any) => {
    if (menuState.value.visible) {
      closeContextMenu()
    }
    emit('nodeClick', evt.target.data())
  })

  cy.on('tap', (evt: any) => {
    if (evt.target === cy) {
      closeContextMenu()
    }
  })

  cy.on('cxttap', (evt: any) => {
    if (evt.target === cy) {
      closeContextMenu()
    }
  })

  cy.on('mouseover', 'node', (evt: any) => {
    evt.target.style({ 'border-width': 4, 'border-color': '#409EFF' })
    emit('nodeHover', evt.target.data())
  })
  cy.on('mouseout', 'node', (evt: any) => {
    evt.target.removeStyle('border-width border-color')
  })

  cy.on('mouseover', 'edge', (evt: any) => {
    evt.target.addClass('review-hover')
  })
  cy.on('mouseout', 'edge', (evt: any) => {
    evt.target.removeClass('review-hover')
  })

  cy.on('cxttap', 'node', (evt: any) => {
    openContextMenu(evt, 'node')
  })
  cy.on('cxttap', 'edge', (evt: any) => {
    openContextMenu(evt, 'edge')
  })

  applyNodeClasses()
}

function applyNodeClasses() {
  if (!cy) return
  cy.nodes().removeClass('highlighted mastered')
  props.highlightNodes.forEach((id: string) => {
    const node = cy.getElementById(id)
    if (node.length) node.addClass('highlighted')
  })
  props.masteredNodes.forEach((id: string) => {
    const node = cy.getElementById(id)
    if (node.length) node.addClass('mastered')
  })
}

function setNodeReviewStatus(nodeId: string, status: string) {
  if (!cy) return
  const node = cy.getElementById(nodeId)
  if (!node.length) return
  const nextStatus = getReviewStatus(status)
  node.data('review_status', nextStatus)
  if (menuState.value.visible && isActiveMenuTarget('node', nodeId)) {
    menuState.value = {
      ...menuState.value,
      targetData: {
        ...menuState.value.targetData,
        review_status: nextStatus,
      },
    }
  }
}

function setEdgeReviewStatus(edgeId: string, status: string) {
  if (!cy) return
  const edge = cy.getElementById(edgeId)
  if (!edge.length) return
  const nextStatus = getReviewStatus(status)
  edge.data('review_status', nextStatus)
  if (menuState.value.visible && isActiveMenuTarget('edge', edgeId)) {
    menuState.value = {
      ...menuState.value,
      targetData: {
        ...menuState.value.targetData,
        review_status: nextStatus,
      },
    }
  }
}

function handleMenuReview(status: string) {
  const { targetType, targetData } = menuState.value
  if (!targetType || !targetData?.id || !canEmitReview(targetData, status)) return

  if (targetType === 'node') {
    emit('reviewNode', targetData.id, status)
    return
  }

  emit('reviewEdge', targetData.id, status)
}

function handleViewNodeDetail() {
  const targetData = menuState.value.targetData
  if (!targetData) return
  emit('nodeClick', targetData)
  closeContextMenu()
}

onMounted(() => {
  isMounted = true
  nextTick(() => void initCytoscape())
})

onUnmounted(() => {
  isMounted = false
  initRequestId += 1
  closeContextMenu()
  if (cy) {
    cy.destroy()
    cy = null
  }
})

watch(() => props.elements, async () => {
  const nextElements = normalizeElementLifecycleData(props.elements)
  if (applyElementDataUpdates(nextElements)) {
    return
  }
  await nextTick()
  await initCytoscape()
})

watch(() => props.layout, (newLayout) => {
  closeContextMenu()
  if (cy) {
    const layout = cy.layout(getLayoutConfig(newLayout))
    layout.run()
  }
})

watch([() => props.highlightNodes, () => props.masteredNodes], () => {
  applyNodeClasses()
}, { deep: true })

watch(() => props.reviewMode, (enabled) => {
  if (!enabled) {
    closeContextMenu()
  }
})

defineExpose({
  zoomIn: () => {
    if (cy) cy.zoom({ level: cy.zoom() * 1.2, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } })
  },
  zoomOut: () => {
    if (cy) cy.zoom({ level: cy.zoom() / 1.2, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } })
  },
  fitView: () => {
    if (cy) cy.fit(undefined, 30)
  },
  focusNode: (nodeId: string) => {
    if (!cy) return false
    const node = cy.getElementById(nodeId)
    if (!node.length) return false

    closeContextMenu()
    const focusElements = node.closedNeighborhood()
    cy.stop()
    cy.animate({
      fit: {
        eles: focusElements.length ? focusElements : node,
        padding: 80,
      },
      duration: 500,
    })
    return true
  },
  highlightBySearch: (keyword: string) => {
    if (!cy) return
    cy.nodes().removeClass('search-match')
    if (!keyword) return
    cy.nodes().forEach((node: any) => {
      const label = (node.data('label') || '').toLowerCase()
      if (label.includes(keyword.toLowerCase())) {
        node.addClass('search-match')
      }
    })
  },
  setNodeReviewStatus,
  setEdgeReviewStatus,
})
</script>

<style scoped>
.graph-canvas {
  position: relative;
  width: 100%;
  height: 100%;
  background: #fafbfc;
  border: 1px solid #eee;
  border-radius: 4px;
  overflow: hidden;
}

.graph-canvas-surface {
  width: 100%;
  height: 100%;
}
</style>
