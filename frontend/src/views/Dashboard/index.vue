<template>
  <PageShell
    title="学习进度"
    eyebrow="学习闭环"
    subtitle="查看当前完成情况、阶段推进和下一步学习建议。"
  >
    <template #actions>
      <el-button plain @click="router.push('/path')">查看路径</el-button>
      <el-button type="primary" @click="loadAll" :loading="loadingAll" :disabled="!projectId">刷新进度</el-button>
    </template>

    <template #summary>
      <PageSummaryBar :items="dashboardSummaryItems">
        <NextActionCard :title="nextLearningTitle" :description="nextLearningDescription">
          <el-button v-if="nextTask" size="small" type="primary" @click="handleMarkStatus(nextTask.node_id, 'start')">
            开始学习
          </el-button>
          <el-button size="small" plain @click="router.push('/path')">查看路径</el-button>
        </NextActionCard>
      </PageSummaryBar>
    </template>

    <template v-if="projectId">
      <section class="dashboard-workspace" v-loading="loadingAll" element-loading-text="加载中...">
        <aside class="stage-progress-panel lp-scroll-panel">
          <h3>阶段进度</h3>
          <article v-for="stage in stageProgressCards" :key="stage.name" class="stage-progress-card">
            <div>
              <strong>{{ stage.name }}</strong>
              <span>{{ stage.completed }}/{{ stage.total }} 个知识点</span>
            </div>
            <el-progress :percentage="stage.percent" :stroke-width="8" />
          </article>
        </aside>

        <section class="dashboard-list-panel lp-scroll-panel">
          <ProgressList
            v-if="planStore.currentPlan?.stages"
            :stages="planStore.currentPlan.stages"
            :events="trackingStore.events"
            :node-resources-map="nodeResourcesMap"
            :resources-loading="resourcesLoading"
            :resource-error="resourceError"
            @mark-status="handleMarkStatus"
          />
          <UserFriendlyEmptyState
            v-else
            description="暂无学习路径"
            hint="请先到项目页完成画像并生成学习路径，之后这里会展示阶段进度和下一步建议。"
          >
            <el-button type="primary" @click="router.push('/path')">前往路径页</el-button>
          </UserFriendlyEmptyState>
        </section>
      </section>
    </template>

    <UserFriendlyEmptyState
      v-else
      description="请先选择学习项目"
      hint="学习进度需要依附于一个项目，请先在项目页选择已有项目或创建新的学习计划。"
    >
      <el-button type="primary" @click="router.push('/project')">前往项目页</el-button>
    </UserFriendlyEmptyState>
  </PageShell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { usePlanStore } from '@/stores/plan'
import { useTrackingStore } from '@/stores/tracking'
import { resourceApi, type PlanResourcesResponse, type ResourceItem } from '@/api/modules/resource'
import PageShell from '@/components/Layout/PageShell.vue'
import PageSummaryBar from '@/components/PageSummaryBar.vue'
import NextActionCard from '@/components/NextActionCard.vue'
import UserFriendlyEmptyState from '@/components/UserFriendlyEmptyState.vue'
import ProgressList from './components/ProgressList.vue'

const router = useRouter()
const projectStore = useProjectStore()
const planStore = usePlanStore()
const trackingStore = useTrackingStore()

