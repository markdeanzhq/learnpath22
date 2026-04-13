<template>
  <div
    v-show="visible"
    ref="menuRef"
    class="review-context-menu"
    :style="menuStyle"
    @contextmenu.prevent
  >
    <div class="menu-header">
      <span class="menu-title">{{ title }}</span>
      <span class="menu-status">{{ statusLabel }}</span>
    </div>

    <div v-if="isEdgeTarget" class="menu-meta">
      <div class="meta-row">
        <span class="meta-label">关系类型</span>
        <span class="meta-value">{{ targetData?.type || '未标注' }}</span>
      </div>
      <div v-if="targetData?.reason" class="meta-row meta-row-block">
        <span class="meta-label">关系说明</span>
        <span class="meta-value">{{ targetData.reason }}</span>
      </div>
      <div class="menu-divider"></div>
    </div>

    <div v-if="hintText" class="menu-hint">{{ hintText }}</div>

    <button
      v-for="action in reviewActions"
      :key="action.status"
      type="button"
      class="menu-item"
      :class="{ active: normalizedCurrentStatus === action.status }"
      @click="emit('review', action.status)"
    >
      <span>{{ action.label }}</span>
      <span v-if="normalizedCurrentStatus === action.status" class="menu-item-check">当前</span>
    </button>

    <div v-if="isNodeTarget" class="menu-divider"></div>

    <button
      v-if="isNodeTarget"
      type="button"
      class="menu-item menu-item-secondary"
      @click="emit('viewDetail')"
    >
      查看节点详情
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

type ReviewTargetType = 'node' | 'edge'
type ReviewStatus = 'confirmed' | 'removed' | 'pending'
type ReviewTargetData = {
  id?: string
  review_status?: string | null
  type?: string | null
  reason?: string | null
  [key: string]: unknown
}

const REVIEW_STATUSES: ReviewStatus[] = ['confirmed', 'removed', 'pending']

const props = withDefaults(defineProps<{
  visible: boolean
  x: number
  y: number
  containerWidth: number
  containerHeight: number
  targetType: ReviewTargetType | null
  targetData?: ReviewTargetData | null
  currentStatus?: ReviewStatus | null
  hintText?: string | null
}>(), {
  targetType: null,
  targetData: null,
  currentStatus: null,
  hintText: null,
})

const emit = defineEmits<{
  close: []
  review: [status: ReviewStatus]
  viewDetail: []
}>()

const menuRef = ref<HTMLDivElement>()
const menuStyle = ref<Record<string, string>>({
  left: '12px',
  top: '12px',
})

const reviewActions = [
  { status: 'confirmed', label: '确认保留' },
  { status: 'removed', label: '标记移除' },
  { status: 'pending', label: '恢复待审' },
] as const satisfies ReadonlyArray<{ status: ReviewStatus; label: string }>

const isNodeTarget = computed(() => props.targetType === 'node')
const isEdgeTarget = computed(() => props.targetType === 'edge')

function normalizeStatus(status?: ReviewStatus | string | null): ReviewStatus {
  return REVIEW_STATUSES.includes(status as ReviewStatus) ? status as ReviewStatus : 'pending'
}

const normalizedCurrentStatus = computed(() => normalizeStatus(props.currentStatus ?? props.targetData?.review_status))
const title = computed(() => isEdgeTarget.value ? '关系审核' : '节点审核')
const statusLabel = computed(() => {
  if (normalizedCurrentStatus.value === 'confirmed') return '已确认'
  if (normalizedCurrentStatus.value === 'removed') return '已移除'
  return '待审核'
})

function updatePosition() {
  if (!props.visible || !menuRef.value) {
    menuStyle.value = {
      left: '12px',
      top: '12px',
    }
    return
  }

  const rect = menuRef.value.getBoundingClientRect()
  const gap = 12
  const maxLeft = Math.max(gap, props.containerWidth - rect.width - gap)
  const maxTop = Math.max(gap, props.containerHeight - rect.height - gap)
  const left = Math.min(Math.max(props.x, gap), maxLeft)
  const top = Math.min(Math.max(props.y, gap), maxTop)

  menuStyle.value = {
    left: `${left}px`,
    top: `${top}px`,
  }
}

function handlePointerDown(event: MouseEvent) {
  if (!props.visible || !menuRef.value) return
  const target = event.target as Node | null
  if (target && menuRef.value.contains(target)) return
  emit('close')
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && props.visible) {
    emit('close')
  }
}

watch(
  () => [props.visible, props.x, props.y, props.containerWidth, props.containerHeight, props.targetType, props.targetData?.id, props.targetData?.type, props.targetData?.review_status, props.targetData?.reason, props.currentStatus, props.hintText],
  async () => {
    if (!props.visible) {
      menuStyle.value = {
        left: '12px',
        top: '12px',
      }
      return
    }
    await nextTick()
    updatePosition()
  },
  { immediate: true },
)

onMounted(() => {
  document.addEventListener('mousedown', handlePointerDown)
  window.addEventListener('keydown', handleKeydown)
  window.addEventListener('resize', updatePosition)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handlePointerDown)
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('resize', updatePosition)
})
</script>

<style scoped>
.review-context-menu {
  position: absolute;
  z-index: 20;
  min-width: 220px;
  max-width: 280px;
  padding: 8px;
  background: rgba(255, 255, 255, 0.97);
  border: 1px solid #dcdfe6;
  border-radius: 10px;
  box-shadow: 0 12px 28px rgba(31, 35, 41, 0.18);
  backdrop-filter: blur(8px);
}

.menu-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 8px 10px;
}

.menu-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.menu-status {
  font-size: 12px;
  color: #909399;
}

.menu-meta {
  padding: 0 8px 6px;
}

.menu-hint {
  padding: 0 10px 6px;
  font-size: 12px;
  line-height: 1.5;
  color: #909399;
}

.meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

.meta-row-block {
  display: block;
}

.meta-label {
  font-size: 12px;
  color: #909399;
}

.meta-value {
  font-size: 12px;
  color: #303133;
  word-break: break-word;
}

.menu-divider {
  height: 1px;
  margin: 6px 0;
  background: #ebeef5;
}

.menu-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 9px 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  font-size: 13px;
  color: #303133;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.menu-item:hover,
.menu-item.active {
  background: #ecf5ff;
  color: #409eff;
}

.menu-item-secondary:hover {
  background: #f4f4f5;
  color: #606266;
}

.menu-item-check {
  font-size: 12px;
  color: #409eff;
}
</style>
