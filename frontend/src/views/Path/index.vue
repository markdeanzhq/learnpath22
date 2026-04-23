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
          <Explanation :explanation="explanation" @polish-change="reloadExplanation" />
        </el-tab-pane>
        <el-tab-pane label="推荐资源" name="resources">
          <div class="resources-section">
            <div class="resources-actions">
              <el-alert
                title="路径生成后可按阶段自动补充候选资源；静态资源用于离线保底，Tavily 结果属于在线增强。"
                type="info"
                :closable="false"
                show-icon
              />
              <el-button type="primary" @click="recommendResources" :loading="recommendLoading">
                自动补充阶段资源
              </el-button>
            </div>
            <div v-loading="resourcesLoading" element-loading-text="正在加载推荐资源...">
              <template v-if="planResources?.stages?.length">
                <el-collapse>
                  <el-collapse-item
                    v-for="stage in planResources.stages"
                    :key="stage.stage_name"
                    :title="`${stage.stage_name}（${stage.resources.length} 条）`"
                    :name="stage.stage_name"
                  >
                    <el-empty v-if="!stage.resources.length" description="当前阶段暂无资源，可点击上方按钮自动补充" />
                    <el-card v-for="item in stage.resources" :key="item.id" shadow="never" class="resource-card">
                      <div class="resource-card__header">
                        <a v-if="item.url" :href="item.url" target="_blank" rel="noopener" class="search-link">{{ item.title }}</a>
                        <span v-else class="resource-title">{{ item.title }}</span>
                        <el-tag size="small" :type="item.source_type === 'static' ? 'info' : item.source_type === 'manual' ? 'success' : 'warning'">
                          {{ item.source_type === 'static' ? '静态保底' : item.source_type === 'manual' ? '手动绑定' : '在线增强' }}
                        </el-tag>
                      </div>
                      <div class="resource-snippet">{{ item.snippet || '暂无摘要' }}</div>
                      <div class="resource-meta" v-if="item.score != null">相关度：{{ (item.score * 100).toFixed(0) }}%</div>
                    </el-card>
                  </el-collapse-item>
                </el-collapse>
              </template>
              <el-empty v-else description="暂无推荐资源，可点击上方按钮自动补充" />
            </div>
          </div>
        </el-tab-pane>
        <el-tab-pane label="变更对比" name="diff" v-if="planStore.lastReplanResult?.diff">
          <div class="diff-section">
            <el-tag type="info" style="margin-bottom: 12px">
              模式: {{ planStore.lastReplanResult.mode === 'progress_aware' ? '进度感知' : '画像更新' }}
            </el-tag>
            <template v-if="replanDiffDetails.added?.length">
              <h4>新增节点</h4>
              <el-tag v-for="item in replanDiffDetails.added" :key="item.node_id" type="success" style="margin: 0 4px 4px 0">{{ item.node_name }}</el-tag>
            </template>
            <template v-if="replanDiffDetails.removed?.length">
              <h4>移除节点</h4>
              <el-tag v-for="item in replanDiffDetails.removed" :key="item.node_id" type="danger" style="margin: 0 4px 4px 0">{{ item.node_name }}</el-tag>
            </template>
            <template v-if="replanDiffDetails.unchanged?.length">
              <h4>保持不变</h4>
              <el-tag v-for="item in replanDiffDetails.unchanged" :key="item.node_id" type="info" style="margin: 0 4px 4px 0">{{ item.node_name }}</el-tag>
            </template>
            <template v-if="replanDiffDetails.completed?.length">
              <h4>已完成（锁定）</h4>
              <el-tag v-for="item in replanDiffDetails.completed" :key="item.node_id" type="success" style="margin: 0 4px 4px 0">{{ item.node_name }}</el-tag>
            </template>
            <template v-if="replanDiffDetails.pending?.length">
              <h4>待重规划</h4>
              <el-tag v-for="item in replanDiffDetails.pending" :key="item.node_id" type="warning" style="margin: 0 4px 4px 0">{{ item.node_name }}</el-tag>
            </template>
            <template v-if="replanDiffDetails.skipped?.length">
              <h4>已跳过</h4>
              <el-tag v-for="item in replanDiffDetails.skipped" :key="item.node_id" type="warning" effect="plain" style="margin: 0 4px 4px 0">{{ item.node_name }}</el-tag>
            </template>
          </div>
        </el-tab-pane>
        <el-tab-pane label="搜索资料" name="search">
          <div class="search-section">
            <div class="search-toolbar">
              <el-input
                v-model="searchQuery"
                placeholder="输入关键词搜索学习资料..."
                @keyup.enter="doSearch"
              >
                <template #append>
                  <el-button @click="doSearch" :loading="searching">搜索</el-button>
                </template>
              </el-input>
              <el-select v-model="selectedStageName" placeholder="选择绑定阶段" style="width: 220px">
                <el-option
                  v-for="stage in stageOptions"
                  :key="stage.stage_name"
                  :label="stage.stage_name"
                  :value="stage.stage_name"
                />
              </el-select>
            </div>
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
              <el-table-column label="操作" width="130">
                <template #default="{ row }">
                  <el-button link type="primary" :loading="bindLoading" @click="bindSearchResultToStage(row)">
                    绑定到阶段
                  </el-button>
                </template>
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
import { resourceApi, type PlanResourcesResponse } from '@/api/modules/resource'
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
const planResources = ref<PlanResourcesResponse | null>(null)
const resourcesLoading = ref(false)
const recommendLoading = ref(false)
const bindLoading = ref(false)
const selectedStageName = ref('')

