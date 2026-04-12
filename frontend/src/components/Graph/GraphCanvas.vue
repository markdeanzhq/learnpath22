<template>
  <div ref="containerRef" class="graph-canvas"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import cytoscape from 'cytoscape'

const CATEGORY_COLORS: Record<string, string> = {
  foundation: '#E6A23C',
  math_foundation: '#409EFF',
  ml_core: '#F56C6C',
  algorithm: '#8B5CF6',
  evaluation: '#909399',
  practice: '#67C23A',
}

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
let cy: any = null

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
      'width': 2,
      'line-color': '#aaa',
      'target-arrow-color': '#aaa',
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
      'arrow-scale': 1.2,
    },
  },
  {
    selector: 'edge[type = "RELATED_TO"]',
    style: {
      'width': 1.5,
      'line-color': '#ccc',
      'line-style': 'dashed',
      'target-arrow-shape': 'none',
      'curve-style': 'bezier',
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
    selector: 'node[review_status = "removed"]',
    style: {
      'background-color': '#C0C4CC',
      'border-color': '#909399',
      'border-width': 2,
      'opacity': 0.5,
    },
  },
  {
    selector: 'edge[review_status = "removed"]',
    style: {
      'line-color': '#C0C4CC',
      'target-arrow-color': '#C0C4CC',
      'opacity': 0.3,
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

function initCytoscape() {
  if (!containerRef.value || !props.elements.length) return
  if (cy) { cy.destroy(); cy = null }

  cy = cytoscape({
    container: containerRef.value,
    elements: props.elements,
    style: cytoscapeStyle,
    layout: getLayoutConfig(props.layout),
    minZoom: 0.3,
    maxZoom: 3,
  })

  cy.on('tap', 'node', (evt: any) => {
    emit('nodeClick', evt.target.data())
  })
  cy.on('mouseover', 'node', (evt: any) => {
    evt.target.style({ 'border-width': 4, 'border-color': '#409EFF' })
    emit('nodeHover', evt.target.data())
  })
  cy.on('mouseout', 'node', (evt: any) => {
    evt.target.removeStyle('border-width border-color')
  })

  // 右键菜单 — 审核模式
  cy.on('cxttap', 'node', (evt: any) => {
    if (!props.reviewMode) return
    const data = evt.target.data()
    const current = data.review_status || 'pending'
    const next = current === 'confirmed' ? 'removed' : current === 'removed' ? 'pending' : 'confirmed'
    emit('reviewNode', data.id, next)
  })
  cy.on('cxttap', 'edge', (evt: any) => {
    if (!props.reviewMode) return
    const data = evt.target.data()
    const edgeId = `${data.source}->${data.target}`
    const current = data.review_status || 'pending'
    const next = current === 'confirmed' ? 'removed' : current === 'removed' ? 'pending' : 'confirmed'
    emit('reviewEdge', edgeId, next)
  })

  applyNodeClasses()
}

function applyNodeClasses() {
  if (!cy) return
  cy.nodes().removeClass('highlighted mastered search-match')
  props.highlightNodes.forEach((id: string) => {
    const node = cy.getElementById(id)
    if (node.length) node.addClass('highlighted')
  })
  props.masteredNodes.forEach((id: string) => {
    const node = cy.getElementById(id)
    if (node.length) node.addClass('mastered')
  })
}

onMounted(() => {
  nextTick(() => initCytoscape())
})

onUnmounted(() => {
  if (cy) { cy.destroy(); cy = null }
})

watch(() => props.elements, () => {
  nextTick(() => initCytoscape())
}, { deep: true })

watch(() => props.layout, (newLayout) => {
  if (cy) {
    const layout = cy.layout(getLayoutConfig(newLayout))
    layout.run()
  }
})

watch([() => props.highlightNodes, () => props.masteredNodes], () => {
  applyNodeClasses()
}, { deep: true })

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
})
</script>

<style scoped>
.graph-canvas {
  width: 100%;
  height: 100%;
  background: #fafbfc;
  border: 1px solid #eee;
  border-radius: 4px;
}
</style>
