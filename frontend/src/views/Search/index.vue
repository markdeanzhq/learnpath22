<template>
  <PageShell
    title="项目资料库"
    eyebrow="资料增强"
    subtitle="搜索、保存并回看当前项目资料；需要进入图谱时再加入扩展草稿。"
  >
    <template #actions>
      <el-button plain @click="router.push('/settings')">搜索设置</el-button>
      <el-button @click="reloadSearchConfig" :loading="configChecking">重新检查</el-button>
    </template>

    <template #summary>
      <PageSummaryBar :items="searchSummaryItems">
        <NextActionCard :title="nextActionTitle" :description="nextActionDescription">
          <el-button v-if="!projectId" size="small" type="primary" @click="router.push('/project')">
            选择项目
          </el-button>
          <el-button v-else-if="!searchReady" size="small" type="primary" @click="router.push('/settings')">
            前往设置
          </el-button>
          <el-button
            v-else
            size="small"
            type="primary"
            :loading="searching"
            :disabled="!searchQuery.trim()"
            @click="doSearch"
          >
            搜索资料
          </el-button>
        </NextActionCard>
      </PageSummaryBar>
    </template>

    <template v-if="projectId">
      <el-alert
        v-if="configMissing || readinessWarning || searchError"
        class="search-alert"
        :title="searchError || readinessWarning || '搜索能力待配置'"
        :type="configMissing || readinessWarning ? 'warning' : 'error'"
        show-icon
        :closable="false"
      >
        <template #default>
          <template v-if="configMissing">
            项目资料库搜索属于在线增强能力。请先到设置页填写搜索 API Key；这不会影响学习路径规划主链演示。
            <el-button link type="primary" @click="router.push('/settings')">前往设置</el-button>
          </template>
          <template v-else-if="readinessWarning">
            当前仅搜索增强能力检查未通过；请检查设置页中的搜索配置后重新检查。学习路径规划主链仍可单独演示。
            <el-button link type="primary" @click="reloadSearchConfig">重新检查</el-button>
            <el-button link type="primary" @click="router.push('/settings')">前往设置</el-button>
          </template>
          <template v-else>
            资料搜索依赖外部在线服务；请检查设置页中的搜索配置或稍后重试。搜索异常不代表系统主链不可用。
            <el-button link type="primary" @click="reloadSearchConfig">重新检查</el-button>
          </template>
        </template>
      </el-alert>

      <section class="resource-workspace">
        <main class="resource-search-panel">
          <header class="panel-heading">
            <div>
              <h3>搜索与本次结果</h3>
              <p>先查找资料，再决定是否保存为图谱扩展草稿来源。</p>
            </div>
          </header>

          <el-input
            v-model="searchQuery"
            class="resource-search-input"
            placeholder="输入学习目标、知识点或资料关键词..."
            clearable
            @keyup.enter="doSearch"
          >
            <template #append>
              <el-button @click="doSearch" :loading="searching" :disabled="!searchReady || !searchQuery.trim()">搜索</el-button>
            </template>
          </el-input>

          <section class="resource-route-hints" aria-label="资料去向提示">
            <article>
              <strong>留在资料库</strong>
              <span>保存搜索历史，便于后续回看和复用。</span>
            </article>
            <article>
              <strong>绑定到路径</strong>
              <span>在路径页把资料绑定到阶段或知识点。</span>
            </article>
            <article>
              <strong>加入扩展草稿</strong>
              <span>在图谱页人工审核后才可能进入规划。</span>
            </article>
          </section>

          <div class="results-table-wrap lp-scroll-panel">
            <el-table v-if="searchResults.length" :data="searchResults" size="small" stripe>
              <el-table-column label="标题" min-width="220">
                <template #default="{ row }">
                  <a v-if="safeExternalUrl(row.url)" :href="safeExternalUrl(row.url)" target="_blank" rel="noopener" class="search-link">{{ row.title }}</a>
                  <span v-else>{{ row.title }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="snippet" label="摘要" min-width="320" show-overflow-tooltip />
              <el-table-column label="相关度" width="90">
                <template #default="{ row }">{{ (row.score * 100).toFixed(0) }}%</template>
              </el-table-column>
              <el-table-column label="图谱扩展" width="130">
                <template #default="{ row, $index }">
                  <el-button link type="primary" :loading="overlayAddingUrl === row.url" @click="addResultToOverlay(row, $index)">
                    加入草稿
                  </el-button>
                </template>
              </el-table-column>
            </el-table>

            <UserFriendlyEmptyState
              v-else-if="searchDone"
              description="未找到相关资料"
              hint="可以换一个更具体的知识点、算法名称或学习目标再试一次。"
            />
            <UserFriendlyEmptyState
              v-else
              description="还没有本次搜索结果"
              hint="输入关键词后，结果会显示在这里；已保存资料在右侧回看。"
            />
          </div>
        </main>

        <aside class="saved-resource-panel lp-scroll-panel">
          <header class="panel-heading compact">
            <div>
              <h3>已保存资料</h3>
              <p>保留搜索历史，并标记是否已加入图谱扩展草稿。</p>
            </div>
          </header>

          <el-table v-if="persistedResults.length" :data="persistedResults" size="small" stripe>
            <el-table-column label="标题" min-width="220">
              <template #default="{ row }">
                <a v-if="safeExternalUrl(row.url)" :href="safeExternalUrl(row.url)" target="_blank" rel="noopener" class="search-link">{{ row.title }}</a>
                <span v-else>{{ row.title }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="query" label="搜索词" width="130" show-overflow-tooltip />
            <el-table-column label="状态" width="116">
              <template #default="{ row }">
                <el-tag v-if="row.source_id" type="success" size="small">已加入</el-tag>
                <el-button v-else link type="primary" :loading="overlayAddingResultId === row.result_id" @click="bridgePersistedResult(row)">
                  加入草稿
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <UserFriendlyEmptyState
            v-else
            description="暂无已保存资料"
            hint="完成一次搜索后，资料会自动保留在这里，便于后续绑定或审核。"
          />
        </aside>
      </section>
    </template>

    <UserFriendlyEmptyState
      v-else
      description="请先选择学习项目"
      hint="资料库按项目保存搜索历史和图谱扩展草稿来源。"
    >
      <el-button type="primary" @click="router.push('/project')">前往项目页</el-button>
    </UserFriendlyEmptyState>
  </PageShell>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus/es/components/message/index'
import { healthApi } from '@/api/modules/health'
import { searchApi, type PersistedSearchResult, type SearchResultItem } from '@/api/modules/search'
import { safeExternalUrl } from '@/utils/url'
import { useProjectStore } from '@/stores/project'
import PageShell from '@/components/Layout/PageShell.vue'
import PageSummaryBar from '@/components/PageSummaryBar.vue'
import NextActionCard from '@/components/NextActionCard.vue'
import UserFriendlyEmptyState from '@/components/UserFriendlyEmptyState.vue'

type SummaryTone = 'primary' | 'success' | 'warning' | 'danger' | 'info'

const router = useRouter()
const projectStore = useProjectStore()

const projectId = computed(() => projectStore.currentProject?.id)
const searchQuery = ref('')
const searchResults = ref<SearchResultItem[]>([])
const persistedResults = ref<PersistedSearchResult[]>([])
const searching = ref(false)
const searchDone = ref(false)
const configChecking = ref(false)
const configMissing = ref(false)
const readinessWarning = ref('')
const searchError = ref('')
const overlayAddingUrl = ref('')
const overlayAddingResultId = ref('')
const searchReady = computed(() => Boolean(projectId.value) && !configMissing.value && !readinessWarning.value)
const searchStatusLabel = computed(() => {
  if (!projectId.value) return '待选择项目'
  if (configMissing.value) return '待配置'
  if (readinessWarning.value) return '需检查'
  return '可搜索'
})
const searchStatusTone = computed<SummaryTone>(() => {
  if (!projectId.value) return 'info'
  if (configMissing.value || readinessWarning.value) return 'warning'
  return 'success'
})
const searchSummaryItems = computed<Array<{ label: string; value: string; detail: string; tone: SummaryTone }>>(() => [
  {
    label: '当前项目',
    value: projectStore.currentProject?.title || '未选择',
    detail: projectStore.currentProject?.goal_text || '选择项目后保存资料',
    tone: projectStore.currentProject ? 'primary' : 'info',
  },
  {
    label: '搜索能力',
    value: searchStatusLabel.value,
    detail: configMissing.value ? '在线增强未配置，不影响主链' : readinessWarning.value || '可以搜索并保存资料',
    tone: searchStatusTone.value,
  },
  {
    label: '本次结果',
    value: `${searchResults.value.length} 条`,
    detail: searchDone.value ? '可加入图谱扩展草稿' : '输入关键词后展示',
    tone: searchResults.value.length ? 'success' : 'info',
  },
  {
    label: '已保存',
    value: `${persistedResults.value.length} 条`,
    detail: persistedResults.value.length ? '可复用、绑定或审核' : '搜索后自动保留历史',
    tone: persistedResults.value.length ? 'primary' : 'info',
  },
])
const nextActionTitle = computed(() => {
  if (!projectId.value) return '先选择学习项目'
  if (!searchReady.value) return '先检查搜索增强配置'
  if (searchResults.value.length) return '筛选可用资料加入草稿'
  return '输入关键词搜索资料'
})
const nextActionDescription = computed(() => {
  if (!projectId.value) return '资料库需要依附具体项目，方便保存搜索历史和扩展草稿来源。'
  if (!searchReady.value) return '搜索是在线增强能力，未配置时不影响路径规划主链。'
  if (searchResults.value.length) return '高相关资料可以加入图谱扩展草稿，审核后再决定是否进入规划。'
  return '建议搜索目标知识点、算法名或当前阶段遇到的问题。'
})

onMounted(async () => {
  await loadSearchConfig()
  await loadPersistedResults()
})

watch(projectId, async (nextProjectId, previousProjectId) => {
  if (nextProjectId === previousProjectId) return
  searchResults.value = []
  persistedResults.value = []
  searchDone.value = false
  searchError.value = ''
  overlayAddingUrl.value = ''
  overlayAddingResultId.value = ''
  if (nextProjectId) {
    await loadPersistedResults()
  }
})

async function loadSearchConfig() {
  configChecking.value = true
  try {
    const [config, readiness] = await Promise.all([
      healthApi.getConfigSilently(),
      healthApi.getSearchReadiness(),
    ])
    configMissing.value = !config.search_api_key_set
    readinessWarning.value = readiness.ready ? '' : (readiness.reason || '搜索增强能力检查未通过')
    if (!configMissing.value && searchError.value === '搜索服务未配置') {
      searchError.value = ''
    }
  } catch {
    configMissing.value = false
    readinessWarning.value = '搜索能力检查失败，请稍后重试'
  } finally {
    configChecking.value = false
  }
}

async function reloadSearchConfig() {
  await loadSearchConfig()
}

async function loadPersistedResults() {
  if (!projectId.value) {
    persistedResults.value = []
    return
  }
  persistedResults.value = await searchApi.listPersistedResults(projectId.value)
}

async function doSearch() {
  if (!projectId.value || !searchQuery.value.trim() || !searchReady.value) return
  searching.value = true
  searchDone.value = false
  searchResults.value = []
  searchError.value = ''
  try {
    const data = await searchApi.search(projectId.value, searchQuery.value)
    searchResults.value = data.results ?? []
    searchDone.value = true
  } catch (e: any) {
    const message = e?.response?.data?.error || '搜索失败'
    searchError.value = message
    if (message === '搜索服务未配置') {
      configMissing.value = true
    }
  } finally {
    searching.value = false
  }
}

async function bridgePersistedResult(result: PersistedSearchResult) {
  if (!projectId.value) return
  overlayAddingResultId.value = result.result_id
  try {
    const bridged = await searchApi.bridgeOverlaySources(projectId.value, [result.result_id])
    const sourceId = bridged.source_ids[0]
    result.source_id = sourceId
    ElMessage.success(bridged.results[0]?.reused ? '已复用图谱扩展草稿来源' : '已加入图谱扩展草稿')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '加入图谱扩展草稿失败')
  } finally {
    overlayAddingResultId.value = ''
  }
}

async function addResultToOverlay(row: SearchResultItem, index: number) {
  if (!projectId.value) return
  overlayAddingUrl.value = row.url
  try {
    const saved = await searchApi.persistResult(projectId.value, {
      query: searchQuery.value,
      provider: row.provider || 'tavily',
      url: row.url,
      title: row.title,
      snippet: row.snippet,
      result_rank: index + 1,
      is_selected: true,
    })
    await bridgePersistedResult(saved)
    await loadPersistedResults()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '保存搜索结果失败')
  } finally {
    overlayAddingUrl.value = ''
  }
}
</script>