async function loadPlanResources() {
  if (!projectId.value || !planStore.currentPlan?.id) {
    planResources.value = null
    return
  }
  resourcesLoading.value = true
  try {
    planResources.value = await resourceApi.getPlanResources(projectId.value, planStore.currentPlan.id)
    if (!selectedStageName.value) {
      selectedStageName.value = planStore.currentPlan.stages[0]?.stage_name || ''
    }
  } catch {
    planResources.value = null
  } finally {
    resourcesLoading.value = false
  }
}

async function loadPath() {
  if (!projectId.value) return
  loadError.value = ''
  planStore.currentPlan = null
  explanation.value = null
  planResources.value = null
  try {
    await planStore.loadLatest(projectId.value)
    explanation.value = await planApi.getExplanation(projectId.value)
    await loadPlanResources()
  } catch (e: any) {
    if (e?.response?.status !== 404) {
      loadError.value = e?.response?.data?.error || '加载路径失败'
    }
  }
}

async function reloadExplanation(polish: boolean) {
  if (!projectId.value) return
  try {
    explanation.value = await planApi.getExplanation(projectId.value, polish)
  } catch (e: any) {
    if (e?.response?.status !== 404) {
      loadError.value = e?.response?.data?.error || '加载解释失败'
    }
  }
}

onMounted(() => loadPath())

watch(projectId, () => loadPath())

async function handleReplan(mode: string) {
  if (!projectId.value) return
  try {
    await planStore.replan(projectId.value, mode as 'progress_aware' | 'profile_update')
    await loadPlanResources()
    activeTab.value = 'diff'
    ElMessage.success('重规划完成')
  } catch (e: any) {
    if (e?.response?.status === 409 && e?.response?.data?.error === 'GOAL_TARGETS_REMOVED') {
      router.push({
        path: '/project',
        query: {
          mode: 'reconfirm',
          projectId: projectId.value,
          reason: 'goal-targets-removed',
        },
      })
      return
    }
    ElMessage.error(e?.response?.data?.error || '重规划失败')
  }
}

async function recommendResources() {
  if (!projectId.value || !planStore.currentPlan?.id) return
  recommendLoading.value = true
  try {
    planResources.value = await resourceApi.recommendPlanResources(projectId.value, planStore.currentPlan.id)
    activeTab.value = 'resources'
    ElMessage.success('已为当前路径补充阶段资源')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '自动补充资源失败')
  } finally {
    recommendLoading.value = false
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

async function bindSearchResultToStage(row: SearchResultItem) {
  if (!projectId.value || !planStore.currentPlan?.id || !selectedStageName.value) {
    ElMessage.warning('请先选择目标阶段')
    return
  }
  bindLoading.value = true
  try {
    await resourceApi.bindManualResource(projectId.value, planStore.currentPlan.id, {
      stage_name: selectedStageName.value,
      title: row.title,
      url: row.url,
      snippet: row.snippet,
    })
    await loadPlanResources()
    activeTab.value = 'resources'
    ElMessage.success('已绑定到当前阶段')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '绑定资源失败')
  } finally {
    bindLoading.value = false
  }
}

const replanDiffDetails = computed(() => planStore.lastReplanResult?.diff_details ?? {})

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

const stageOptions = computed(() => planStore.currentPlan?.stages ?? [])
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
.search-toolbar,
.resources-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.resource-card {
  margin-bottom: 12px;
}
.resource-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
.resource-title,
.search-link {
  color: #409EFF;
  text-decoration: none;
  font-weight: 500;
}
.search-link:hover {
  text-decoration: underline;
}
.resource-snippet {
  color: #606266;
  line-height: 1.6;
}
.resource-meta {
  color: #909399;
  font-size: 12px;
  margin-top: 8px;
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

  .search-toolbar,
  .resources-actions,
  .resource-card__header {
    flex-direction: column;
    align-items: stretch;
  }

  :deep(.el-tabs__nav) {
    flex-wrap: wrap;
  }
}
</style>