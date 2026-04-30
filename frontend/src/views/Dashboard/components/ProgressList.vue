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

        <section
          v-for="task in stage.tasks"
          :key="task.node_id"
          class="task-block"
        >
          <div class="task-row">
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

          <details class="task-resources">
            <summary>
              <span>学习资料 {{ taskResources(task.node_id).length }} 条</span>
              <small v-if="resourcesLoading">加载中...</small>
              <small v-else-if="resourceError">资源暂不可用</small>
            </summary>
            <p v-if="resourcesLoading" class="resource-fallback">正在加载该知识点绑定资源，进度操作可继续使用。</p>
            <p v-else-if="resourceError" class="resource-fallback warning">{{ resourceError }}；进度操作仍可继续。</p>
            <p v-else-if="!taskResources(task.node_id).length" class="resource-fallback">该知识点暂无绑定资源，可先继续记录进度，稍后到学习路径页补充。</p>
            <article v-for="resource in taskResources(task.node_id)" :key="resource.id" class="task-resource-card">
              <div class="task-resource-header">
                <a v-if="safeExternalUrl(resource.url)" :href="safeExternalUrl(resource.url)" target="_blank" rel="noopener" class="resource-link">{{ resource.title }}</a>
                <span v-else class="resource-title">{{ resource.title }}</span>
                <el-tag size="small" :type="resourceTagType(resource.source_type)">{{ resourceSourceLabel(resource.source_type) }}</el-tag>
              </div>
              <p>{{ resource.snippet || '暂无摘要' }}</p>
            </article>
          </details>
        </section>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { SuccessFilled, Loading, RemoveFilled, MoreFilled } from '@element-plus/icons-vue'
import { buildPathGraphQuery } from '@/api/modules/graph'
import type { PathStage } from '@/api/modules/plan'
import type { ResourceItem } from '@/api/modules/resource'
import type { TrackingEventResponse } from '@/api/modules/tracking'

type NodeResourcesMap = Record<string, ResourceItem[]>

const props = withDefaults(defineProps<{
  stages: PathStage[]
  events: TrackingEventResponse[]
  nodeResourcesMap?: NodeResourcesMap
  resourcesLoading?: boolean
  resourceError?: string
}>(), {
  nodeResourcesMap: () => ({}),
  resourcesLoading: false,
  resourceError: '',
})

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

function taskResources(nodeId: string) {
  return props.nodeResourcesMap[nodeId] || []
}

function safeExternalUrl(url?: string | null) {
  if (!url) return ''
  try {
    const parsed = new URL(url)
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.toString() : ''
  } catch {
    return ''
  }
}

function resourceSourceLabel(sourceType: string) {
  if (sourceType === 'static') return '内置资料'
  if (sourceType === 'tavily_auto') return '在线增强'
  if (sourceType === 'manual') return '手动绑定'
  return sourceType || '资料'
}

function resourceTagType(sourceType: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  if (sourceType === 'static') return 'success'
  if (sourceType === 'tavily_auto') return 'warning'
  return 'info'
}

function handleLocateNode(nodeId: string) {
  emit('locateNode', nodeId)
  router.push({
    name: 'Knowledge',
    query: buildPathGraphQuery(nodeId),
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
.task-block {
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}
.task-block:last-child { border-bottom: none; }
.task-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
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
.task-resources {
  margin: 8px 0 0 28px;
  padding: 8px 10px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fafafa;
}
.task-resources summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  cursor: pointer;
  color: #606266;
  font-size: 13px;
}
.task-resources summary small {
  color: #909399;
}
.resource-fallback {
  margin: 8px 0 0;
  color: #909399;
  font-size: 12px;
}
.resource-fallback.warning {
  color: #e6a23c;
}
.task-resource-card {
  margin-top: 8px;
  padding: 8px;
  border-radius: 6px;
  background: #fff;
}
.task-resource-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.resource-link,
.resource-title {
  color: #303133;
  font-weight: 600;
  text-decoration: none;
}
.task-resource-card p {
  margin: 6px 0 0;
  color: #606266;
  font-size: 12px;
  line-height: 1.5;
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

  .task-resources {
    margin-left: 0;
    width: 100%;
  }

  .task-resource-header {
    align-items: flex-start;
    flex-direction: column;
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