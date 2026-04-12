<template>
  <div class="stats-overview" v-if="summary">
    <el-row :gutter="16">
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="已完成" :value="summary.completed">
            <template #suffix>
              <span class="stat-unit"> / {{ summary.total_nodes }}</span>
            </template>
          </el-statistic>
          <div class="stat-bar" style="background: #67C23A" />
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="学习中" :value="summary.in_progress" />
          <div class="stat-bar" style="background: #409EFF" />
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="已跳过" :value="summary.skipped" />
          <div class="stat-bar" style="background: #909399" />
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="待学习" :value="summary.pending" />
          <div class="stat-bar" style="background: #E6A23C" />
        </el-card>
      </el-col>
    </el-row>

    <div class="progress-ring">
      <el-progress
        type="circle"
        :percentage="Math.round(summary.completion_rate * 100)"
        :width="120"
        :color="progressColor"
      />
      <p class="progress-label">总体完成率</p>
    </div>
  </div>
  <el-empty v-else description="暂无进度数据" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TrackingSummary } from '@/api/modules/tracking'

const props = defineProps<{ summary: TrackingSummary | null }>()

const progressColor = computed(() => {
  const rate = (props.summary?.completion_rate ?? 0) * 100
  if (rate >= 70) return '#67C23A'
  if (rate >= 30) return '#E6A23C'
  return '#F56C6C'
})
</script>

<style scoped>
.stat-card {
  text-align: center;
  position: relative;
  overflow: hidden;
}
.stat-bar {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3px;
}
.stat-unit {
  font-size: 14px;
  color: #909399;
}
.progress-ring {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-top: 24px;
}
.progress-label {
  margin-top: 8px;
  color: #606266;
  font-size: 14px;
}

@media (max-width: 768px) {
  :deep(.el-col) {
    margin-bottom: 12px;
  }
}
</style>