const loadingAll = ref(false)
const resourcesLoading = ref(false)
const resourceError = ref('')
const planResources = ref<PlanResourcesResponse | null>(null)
const projectId = computed(() => projectStore.currentProject?.id)
const nodeResourcesMap = computed<Record<string, ResourceItem[]>>(() => {
  const map: Record<string, ResourceItem[]> = {}
  for (const stage of planResources.value?.stages || []) {
    for (const node of stage.nodes || []) {
      map[node.node_id] = node.resources || []
    }
  }
  return map
})
const statusMap = computed(() => {
  const map: Record<string, string> = {}
  for (const evt of trackingStore.events) {
    if (map[evt.node_id]) continue
    map[evt.node_id] = evt.event_type === 'start' ? 'in_progress'
      : evt.event_type === 'complete' ? 'completed'
      : 'skipped'
  }
  return map
})
const allTasks = computed(() => planStore.currentPlan?.stages.flatMap((stage) => stage.tasks) ?? [])
const inProgressTask = computed(() => allTasks.value.find((task) => statusMap.value[task.node_id] === 'in_progress') ?? null)
const nextTask = computed(() => inProgressTask.value ?? allTasks.value.find((task) => !['completed', 'skipped'].includes(statusMap.value[task.node_id] || 'pending')) ?? null)
const nextTaskResourceCount = computed(() => nextTask.value ? nodeResourcesMap.value[nextTask.value.node_id]?.length || 0 : 0)
const dashboardSummaryItems = computed<Array<{ label: string; value: string; detail: string; tone: 'primary' | 'success' | 'warning' | 'danger' | 'info' }>>(() => {
  const summary = trackingStore.summary
  const completionRate = summary ? Math.round(summary.completion_rate * 100) : 0
  return [
    {
      label: '总体完成率',
      value: `${completionRate}%`,
      detail: summary ? `${summary.completed}/${summary.total_nodes} 个知识点已完成` : '暂无进度数据',
      tone: completionRate >= 70 ? 'success' : completionRate >= 30 ? 'warning' : 'info',
    },
    {
      label: '学习中',
      value: `${summary?.in_progress ?? 0} 个`,
      detail: inProgressTask.value?.name || '还没有正在学习的知识点',
      tone: inProgressTask.value ? 'primary' : 'info',
    },
    {
      label: '待学习',
      value: `${summary?.pending ?? allTasks.value.length} 个`,
      detail: nextTask.value ? `下一项：${nextTask.value.name}` : '当前没有待学习节点',
      tone: 'info',
    },
    {
      label: '已跳过',
      value: `${summary?.skipped ?? 0} 个`,
      detail: summary?.skipped ? '可在路径页触发进度感知重规划' : '暂未跳过知识点',
      tone: summary?.skipped ? 'warning' : 'success',
    },
  ]
})
const stageProgressCards = computed(() => (planStore.currentPlan?.stages ?? []).map((stage) => {
  const total = stage.tasks.length
  const completed = stage.tasks.filter((task) => statusMap.value[task.node_id] === 'completed').length
  return {
    name: stage.stage_name,
    total,
    completed,
    percent: total ? Math.round((completed / total) * 100) : 0,
  }
}))
const nextLearningTitle = computed(() => {
  if (!projectId.value) return '先选择学习项目'
  if (!planStore.currentPlan) return '先生成学习路径'
  if (!nextTask.value) return '当前路径已无待学习项'
  return inProgressTask.value ? `继续学习「${nextTask.value.name}」` : `开始学习「${nextTask.value.name}」`
})
const nextLearningDescription = computed(() => {
  if (!projectId.value) return '学习进度需要依附于项目，先去项目页选择或创建学习计划。'
  if (!planStore.currentPlan) return '生成路径后，这里会自动给出下一步学习建议。'
  if (!nextTask.value) return '可以回顾路径解释，或根据学习结果进行重规划。'
  return nextTaskResourceCount.value
    ? `当前知识点已有 ${nextTaskResourceCount.value} 条绑定资料，可先阅读资料再记录进度。`
    : '当前知识点暂无绑定资料，也可以先开始学习，之后在路径页补充资源。'
})

async function loadAll() {
  if (!projectId.value) return
  loadingAll.value = true
  trackingStore.summary = null
  trackingStore.events = []
  planResources.value = null
  resourceError.value = ''
  try {
    const results = await Promise.allSettled([
      trackingStore.loadSummary(projectId.value),
      trackingStore.loadEvents(projectId.value),
      planStore.loadLatest(projectId.value),
    ])
    for (const r of results) {
      if (r.status === 'rejected' && r.reason?.response?.status !== 404) {
        console.warn('Dashboard load error:', r.reason)
      }
    }
    await loadPlanResources()
  } finally {
    loadingAll.value = false
  }
}

onMounted(() => loadAll())

watch(projectId, () => loadAll())

async function loadPlanResources() {
  const currentProjectId = projectId.value
  const pathId = planStore.currentPlan?.id
  if (!currentProjectId || !pathId) {
    planResources.value = null
    return
  }
  resourcesLoading.value = true
  resourceError.value = ''
  try {
    planResources.value = await resourceApi.getPlanResources(currentProjectId, pathId)
  } catch (e: any) {
    resourceError.value = e?.response?.data?.error || '资源加载失败'
    planResources.value = null
    console.warn('Dashboard resource load error:', e)
  } finally {
    resourcesLoading.value = false
  }
}

async function handleMarkStatus(nodeId: string, eventType: 'start' | 'complete' | 'skip') {
  if (!projectId.value) return
  await trackingStore.addEvent(projectId.value, { node_id: nodeId, event_type: eventType })
  await Promise.allSettled([
    trackingStore.loadSummary(projectId.value),
    trackingStore.loadEvents(projectId.value),
  ])
}
</script>

<style scoped>
.dashboard-workspace {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: var(--lp-space-4);
  height: calc(100vh - var(--lp-header-height) - 228px);
  min-height: 440px;
}

.stage-progress-panel,
.dashboard-list-panel {
  min-width: 0;
  padding: var(--lp-space-4);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--lp-radius-lg);
  background: var(--el-fill-color-blank);
}

.stage-progress-panel h3 {
  margin: 0 0 var(--lp-space-3);
  color: var(--el-text-color-primary);
  font-size: 16px;
}

.stage-progress-card {
  display: grid;
  gap: var(--lp-space-2);
  padding: var(--lp-space-3);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--lp-radius-md);
  background: var(--el-fill-color-light);
}

.stage-progress-card + .stage-progress-card {
  margin-top: var(--lp-space-2);
}

.stage-progress-card div {
  display: flex;
  justify-content: space-between;
  gap: var(--lp-space-2);
  align-items: center;
}

.stage-progress-card strong {
  color: var(--el-text-color-primary);
  font-size: 14px;
}

.stage-progress-card span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

@media (max-width: 960px) {
  .dashboard-workspace {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 0;
  }

  .stage-progress-panel,
  .dashboard-list-panel {
    overflow: visible;
  }
}
</style>
