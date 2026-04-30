<template>
  <section class="overlay-preflight-panel graph-alert">
    <div class="overlay-preflight-header">
      <strong>增强图谱使用状态</strong>
      <el-tag :type="tagType">{{ statusLabel }}</el-tag>
    </div>
    <p>{{ preflight.summary }}</p>
    <p class="overlay-guidance">{{ guidance }}</p>
    <div class="overlay-preflight-tags">
      <el-tag type="info" effect="plain">候选 {{ preflight.counts.active_nodes }} 节点 / {{ preflight.counts.active_edges }} 关系</el-tag>
      <el-tag type="success" effect="plain">可进入增强图谱 {{ preflight.counts.visible_overlay_nodes }} 节点 / {{ preflight.counts.visible_overlay_edges }} 关系</el-tag>
      <el-tag type="warning" effect="plain">待审核 {{ preflight.counts.nodes.pending_review + preflight.counts.edges.pending_review }}</el-tag>
      <el-tag type="danger" effect="plain">校验失败 {{ preflight.counts.nodes.invalid + preflight.counts.edges.invalid }}</el-tag>
      <el-tag type="warning" effect="plain">当前路径命中 {{ preflight.counts.path_overlay_nodes }} 节点 / {{ preflight.counts.path_overlay_edges }} 关系</el-tag>
      <el-tag v-if="preflight.counts.ignored_overlay_edges" type="warning" effect="plain">忽略关系 {{ preflight.counts.ignored_overlay_edges }}</el-tag>
    </div>
    <div v-if="issues.length" class="overlay-preflight-issues">
      <span v-for="(item, index) in issues" :key="`${item.kind}-${index}`">{{ item.message }}</span>
    </div>
    <div v-if="candidateActions.length" class="overlay-preflight-candidate-actions">
      <div class="overlay-preflight-action-copy">
        <strong>候选处理入口</strong>
        <span>{{ primaryAction?.description || '打开候选队列后再显式修复、审核或开启规划。' }}</span>
      </div>
      <div class="overlay-preflight-action-buttons">
        <el-button
          v-for="action in candidateActions"
          :key="action.actionType"
          size="small"
          :type="actionButtonType(action.tagType)"
          plain
          @click="emit('open-candidate-action', action)"
        >
          {{ action.label }}
        </el-button>
      </div>
    </div>
    <div v-if="canOpenPathComparison" class="overlay-preflight-actions">
      <span>已纳入规划的扩展可在学习路径页比较基础/增强图谱影响。</span>
      <el-button size="small" type="primary" plain @click="emit('open-path-comparison')">
        查看路径对比
      </el-button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { OverlayPreflightItem, OverlayPreflightResponse } from '@/api/modules/graph'
import type { OverlayPreflightCandidateAction } from './composables/useOverlayCandidateWorkflow'

const props = withDefaults(defineProps<{
  preflight: OverlayPreflightResponse
  tagType: string
  statusLabel: string
  guidance: string
  issues: OverlayPreflightItem[]
  candidateActions?: OverlayPreflightCandidateAction[]
  primaryAction?: OverlayPreflightCandidateAction | null
}>(), {
  candidateActions: () => [],
  primaryAction: null,
})

const emit = defineEmits<{
  'open-path-comparison': []
  'open-candidate-action': [action: OverlayPreflightCandidateAction]
}>()

const canOpenPathComparison = computed(() => (
  props.preflight.status !== 'blocked'
  && Boolean(props.preflight.counts.visible_overlay_nodes || props.preflight.counts.visible_overlay_edges)
))

function actionButtonType(tagType: OverlayPreflightCandidateAction['tagType']) {
  return tagType === 'danger' ? 'danger' : tagType
}
</script>

<style scoped>
.graph-alert {
  margin: 12px 12px 0;
}

.overlay-preflight-panel {
  padding: 12px;
  border: 1px solid #dcdfe6;
  border-radius: 10px;
  background: #fff;
}

.overlay-preflight-header,
.overlay-preflight-tags,
.overlay-preflight-issues {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.overlay-preflight-header {
  justify-content: space-between;
}

.overlay-preflight-panel p {
  margin: 8px 0;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
}

.overlay-preflight-issues {
  margin-top: 8px;
  color: #e6a23c;
  font-size: 12px;
}

.overlay-preflight-actions,
.overlay-preflight-candidate-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
  padding: 10px;
  border-radius: 8px;
  color: #606266;
  font-size: 12px;
}

.overlay-preflight-actions {
  border: 1px solid #d9ecff;
  background: #ecf5ff;
}

.overlay-preflight-candidate-actions {
  border: 1px solid #fde2e2;
  background: #fef0f0;
}

.overlay-preflight-action-copy {
  display: grid;
  gap: 4px;
  min-width: 220px;
}

.overlay-preflight-action-copy strong {
  color: #303133;
}

.overlay-preflight-action-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.overlay-guidance {
  margin: 4px 0 0;
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
}
</style>
