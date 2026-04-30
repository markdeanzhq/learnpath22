<template>
  <section class="graph-status-panel">
    <div>
      <strong>{{ scopeLabel }}</strong>
      <p>{{ statusHint }}</p>
    </div>
    <div class="graph-status-meta">
      <div class="graph-status-tags">
        <el-tag size="small" type="info" effect="plain">节点 {{ nodeCount }}</el-tag>
        <el-tag size="small" type="info" effect="plain">关系 {{ edgeCount }}</el-tag>
        <el-tag size="small" type="success" effect="plain">本地读模型</el-tag>
        <el-tag v-if="overlayPreflight" size="small" :type="overlayPreflightTagType" effect="plain">
          增强候选 {{ overlayPreflight.counts.visible_overlay_nodes }} / {{ overlayPreflight.counts.visible_overlay_edges }}
        </el-tag>
      </div>
      <div v-if="showGraphCacheDiagnostics" class="graph-cache-diagnostics" data-testid="graph-cache-diagnostics">
        <span class="graph-cache-title">缓存诊断</span>
        <el-tag
          v-for="item in graphCacheDiagnosticItems"
          :key="item.key"
          size="small"
          type="info"
          effect="plain"
        >
          {{ item.label }} {{ item.hitRateLabel }} · {{ item.sizeLabel }}
        </el-tag>
        <el-tag v-if="graphCacheStatsLoading" size="small" type="warning" effect="plain">刷新中</el-tag>
        <el-tag v-if="graphCacheStatsError" size="small" type="danger" effect="plain">{{ graphCacheStatsError }}</el-tag>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { OverlayPreflightResponse } from '@/api/modules/graph'
import type { GraphCacheDiagnosticItem } from './composables/useGraphCacheDiagnostics'

defineProps<{
  scopeLabel: string
  statusHint: string
  nodeCount: number
  edgeCount: number
  overlayPreflight: OverlayPreflightResponse | null
  overlayPreflightTagType: string
  showGraphCacheDiagnostics: boolean
  graphCacheDiagnosticItems: GraphCacheDiagnosticItem[]
  graphCacheStatsLoading: boolean
  graphCacheStatsError: string
}>()
</script>

<style scoped>
.graph-status-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 12px 12px 0;
  padding: 12px;
  border: 1px solid #e1f3d8;
  border-radius: 12px;
  background: linear-gradient(135deg, #f0f9eb 0%, #f5f7fa 100%);
}

.graph-status-panel strong {
  display: block;
  margin-bottom: 4px;
  color: #303133;
  font-size: 14px;
}

.graph-status-panel p {
  margin: 0;
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
}

.graph-status-meta,
.graph-status-tags,
.graph-cache-diagnostics {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.graph-status-meta {
  flex-direction: column;
  align-items: flex-end;
}

.graph-cache-diagnostics {
  align-items: center;
  color: #909399;
  font-size: 12px;
}

.graph-cache-title {
  font-weight: 600;
}

@media (max-width: 768px) {
  .graph-status-panel {
    flex-direction: column;
    align-items: flex-start;
  }

  .graph-status-tags {
    justify-content: flex-start;
  }
}
</style>
