<template>
  <el-card shadow="hover" class="task-card" :class="difficultyClass">
    <div class="task-topline">
      <span class="task-order">第 {{ taskNumber }} 项</span>
      <el-tag :type="importanceType" size="small" effect="light">{{ importanceLabel }}</el-tag>
    </div>

    <h4 class="task-name">{{ task.name }}</h4>

    <div class="task-meta" aria-label="任务学习属性">
      <span class="meta-item">
        <el-icon><Star /></el-icon>
        {{ difficultyLabel }}
      </span>
      <span class="meta-item">
        <el-icon><Clock /></el-icon>
        {{ estimatedTimeLabel }}
      </span>
    </div>

    <p class="task-guidance">{{ guidanceLabel }}</p>

    <div class="task-actions">
      <el-button link type="primary" size="small" @click="emit('locateNode', task.node_id)">
        查看图谱位置
      </el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Star, Clock } from '@element-plus/icons-vue'
import type { PathTask } from '@/api/modules/plan'

const props = withDefaults(defineProps<{
  task: PathTask
  taskNumber?: number
  practiceIntensity?: number | null
}>(), {
  taskNumber: 1,
  practiceIntensity: null,
})

const emit = defineEmits<{
  locateNode: [nodeId: string]
}>()

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

const importanceLabel = computed(() => {
  if (props.task.importance >= 4) return '关键知识点'
  if (props.task.importance >= 2) return '常规知识点'
  return '了解即可'
})

const difficultyLabel = computed(() => {
  if (props.task.difficulty <= 2) return `入门难度 ${props.task.difficulty}/5`
  if (props.task.difficulty <= 3) return `中等难度 ${props.task.difficulty}/5`
  return `较高难度 ${props.task.difficulty}/5`
})

const estimatedTimeLabel = computed(() => (
  props.task.estimated_hours ? `约 ${props.task.estimated_hours} 小时` : '时长待估算'
))

const normalizedPracticeIntensity = computed(() => (
  typeof props.practiceIntensity === 'number' ? props.practiceIntensity : 3
))

const practiceGuidance = computed(() => {
  if (normalizedPracticeIntensity.value >= 4) return '高练习密度：优先在推荐资源中找代码、案例或小题完成一次动手验证。'
  if (normalizedPracticeIntensity.value <= 2) return '低练习密度：先记录关键概念，练习可作为复盘选项。'
  return '均衡练习密度：学完后做一次小练习或复述检查。'
})

const guidanceLabel = computed(() => {
  if (props.task.importance >= 4) return `关键节点：${practiceGuidance.value}`
  if (props.task.difficulty >= 4) return '难度较高：建议拆成小目标，必要时回看前置概念。'
  return `建议动作：${practiceGuidance.value}`
})
</script>

<style scoped>
.task-card {
  height: 100%;
  border-left: 4px solid var(--el-border-color);
  transition: transform 0.18s ease, box-shadow 0.18s ease;
}

.task-card :deep(.el-card__body) {
  padding: 14px;
}

.task-card:hover {
  transform: translateY(-2px);
}

.task-card.diff-easy { border-left-color: var(--el-color-success); }
.task-card.diff-medium { border-left-color: var(--el-color-primary); }
.task-card.diff-hard { border-left-color: var(--el-color-warning); }

.task-topline {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.task-order {
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
}

.task-name {
  margin: 0 0 10px;
  color: var(--el-text-color-primary);
  font-size: 15px;
  line-height: 1.5;
}

.task-meta {
  display: flex;
  gap: 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  flex-wrap: wrap;
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.task-guidance {
  display: -webkit-box;
  min-height: 40px;
  margin: 10px 0 0;
  overflow: hidden;
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.6;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.task-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}

@media (max-width: 768px) {
  .task-topline {
    align-items: flex-start;
    flex-direction: column;
  }

  .task-guidance {
    min-height: auto;
  }
}
</style>
