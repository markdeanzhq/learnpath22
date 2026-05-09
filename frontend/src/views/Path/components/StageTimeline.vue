<template>
  <div class="stage-focus-board">
    <section v-if="!stages.length" class="timeline-empty-state">
      <h3>当前路径暂无阶段</h3>
      <p>学习路径已经创建但还没有可展示的阶段，请返回项目页重新生成，或检查画像和目标是否完整。</p>
    </section>

    <template v-else>
      <aside class="stage-nav" aria-label="学习阶段导航">
        <button
          v-for="stage in stages"
          :key="stage.stage_index"
          type="button"
          class="stage-nav-item"
          :class="{ active: stage.stage_index === selectedStageIndex }"
          @click="selectedStageIndex = stage.stage_index"
        >
          <span>阶段 {{ stage.stage_index + 1 }}</span>
          <strong>{{ stage.stage_name }}</strong>
          <small>{{ stage.tasks.length }} 个知识点 · {{ stageHoursLabel(stage) }}</small>
        </button>
      </aside>

      <section class="stage-detail" v-if="selectedStage">
        <header class="stage-detail-header">
          <div>
            <span class="stage-index">阶段 {{ selectedStage.stage_index + 1 }}</span>
            <h3>{{ selectedStage.stage_name }}</h3>
            <p>{{ stageGuide(selectedStage) }}</p>
          </div>
          <div class="stage-meta">
            <el-tag size="small" type="info">{{ selectedStage.tasks.length }} 个知识点</el-tag>
            <el-tag size="small" effect="plain">{{ stageHoursLabel(selectedStage) }}</el-tag>
          </div>
        </header>

        <section v-if="!selectedStage.tasks.length" class="stage-empty-reason">
          <el-empty :description="selectedStage.empty_reason || defaultEmptyStageReason" />
          <p>这不是规划失败；系统不会为了填满版式加入无关知识点。</p>
        </section>

        <div v-else class="task-list lp-scroll-panel">
          <TaskCard
            v-for="task in selectedStage.tasks"
            :key="task.node_id"
            :task="task"
            :task-number="task.order_in_stage + 1"
            :practice-intensity="practiceIntensity"
            @locate-node="handleLocateNode"
          />
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { buildPathGraphQuery } from '@/api/modules/graph'
import type { PathStage } from '@/api/modules/plan'
import TaskCard from './TaskCard.vue'

const props = withDefaults(defineProps<{
  stages: PathStage[]
  practiceIntensity?: number | null
}>(), {
  practiceIntensity: null,
})

const emit = defineEmits<{
  locateNode: [nodeId: string]
}>()

const router = useRouter()
const selectedStageIndex = ref(0)
const defaultEmptyStageReason = '当前目标范围没有匹配到该阶段的知识点；系统不会为填充版式加入无关节点。'
const selectedStage = computed(() => (
  props.stages.find((stage) => stage.stage_index === selectedStageIndex.value) ?? props.stages[0] ?? null
))

watch(() => props.stages, (stages) => {
  if (!stages.some((stage) => stage.stage_index === selectedStageIndex.value)) {
    selectedStageIndex.value = stages[0]?.stage_index ?? 0
  }
}, { immediate: true })

function stageHoursLabel(stage: PathStage) {
  return stage.estimated_hours ? `约 ${stage.estimated_hours} 小时` : '时长待估算'
}

function normalizedPracticeIntensity() {
  return typeof props.practiceIntensity === 'number' ? props.practiceIntensity : 3
}

function stageGuide(stage: PathStage) {
  if (!stage.tasks.length) {
    return '该阶段暂时保持为空，说明当前目标闭包没有命中这一阶段的必要知识点。'
  }
  const intensity = normalizedPracticeIntensity()
  if (intensity >= 4) {
    return '建议按顺序学习，并优先选择代码、案例或小题完成动手验证。'
  }
  if (intensity <= 2) {
    return '建议先理解核心概念，练习可作为复盘时的可选巩固。'
  }
  return '建议按顺序完成本阶段知识点，遇到陌生概念可定位到图谱查看前置关系。'
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
.stage-focus-board {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: var(--lp-space-4);
  min-height: 430px;
}

.timeline-empty-state {
  grid-column: 1 / -1;
  padding: var(--lp-space-6);
  border: 1px dashed var(--el-border-color);
  border-radius: var(--lp-radius-lg);
  background: var(--el-fill-color-light);
  text-align: center;
}

.timeline-empty-state h3 {
  margin: 0 0 var(--lp-space-2);
  color: var(--el-text-color-primary);
}

.timeline-empty-state p {
  max-width: 560px;
  margin: 0 auto;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}

.stage-nav {
  display: flex;
  flex-direction: column;
  gap: var(--lp-space-2);
  min-height: 0;
  overflow: auto;
}

.stage-nav-item {
  display: grid;
  gap: 4px;
  width: 100%;
  padding: var(--lp-space-3);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--lp-radius-md);
  background: var(--el-fill-color-light);
  color: var(--el-text-color-regular);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.stage-nav-item:hover,
.stage-nav-item:focus-visible,
.stage-nav-item.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  box-shadow: 0 8px 18px rgb(64 158 255 / 10%);
  outline: none;
}

.stage-nav-item span,
.stage-nav-item small {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.stage-nav-item strong {
  color: var(--el-text-color-primary);
  font-size: 15px;
  line-height: 1.4;
}

.stage-detail {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  padding: var(--lp-space-4);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--lp-radius-lg);
  background: linear-gradient(135deg, var(--el-fill-color-blank), var(--el-fill-color-light));
}

.stage-detail-header {
  display: flex;
  justify-content: space-between;
  gap: var(--lp-space-4);
  align-items: flex-start;
  margin-bottom: var(--lp-space-3);
}

.stage-index {
  display: inline-flex;
  margin-bottom: 4px;
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.stage-detail h3 {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 19px;
  line-height: 1.4;
}

.stage-detail p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.stage-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: var(--lp-space-2);
}

.stage-empty-reason {
  padding: var(--lp-space-3);
  border: 1px dashed var(--el-border-color);
  border-radius: var(--lp-radius-md);
  background: var(--el-fill-color-blank);
}

.task-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--lp-space-3);
  padding-right: 2px;
}

@media (max-width: 960px) {
  .stage-focus-board {
    grid-template-columns: 1fr;
    min-height: 0;
  }

  .stage-nav {
    flex-direction: row;
    overflow-x: auto;
  }

  .stage-nav-item {
    min-width: 210px;
  }
}

@media (max-width: 768px) {
  .stage-detail-header {
    flex-direction: column;
  }

  .stage-meta {
    justify-content: flex-start;
  }
}
</style>
