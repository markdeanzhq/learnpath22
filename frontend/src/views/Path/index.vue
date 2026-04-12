<template>
  <div class="page-container">
    <!-- 路径概览 -->
    <el-card shadow="never" v-if="planStore.currentPlan" style="margin-bottom: 20px">
      <template #header>
        <div class="card-header">
          <span>学习路径</span>
          <div class="header-actions">
            <el-tag>v{{ planStore.currentPlan.version }}</el-tag>
            <el-tag :type="budgetTagType">
              {{ budgetLabel }}
            </el-tag>
            <el-tag type="info">
              {{ planStore.currentPlan.stages.reduce((sum, s) => sum + s.tasks.length, 0) }} 个知识点
            </el-tag>
            <el-tag v-if="planStore.currentPlan.total_hours" type="info">
              共 {{ planStore.currentPlan.total_hours }} 小时
            </el-tag>
            <el-dropdown trigger="click" @command="handleReplan" style="margin-left: 8px">
              <el-button size="small" :loading="planStore.loading">重规划</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="progress_aware">进度感知（保留已完成）</el-dropdown-item>
                  <el-dropdown-item command="profile_update">画像更新（全量重生成）</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="路径总览" name="timeline">
          <StageTimeline :stages="planStore.currentPlan.stages" />
        </el-tab-pane>
        <el-tab-pane label="规划解释" name="explanation">
          <Explanation :explanation="explanation" />
        </el-tab-pane>
        <el-tab-pane label="变更对比" name="diff" v-if="planStore.lastReplanResult?.diff">
          <div class="diff-section">
            <el-tag type="info" style="margin-bottom: 12px">
              模式: {{ planStore.lastReplanResult.mode === 'progress_aware' ? '进度感知' : '画像更新' }}
            </el-tag>
            <template v-if="planStore.lastReplanResult.diff.added">
              <h4>新增节点</h4>
              <el-tag v-for="nid in planStore.lastReplanResult.diff.added" :key="nid" type="success" style="margin: 0 4px 4px 0">{{ nid }}</el-tag>
            </template>
            <template v-if="planStore.lastReplanResult.diff.removed">
              <h4>移除节点</h4>
              <el-tag v-for="nid in planStore.lastReplanResult.diff.removed" :key="nid" type="danger" style="margin: 0 4px 4px 0">{{ nid }}</el-tag>
            </template>
            <template v-if="planStore.lastReplanResult.diff.unchanged">
              <h4>保持不变</h4>
              <el-tag v-for="nid in planStore.lastReplanResult.diff.unchanged" :key="nid" type="info" style="margin: 0 4px 4px 0">{{ nid }}</el-tag>
            </template>
            <template v-if="planStore.lastReplanResult.diff.completed">
              <h4>已完成（锁定）</h4>
              <el-tag v-for="nid in planStore.lastReplanResult.diff.completed" :key="nid" type="success" style="margin: 0 4px 4px 0">{{ nid }}</el-tag>
            </template>
            <template v-if="planStore.lastReplanResult.diff.pending">
              <h4>待重规划</h4>
              <el-tag v-for="nid in planStore.lastReplanResult.diff.pending" :key="nid" type="warning" style="margin: 0 4px 4px 0">{{ nid }}</el-tag>
            </template>
          </div>
        </el-tab-pane>
        <el-tab-pane label="搜索资料" name="search">
          <div class="search-section">
            <el-input
              v-model="searchQuery"
              placeholder="输入关键词搜索学习资料..."
              @keyup.enter="doSearch"
              style="margin-bottom: 16px"
            >
              <template #append>
                <el-button @click="doSearch" :loading="searching">搜索</el-button>
              </template>
            </el-input>
            <el-table :data="searchResults" v-if="searchResults.length" size="small" stripe>
              <el-table-column label="标题" min-width="200">
                <template #default="{ row }">
                  <a :href="row.url" target="_blank" rel="noopener" class="search-link">{{ row.title }}</a>
                </template>
              </el-table-column>
              <el-table-column prop="snippet" label="摘要" min-width="300" show-overflow-tooltip />
              <el-table-column label="相关度" width="80">
                <template #default="{ row }">{{ (row.score * 100).toFixed(0) }}%</template>
              </el-table-column>
            </el-table>
            <el-empty v-else-if="searchDone" description="未找到相关资料" />
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 加载中 -->
    <el-card v-else-if="planStore.loading" shadow="never">
      <div v-loading="true" style="height: 200px" element-loading-text="正在加载学习路径..." />
    </el-card>

    <!-- 暂无路径 -->
    <el-card v-else-if="projectId && !loadError" shadow="never">
      <el-empty description="暂无学习路径，请先生成">
        <template #image>
          <el-icon :size="60" color="#67C23A"><Guide /></el-icon>
        </template>
        <el-button type="primary" @click="router.push('/project')">前往项目页</el-button>
      </el-empty>
    </el-card>

    <!-- 加载失败 -->
    <el-card v-else-if="loadError" shadow="never">
      <el-result icon="warning" title="加载失败" :sub-title="loadError">
        <template #extra>
          <el-button type="primary" @click="loadPath">重试</el-button>
        </template>
      </el-result>
    </el-card>

    <!-- 无项目 -->
    <el-card v-else shadow="never">
      <el-empty description="请先在项目页面选择一个项目">
        <template #image>
          <el-icon :size="60" color="#409EFF"><Guide /></el-icon>
        </template>
        <el-button type="primary" @click="router.push('/project')">前往项目页</el-button>
      </el-empty>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Guide } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import { usePlanStore } from '@/stores/plan'