<style scoped>
.search-alert {
  margin-bottom: var(--lp-space-3);
}

.resource-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(340px, 0.9fr);
  gap: var(--lp-space-4);
  height: calc(100vh - var(--lp-header-height) - 230px);
  min-height: 440px;
}

.resource-search-panel,
.saved-resource-panel {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  padding: var(--lp-space-4);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--lp-radius-lg);
  background: var(--el-fill-color-blank);
}

.panel-heading {
  display: flex;
  justify-content: space-between;
  gap: var(--lp-space-3);
  align-items: flex-start;
  margin-bottom: var(--lp-space-3);
}

.panel-heading.compact {
  margin-bottom: var(--lp-space-2);
}

.panel-heading h3 {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 16px;
}

.panel-heading p {
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.resource-search-input {
  margin-bottom: var(--lp-space-3);
}

.resource-route-hints {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--lp-space-2);
  margin-bottom: var(--lp-space-3);
}

.resource-route-hints article {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding: var(--lp-space-2);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--lp-radius-md);
  background: var(--el-fill-color-light);
}

.resource-route-hints strong {
  color: var(--el-text-color-primary);
  font-size: 13px;
}

.resource-route-hints span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.results-table-wrap {
  flex: 1;
  min-height: 0;
}

.search-link {
  color: var(--el-color-primary);
  text-decoration: none;
}

.search-link:hover {
  text-decoration: underline;
}

@media (max-width: 960px) {
  .resource-workspace {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 0;
  }

  .resource-route-hints {
    grid-template-columns: 1fr;
  }

  .saved-resource-panel {
    overflow: visible;
  }
}
</style>
