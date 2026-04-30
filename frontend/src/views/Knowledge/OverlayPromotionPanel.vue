<template>
  <section class="overlay-subsection">
    <h4>高级操作：推广到领域包</h4>
    <el-button size="small" :loading="promotionLoading" @click="emit('preview-promotion')">预览推广结果（不写入）</el-button>
    <el-descriptions v-if="promotionPreview" class="promotion-summary" :column="1" border size="small">
      <el-descriptions-item label="状态">
        <el-tag
          size="small"
          :type="promotionPreviewStatusMeta(promotionPreview.status).tagType"
          :title="promotionPreviewStatusMeta(promotionPreview.status).detail || promotionPreview.status"
        >
          {{ promotionPreviewStatusMeta(promotionPreview.status).label }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="候选数">{{ promotionPreview.candidate_count }}</el-descriptions-item>
      <el-descriptions-item label="原领域包指纹">{{ promotionPreview.baseline_pack_hash }}</el-descriptions-item>
      <el-descriptions-item label="推广后指纹">{{ promotionPreview.resulting_pack_hash }}</el-descriptions-item>
      <el-descriptions-item label="资源明细">{{ promotionPreview.resources?.length || 0 }}</el-descriptions-item>
      <el-descriptions-item label="写入说明">预览只校验，不写入领域包、Neo4j 或候选状态。</el-descriptions-item>
    </el-descriptions>
    <el-alert
      v-if="promotionPreview?.errors?.length"
      class="overlay-alert"
      type="warning"
      :closable="false"
      show-icon
      :title="promotionPreview.errors.join('; ')"
    />
    <el-input
      :model-value="promotionSecret"
      class="promotion-secret"
      type="password"
      show-password
      placeholder="输入管理员密钥后确认推广"
      @update:model-value="emit('update:promotionSecret', String($event))"
    />
    <el-button size="small" type="danger" :loading="promotionLoading" @click="emit('commit-promotion')">确认推广</el-button>
    <el-alert
      v-if="promotionResult"
      class="overlay-alert"
      :type="promotionResult.status === 'promoted' || promotionResult.reason === 'promoted' ? 'success' : 'info'"
      :closable="false"
      show-icon
      :title="promotionStatusMessage"
    />
  </section>
</template>

<script setup lang="ts">
import type { OverlayPromotionResponse } from '@/api/modules/graph'
import { promotionPreviewStatusMeta } from '@/utils/displayLabels'

defineProps<{
  promotionPreview: OverlayPromotionResponse | null
  promotionResult: OverlayPromotionResponse | null
  promotionSecret: string
  promotionLoading: boolean
  promotionStatusMessage: string
}>()

const emit = defineEmits<{
  'update:promotionSecret': [secret: string]
  'preview-promotion': []
  'commit-promotion': []
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

.promotion-summary,
.promotion-secret {
  margin-top: 10px;
}
</style>
