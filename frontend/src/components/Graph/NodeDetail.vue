<template>
  <el-drawer v-model="visible" title="节点详情" :size="380" direction="rtl">
    <template v-if="node">
      <div class="detail-content">
        <section class="detail-section">
          <h3>{{ node.label }}</h3>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="类别">
              <el-tag :color="categoryColor" effect="dark" size="small" style="color: #fff">
                {{ categoryLabel }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="难度">
              <el-rate :model-value="node.difficulty" disabled :max="5" size="small" />
            </el-descriptions-item>
            <el-descriptions-item label="重要性">
              <el-rate :model-value="node.importance" disabled :max="5" size="small" />
            </el-descriptions-item>
            <el-descriptions-item v-if="node.estimated_hours" label="预计学时">
              {{ node.estimated_hours }} 小时
            </el-descriptions-item>
            <el-descriptions-item label="主路径">
              <el-tag :type="node.is_main_path ? 'success' : 'info'" size="small">
                {{ node.is_main_path ? '是' : '否' }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </section>

        <section class="detail-section">
          <div class="section-header">
            <div>
              <h4>关联边审核</h4>
              <p class="section-subtitle">直接在侧栏审核与当前节点相连的关系</p>
            </div>
            <el-tag size="small" type="info">{{ adjacentEdges.length }} 条</el-tag>
          </div>

          <el-empty
            v-if="adjacentEdges.length === 0"
            :image-size="72"
            description="当前节点暂无关联边"
          />

          <div v-else class="edge-list">
            <article v-for="edge in adjacentEdges" :key="edge.id" class="edge-card">
              <div class="edge-card-header">
                <div class="edge-card-main">
                  <div class="edge-target">{{ getCounterpartLabel(edge) }}</div>
                  <div class="edge-direction">{{ getDirectionLabel(edge) }}</div>
                </div>
                <el-tag size="small" :type="getStatusTagType(edge.review_status)">
                  {{ getStatusLabel(edge.review_status) }}
                </el-tag>
              </div>

              <div class="edge-meta">
                <span class="edge-meta-label">关系类型</span>
                <span class="edge-meta-value">{{ getRelationLabel(edge.type) }}</span>
              </div>

              <div class="edge-meta edge-meta-block">
                <span class="edge-meta-label">reason</span>
                <span class="edge-meta-value">{{ edge.reason || '未提供' }}</span>
              </div>

              <div class="edge-actions">
                <el-button
                  v-for="action in reviewActions"
                  :key="action.status"
                  size="small"
                  :type="normalizeStatus(edge.review_status) === action.status ? action.buttonType : 'default'"
                  :plain="normalizeStatus(edge.review_status) !== action.status"
                  :disabled="normalizeStatus(edge.review_status) === action.status"
                  @click="emit('review-edge', edge.id, action.status)"
                >
                  {{ action.label }}
                </el-button>
              </div>
            </article>
          </div>
        </section>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { GraphEdgeData, GraphNodeData, ReviewStatus } from '@/api/modules/graph'
import { CATEGORY_COLORS, CATEGORY_LABELS, GRAPH_RELATION_LEGEND } from './graphMeta'

type SelectedAdjacentEdge = GraphEdgeData & {
  direction: 'incoming' | 'outgoing'
  source_label?: string
  target_label?: string
}

type NodeDetailData = GraphNodeData & {
  adjacent_edges?: SelectedAdjacentEdge[]
  incoming_edges?: SelectedAdjacentEdge[]
  outgoing_edges?: SelectedAdjacentEdge[]
}

const REVIEW_STATUSES: ReviewStatus[] = ['pending', 'confirmed', 'removed']
const RELATION_LABELS = Object.fromEntries(
  GRAPH_RELATION_LEGEND.map(({ type, label }) => [type, label]),
) as Record<string, string>

const props = defineProps<{ node: NodeDetailData | null }>()
const emit = defineEmits<{
  'review-edge': [edgeId: string, status: ReviewStatus]
}>()

const visible = ref(false)
const reviewActions = [
  { status: 'confirmed', label: '确认保留', buttonType: 'success' },
  { status: 'removed', label: '标记移除', buttonType: 'danger' },
  { status: 'pending', label: '恢复待审', buttonType: 'warning' },
] as const satisfies ReadonlyArray<{
  status: ReviewStatus
  label: string
  buttonType: 'success' | 'danger' | 'warning'
}>

watch(
  () => props.node,
  (val) => {
    visible.value = !!val
  },
  { immediate: true },
)

const categoryColor = computed(() => CATEGORY_COLORS[props.node?.category || ''] || '#909399')
const categoryLabel = computed(() => CATEGORY_LABELS[props.node?.category || ''] || props.node?.category || '')
const adjacentEdges = computed(() => props.node?.adjacent_edges || [])

function normalizeStatus(status?: string | null): ReviewStatus {
  return REVIEW_STATUSES.includes(status as ReviewStatus) ? (status as ReviewStatus) : 'pending'
}

function getStatusLabel(status?: string | null) {
  if (normalizeStatus(status) === 'confirmed') return '已确认'
  if (normalizeStatus(status) === 'removed') return '已移除'
  return '待审核'
}

function getStatusTagType(status?: string | null) {
  if (normalizeStatus(status) === 'confirmed') return 'success'
  if (normalizeStatus(status) === 'removed') return 'danger'
  return 'warning'
}

function getRelationLabel(type?: string | null) {
  return type ? RELATION_LABELS[type] || type : '未标注'
}

function getCounterpartLabel(edge: SelectedAdjacentEdge) {
  if (edge.direction === 'incoming') {
    return edge.source_label || edge.source || '未命名节点'
  }
  return edge.target_label || edge.target || '未命名节点'
}

function getDirectionLabel(edge: SelectedAdjacentEdge) {
  return edge.direction === 'incoming' ? '来源节点' : '指向节点'
}
</script>

<style scoped>
.detail-content {
  height: 100%;
  padding: 0 10px 16px;
  overflow-y: auto;
}

.detail-section + .detail-section {
  margin-top: 24px;
}

.detail-content h3 {
  margin: 0 0 16px;
  font-size: 18px;
  color: #303133;
}

.section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.section-header h4 {
  margin: 0;
  font-size: 16px;
  color: #303133;
}

.section-subtitle {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: #909399;
}

.edge-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.edge-card {
  padding: 12px;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  background: #fff;
}

.edge-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.edge-card-main {
  min-width: 0;
}

.edge-target {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  word-break: break-word;
}

.edge-direction {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}

.edge-meta {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
}

.edge-meta-block {
  display: block;
}

.edge-meta-label {
  font-size: 12px;
  color: #909399;
}

.edge-meta-value {
  font-size: 13px;
  line-height: 1.5;
  color: #606266;
  word-break: break-word;
}

.edge-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
</style>
