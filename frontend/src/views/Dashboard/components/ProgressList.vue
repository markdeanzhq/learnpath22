<template>
  <div class="progress-list">
    <el-collapse v-model="activeStages">
      <el-collapse-item
        v-for="stage in stages"
        :key="stage.stage_index"
        :name="stage.stage_index"
      >
        <template #title>
          <div class="stage-title">
            <span>{{ stage.stage_name }}</span>
            <el-tag size="small" type="info">
              {{ completedCount(stage) }}/{{ stage.tasks.length }}
            </el-tag>
          </div>
        </template>

        <div
          v-for="task in stage.tasks"
          :key="task.node_id"
          class="task-row"
        >
          <div class="task-info">
            <el-icon :color="statusColor(statusMap[task.node_id] ?? 'pending')">
              <SuccessFilled v-if="statusMap[task.node_id] === 'completed'" />
              <Loading v-else-if="statusMap[task.node_id] === 'in_progress'" />
              <RemoveFilled v-else-if="statusMap[task.node_id] === 'skipped'" />
              <MoreFilled v-else />
            </el-icon>
            <span class="task-name">{{ task.name }}</span>
            <el-tag size="small" :type="difficultyType(task.difficulty)">
              难度 {{ task.difficulty }}
            </el-tag>
            <span v-if="task.estimated_hours" class="task-hours">{{ task.estimated_hours }}h</span>
            <el-button link type="primary" size="small" @click="handleLocateNode(task.node_id)">
              在图谱中定位
            </el-button>
          </div>

          <el-button-group size="small">
            <el-button
              :type="statusMap[task.node_id] === 'in_progress' ? 'primary' : ''"
              :disabled="statusMap[task.node_id] === 'in_progress'"
              @click="$emit('markStatus', task.node_id, 'start')"
            >开始</el-button>
            <el-button
              :type="statusMap[task.node_id] === 'completed' ? 'success' : ''"
              :disabled="statusMap[task.node_id] === 'completed'"
              @click="$emit('markStatus', task.node_id, 'complete')"
            >完成</el-button>
            <el-button
              :type="statusMap[task.node_id] === 'skipped' ? 'info' : ''"
              :disabled="statusMap[task.node_id] === 'skipped'"
              @click="$emit('markStatus', task.node_id, 'skip')"
            >跳过</el-button>
          </el-button-group>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { SuccessFilled, Loading, RemoveFilled, MoreFilled } from '@element-plus/icons-vue'
import type { PathStage } from '@/api/modules/plan'
import type { TrackingEventResponse } from '@/api/modules/tracking'

const props = defineProps<{
  stages: PathStage[]
  events: TrackingEventResponse[]
}>()

const emit = defineEmits<{
  markStatus: [nodeId: string, eventType: 'start' | 'complete' | 'skip']
  locateNode: [nodeId: string]
}>()

const router = useRouter()
const activeStages = computed(() => props.stages.map(s => s.stage_index))

const statusMap = computed(() => {
  const map: Record<string, string> = {}
  for (const evt of props.events) {
    const existing = map[evt.node_id]
    if (!existing) {
      map[evt.node_id] = evt.event_type === 'start' ? 'in_progress'
        : evt.event_type === 'complete' ? 'completed'
        : 'skipped'
    }
  }
  return map
})

function completedCount(stage: PathStage): number {
  return stage.tasks.filter(t => statusMap.value[t.node_id] === 'completed').length
}

function statusColor(status: string): string {
  if (status === 'completed') return '#67C23A'
  if (status === 'in_progress') return '#409EFF'
  if (status === 'skipped') return '#909399'
  return '#C0C4CC'
}

function difficultyType(d: number): '' | 'success' | 'warning' | 'danger' | 'info' {
  if (d <= 2) return 'success'
  if (d <= 3) return ''
  return 'warning'
}

function handleLocateNode(nodeId: string) {
  emit('locateNode', nodeId)
  router.push({
    name: 'Knowledge',
    query: {
      nodeId,
      scope: 'project',
    },
  })
}
</script>

<style scoped>
.stage-title {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.task-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}
.task-row:last-child { border-bottom: none; }
.task-info {
  display: flex;
  align-items: center;
  gap: 8px;
}
.task-name { font-size: 14px; }
.task-hours {
  color: #909399;
  font-size: 12px;
}

@media (max-width: 768px) {
  .task-row {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }

  .task-info {
    flex-wrap: wrap;
  }

  :deep(.el-button-group) {
    display: flex;
    width: 100%;
  }

  :deep(.el-button-group .el-button) {
    flex: 1;
  }
}
</style>