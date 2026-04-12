<template>
  <el-card shadow="hover" class="task-card" :class="difficultyClass">
    <div class="task-header">
      <span class="task-name">{{ task.name }}</span>
      <el-tag :type="importanceType" size="small">
        {{ task.importance >= 4 ? '重要' : task.importance >= 2 ? '一般' : '了解' }}
      </el-tag>
    </div>
    <div class="task-meta">
      <span class="meta-item">
        <el-icon><Star /></el-icon>
        难度 {{ task.difficulty }}/5
      </span>
      <span v-if="task.estimated_hours" class="meta-item">
        <el-icon><Clock /></el-icon>
        约 {{ task.estimated_hours }} 小时
      </span>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Star, Clock } from '@element-plus/icons-vue'
import type { PathTask } from '@/api/modules/plan'

const props = defineProps<{ task: PathTask }>()

const difficultyClass = computed(() => {
  if (props.task.difficulty <= 2) return 'diff-easy'
  if (props.task.difficulty <= 3) return 'diff-medium'
  return 'diff-hard'
})

const importanceType = computed(() => {
  if (props.task.importance >= 4) return 'danger'
  if (props.task.importance >= 2) return ''
  return 'info'
})
</script>

<style scoped>
.task-card {
  border-left: 3px solid #dcdfe6;
}
.task-card.diff-easy { border-left-color: #67C23A; }
.task-card.diff-medium { border-left-color: #409EFF; }
.task-card.diff-hard { border-left-color: #E6A23C; }

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  gap: 8px;
}
.task-name {
  font-weight: 500;
  font-size: 14px;
}
.task-meta {
  display: flex;
  gap: 16px;
  color: #909399;
  font-size: 13px;
  flex-wrap: wrap;
}
.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

@media (max-width: 768px) {
  .task-header {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>