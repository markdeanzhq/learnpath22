<template>
  <div class="stage-timeline">
    <el-timeline>
      <el-timeline-item
        v-for="stage in stages"
        :key="stage.stage_index"
        :color="stageColors[stage.stage_index]"
        :hollow="false"
        size="large"
      >
        <div class="stage-header">
          <span class="stage-name">{{ stage.stage_name }}</span>
          <el-tag size="small" type="info">
            {{ stage.tasks.length }} 个知识点
            <template v-if="stage.estimated_hours"> · 约 {{ stage.estimated_hours }} 小时</template>
          </el-tag>
        </div>
        <el-row :gutter="12" class="task-grid">
          <el-col
            v-for="task in stage.tasks"
            :key="task.node_id"
            :xs="24" :sm="12" :md="8" :lg="6"
          >
            <TaskCard :task="task" @locate-node="handleLocateNode" />
          </el-col>
        </el-row>
      </el-timeline-item>
    </el-timeline>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { buildPathGraphQuery } from '@/api/modules/graph'
import type { PathStage } from '@/api/modules/plan'
import TaskCard from './TaskCard.vue'

defineProps<{ stages: PathStage[] }>()

const emit = defineEmits<{
  locateNode: [nodeId: string]
}>()

const router = useRouter()

function handleLocateNode(nodeId: string) {
  emit('locateNode', nodeId)
  router.push({
    name: 'Knowledge',
    query: buildPathGraphQuery(nodeId),
  })
}

const stageColors = ['#409EFF', '#67C23A', '#E6A23C']
</script>

<style scoped>
.stage-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.stage-name {
  font-size: 16px;
  font-weight: 600;
}
.task-grid {
  margin-bottom: 8px;
}
.task-grid .el-col {
  margin-bottom: 12px;
}
</style>