import { planApi, type ExplanationResponse } from '@/api/modules/plan'
import { searchApi, type SearchResultItem } from '@/api/modules/search'
import StageTimeline from './components/StageTimeline.vue'
import Explanation from './Explanation.vue'

const router = useRouter()
const projectStore = useProjectStore()
const planStore = usePlanStore()

const activeTab = ref('timeline')
const loadError = ref('')
const projectId = computed(() => projectStore.currentProject?.id)
const explanation = ref<ExplanationResponse | null>(null)
const searchQuery = ref('')
const searchResults = ref<SearchResultItem[]>([])
const searching = ref(false)
const searchDone = ref(false)

async function loadPath() {
  if (!projectId.value) return
  loadError.value = ''
  planStore.currentPlan = null
  explanation.value = null
  try {
    await planStore.loadLatest(projectId.value)
    explanation.value = await planApi.getExplanation(projectId.value)
  } catch (e: any) {
    if (e?.response?.status !== 404) {
      loadError.value = e?.response?.data?.error || '加载路径失败'
    }
  }
}

onMounted(() => loadPath())

watch(projectId, () => loadPath())

async function handleReplan(mode: string) {
  if (!projectId.value) return
  try {
    await planStore.replan(projectId.value, mode as 'progress_aware' | 'profile_update')
    activeTab.value = 'diff'
    ElMessage.success('重规划完成')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '重规划失败')
  }
}

async function doSearch() {
  if (!projectId.value || !searchQuery.value.trim()) return
  searching.value = true
  searchDone.value = false
  try {
    const data = await searchApi.search(projectId.value, searchQuery.value)
    searchResults.value = data.results ?? []
    searchDone.value = true
  } catch (e: any) {
    ElMessage.error('搜索失败')
  } finally {
    searching.value = false
  }
}

const budgetTagType = computed(() => {
  const status = planStore.currentPlan?.budget_status
  if (status === 'feasible') return 'success'
  if (status === 'tight') return 'warning'
  return 'danger'
})

const budgetLabel = computed(() => {
  const status = planStore.currentPlan?.budget_status
  if (status === 'feasible') return '时间充裕'
  if (status === 'tight') return '时间紧张'
  if (status === 'insufficient') return '时间不足'
  return status ?? '未知'
})
</script>

<style scoped>
.page-container { padding: 20px; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.diff-section h4 {
  margin: 12px 0 8px 0;
  font-size: 14px;
  color: #303133;
}
.search-link {
  color: #409EFF;
  text-decoration: none;
}
.search-link:hover {
  text-decoration: underline;
}

@media (max-width: 768px) {
  .page-container {
    padding: 12px;
  }

  .card-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }

  .header-actions {
    width: 100%;
  }

  :deep(.el-tabs__nav) {
    flex-wrap: wrap;
  }
}
</style>