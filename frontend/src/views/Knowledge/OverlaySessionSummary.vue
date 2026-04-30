<template>
  <div class="section-header">
    <div>
      <h3>抽取结果</h3>
      <p v-if="showTechnicalDetails">追溯编号：{{ session.session.session_id }}</p>
      <p v-else>{{ overlaySessionGuide }}</p>
    </div>
    <el-tag :type="sessionStatusMeta(session.session.session_status).tagType" :title="session.session.session_status">
      {{ sessionStatusMeta(session.session.session_status).label }}
    </el-tag>
  </div>
  <el-descriptions :column="1" border size="small">
    <el-descriptions-item label="节点候选">{{ session.nodes?.length || 0 }}</el-descriptions-item>
    <el-descriptions-item label="关系候选">{{ session.edges?.length || 0 }}</el-descriptions-item>
    <el-descriptions-item label="资源候选">{{ session.resources?.length || 0 }}</el-descriptions-item>
    <el-descriptions-item label="校验概览">
      通过 {{ overlaySessionStats.valid }}，失败 {{ overlaySessionStats.invalid }}，待复核 {{ overlaySessionStats.needsReview }}，待审核 {{ overlaySessionStats.pendingReview }}
    </el-descriptions-item>
    <el-descriptions-item label="来源数">{{ session.sources?.length || 0 }}</el-descriptions-item>
  </el-descriptions>
  <el-alert
    class="overlay-alert"
    :type="overlaySessionStats.invalid ? 'warning' : 'info'"
    :closable="false"
    show-icon
    :title="overlaySessionGuide"
  />
</template>

<script setup lang="ts">
import { sessionStatusMeta } from '@/utils/displayLabels'
import type { OverlaySessionView } from './composables/useOverlayCandidateWorkflow'
import type { OverlaySessionStats } from './overlaySessionPanelTypes'

defineProps<{
  session: OverlaySessionView
  showTechnicalDetails: boolean
  overlaySessionGuide: string
  overlaySessionStats: OverlaySessionStats
}>()
</script>

<style scoped>
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

h3 {
  margin: 0;
  color: #303133;
  font-size: 16px;
}

p {
  margin: 4px 0 0;
  color: #909399;
  font-size: 12px;
  word-break: break-all;
}

.overlay-alert {
  margin-bottom: 4px;
}
</style>
