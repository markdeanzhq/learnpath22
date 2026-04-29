<template>
  <div class="stage-timeline">
    <section v-if="!stages.length" class="timeline-empty-state">
      <h3>当前路径暂无阶段</h3>
      <p>学习路径已经创建但还没有可展示的阶段，请返回项目页重新生成，或检查画像和目标是否完整。</p>
    </section>

    <el-timeline v-else>
      <el-timeline-item
        v-for="stage in stages"
        :key="stage.stage_index"
        :color="stageColor(stage.stage_index)"
        :hollow="false"
        size="large"
      >
        <article class="stage-card">
          <header class="stage-card-header">
            <div>
              <span class="stage-index">阶段 {{ stage.stage_index + 1 }}</span>
              <h3>{{ stage.stage_name }}</h3>
            </div>
            <div class="stage-meta">
              <el-tag size="small" type="info">{{ stage.tasks.length }} 个知识点</el-tag>
              <el-tag size="small" effect="plain">{{ stageHoursLabel(stage) }}</el-tag>
            </div>
          </header>

          <p class="stage-guide">按顺序完成本阶段知识点，遇到陌生概念可先定位到图谱查看前置关系。</p>

          <el-empty v-if="!stage.tasks.length" description="该阶段暂无知识点，请重新生成路径或检查目标覆盖范围" />
          <el-row v-else :gutter="12" class="task-grid">
            <el-col
              v-for="task in stage.tasks"
              :key="task.node_id"
              :xs="24" :sm="12" :md="8" :lg="6"
            >
              <TaskCard
                :task="task"
                :task-number="task.order_in_stage + 1"
                @locate-node="handleLocateNode"
              />
            </el-col>
          </el-row>
        </article>
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
const stageColors = ['#409EFF', '#67C23A', '#E6A23C', '#909399']

function stageColor(stageIndex: number) {
  return stageColors[stageIndex % stageColors.length]
}

function stageHoursLabel(stage: PathStage) {
  return stage.estimated_hours ? `约 ${stage.estimated_hours} 小时` : '时长待估算'
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
.stage-timeline :deep(.el-timeline-item__content) {
  padding-bottom: 8px;
}

.timeline-empty-state {
  padding: 24px;
  border: 1px dashed var(--el-border-color);
  border-radius: 16px;
  background: var(--el-fill-color-light);
  text-align: center;
}

.timeline-empty-state h3 {
  margin: 0 0 8px;
  color: var(--el-text-color-primary);
}

.timeline-empty-state p {
  max-width: 560px;
  margin: 0 auto;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}

.stage-card {
  padding: 18px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 16px;
  background: linear-gradient(135deg, var(--el-fill-color-blank), var(--el-fill-color-light));
  box-shadow: 0 8px 24px rgb(15 23 42 / 5%);
}

.stage-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.stage-index {
  display: inline-flex;
  margin-bottom: 6px;
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.stage-card h3 {
  margin: 0;
  font-size: 18px;
  line-height: 1.4;
}

.stage-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.stage-guide {
  margin: 10px 0 16px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.task-grid {
  margin-bottom: -12px;
}

.task-grid .el-col {
  margin-bottom: 12px;
}

@media (max-width: 768px) {
  .stage-card {
    padding: 14px;
  }

  .stage-card-header {
    flex-direction: column;
  }

  .stage-meta {
    justify-content: flex-start;
  }
}
</style>
