<template>
  <div class="page-container">
    <!-- 有项目时 -->
    <template v-if="projectId">
      <!-- 进度概览 -->
      <el-card shadow="never" style="margin-bottom: 20px">
        <template #header><span>学习进度</span></template>
        <StatsOverview :summary="trackingStore.summary" />
      </el-card>

      <!-- 节点列表 -->
      <el-card shadow="never" v-loading="loadingAll" element-loading-text="加载中...">
        <template #header><span>知识点进度</span></template>
        <ProgressList
          v-if="planStore.currentPlan?.stages"
          :stages="planStore.currentPlan.stages"
          :events="trackingStore.events"
          @mark-status="handleMarkStatus"
        />
        <el-empty v-else description="暂无学习路径，请先生成路径">
          <el-button type="primary" @click="router.push('/path')">前往路径页</el-button>
        </el-empty>
      </el-card>
    </template>

    <!-- 无项目提示 -->
    <el-card v-else shadow="never">
      <el-empty description="请先在项目页面选择一个项目">
        <template #image>
          <el-icon :size="60" color="#E6A23C"><DataAnalysis /></el-icon>
        </template>
        <el-button type="primary" @click="router.push('/project')">前往项目页</el-button>
      </el-empty>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { DataAnalysis } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import { usePlanStore } from '@/stores/plan'
import { useTrackingStore } from '@/stores/tracking'
import StatsOverview from './components/StatsOverview.vue'
import ProgressList from './components/ProgressList.vue'

const router = useRouter()
const projectStore = useProjectStore()
const planStore = usePlanStore()
const trackingStore = useTrackingStore()

const loadingAll = ref(false)
const projectId = computed(() => projectStore.currentProject?.id)

async function loadAll() {
  if (!projectId.value) return
  loadingAll.value = true
  trackingStore.summary = null
  trackingStore.events = []
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
  } finally {
    loadingAll.value = false
  }
}

onMounted(() => loadAll())

watch(projectId, () => loadAll())

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
.page-container { padding: 20px; }
</style>
