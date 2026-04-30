<template>
  <section class="overlay-subsection goal-draft-summary">
    <h4>目标缺口分析</h4>
    <el-alert
      class="overlay-alert"
      type="warning"
      :closable="false"
      show-icon
      title="扩展草稿只作为审核候选；未确认审核并开启规划前，不会进入正式路径。"
    />
    <el-descriptions :column="1" border size="small">
      <el-descriptions-item v-if="details.gap_analysis?.user_goal" label="用户目标">
        {{ details.gap_analysis.user_goal }}
      </el-descriptions-item>
      <el-descriptions-item label="缺失概念">
        {{ missingConcepts.join('、') || '暂无' }}
      </el-descriptions-item>
      <el-descriptions-item v-if="details.gap_analysis?.why_current_graph_is_insufficient" label="缺口原因">
        {{ details.gap_analysis.why_current_graph_is_insufficient }}
      </el-descriptions-item>
      <el-descriptions-item v-if="showAuditDetails" label="草稿来源">
        {{ details.draft_metadata?.draft_engine || 'rules' }} / {{ details.draft_metadata?.prompt_version || 'unknown' }}
      </el-descriptions-item>
      <el-descriptions-item v-if="showAuditDetails" label="安全边界">
        需人工审核：{{ details.draft_metadata?.requires_user_review ? '是' : '否' }}；可直接规划：{{ details.draft_metadata?.can_directly_plan ? '是' : '否' }}
      </el-descriptions-item>
    </el-descriptions>
    <ul v-if="reviewNotes.length" class="review-notes">
      <li v-for="note in reviewNotes" :key="note">{{ note }}</li>
    </ul>
    <div v-if="showAuditDetails && reviewFocus.length" class="review-focus-list">
      <el-tag v-for="item in reviewFocus" :key="item" type="info" effect="plain">{{ item }}</el-tag>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { GoalExtensionDraftResponse } from '@/api/modules/graph'

defineProps<{
  details: GoalExtensionDraftResponse
  missingConcepts: string[]
  reviewNotes: string[]
  reviewFocus: string[]
  showAuditDetails: boolean
}>()
</script>

<style scoped>
.overlay-subsection {
  margin-top: 14px;
}

.overlay-subsection h4 {
  margin: 0 0 8px;
  color: #303133;
  font-size: 14px;
}

.overlay-alert {
  margin-bottom: 4px;
}

.goal-draft-summary {
  padding: 12px;
  border: 1px solid #f3d19e;
  border-radius: 10px;
  background: #fdf6ec;
}

.review-notes {
  margin: 10px 0 0;
  padding-left: 18px;
  color: #606266;
  font-size: 12px;
  line-height: 1.7;
}

.review-focus-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
</style>
