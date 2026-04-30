<template>
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <div class="page-title">项目资料库</div>
            <div class="page-subtitle">搜索、保存并回看当前项目的学习资料；需要进入图谱时再转为草稿来源。</div>
          </div>
          <el-tag v-if="projectStore.currentProject" type="info">
            {{ projectStore.currentProject.title }}
          </el-tag>
        </div>
      </template>

      <template v-if="projectId">
        <el-alert
          v-if="configMissing || readinessWarning || searchError"
          :title="searchError || readinessWarning || '搜索能力待配置'"
          :type="configMissing || readinessWarning ? 'warning' : 'error'"
          show-icon
          :closable="false"
          style="margin-bottom: 16px"
        >
          <template #default>
            <template v-if="configMissing">
              项目资料库搜索属于在线增强能力。请先到“设置”页面填写 `SEARCH_API_KEY`，保存后再使用搜索；这不会影响学习路径规划主链演示。
              <el-button link type="primary" @click="router.push('/settings')">前往设置</el-button>
            </template>
            <template v-else-if="readinessWarning">
              当前仅搜索增强能力检查未通过；请检查设置页中的搜索配置后重新检查。学习路径规划主链仍可单独演示。
              <el-button link type="primary" @click="reloadSearchConfig">重新检查</el-button>
              <el-button link type="primary" @click="router.push('/settings')">前往设置</el-button>
            </template>
            <template v-else>
              资料搜索依赖外部在线服务；请检查设置页中的搜索配置或稍后重试。搜索异常不会代表系统主链不可用。
              <el-button link type="primary" @click="reloadSearchConfig">重新检查</el-button>
            </template>
          </template>
        </el-alert>

        <el-input
          v-model="searchQuery"
          placeholder="搜索并保存到项目资料库..."
          @keyup.enter="doSearch"
        >
          <template #append>
            <el-button @click="doSearch" :loading="searching" :disabled="configMissing || !!readinessWarning">搜索</el-button>
          </template>
        </el-input>

        <div class="tips">这里是项目资料库与搜索历史；路径页负责绑定到知识点，知识图谱页负责把资料转为 overlay 候选。</div>

        <section class="resource-route-hints" aria-label="资料去向提示">
          <article>
            <strong>留在资料库</strong>
            <span>保存搜索历史，便于后续回看和复用。</span>
          </article>
          <article>
            <strong>去路径页绑定</strong>
            <span>把资料绑定到当前阶段或知识点，学习时可在 Path 与 Dashboard 展开。</span>
          </article>
          <article>
            <strong>去知识图谱页生成候选</strong>
            <span>将高相关资料转为 overlay 草稿来源，再人工审核是否进入规划。</span>
          </article>
        </section>

        <el-table v-if="searchResults.length" :data="searchResults" size="small" stripe>
          <el-table-column label="标题" min-width="240">
            <template #default="{ row }">
              <a v-if="safeExternalUrl(row.url)" :href="safeExternalUrl(row.url)" target="_blank" rel="noopener" class="search-link">{{ row.title }}</a>
              <span v-else>{{ row.title }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="snippet" label="摘要" min-width="360" show-overflow-tooltip />
          <el-table-column label="相关度" width="100">
            <template #default="{ row }">{{ (row.score * 100).toFixed(0) }}%</template>
          </el-table-column>
          <el-table-column label="图谱草稿来源" width="170">
            <template #default="{ row, $index }">
              <el-button link type="primary" :loading="overlayAddingUrl === row.url" @click="addResultToOverlay(row, $index)">
                转为草稿来源
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <section v-if="persistedResults.length" class="saved-section">
          <div class="section-title">已保存资料与搜索历史</div>
          <el-table :data="persistedResults" size="small" stripe>
            <el-table-column label="标题" min-width="240">
              <template #default="{ row }">
                <a v-if="safeExternalUrl(row.url)" :href="safeExternalUrl(row.url)" target="_blank" rel="noopener" class="search-link">{{ row.title }}</a>
              <span v-else>{{ row.title }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="query" label="搜索词" min-width="160" />
            <el-table-column label="图谱草稿来源" width="170">
              <template #default="{ row }">
                <el-tag v-if="row.source_id" type="success" size="small">已转来源</el-tag>
                <el-button v-else link type="primary" :loading="overlayAddingResultId === row.result_id" @click="bridgePersistedResult(row)">
                  转为草稿来源
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </section>

        <el-empty v-else-if="searchDone" description="未找到相关资料" />
      </template>

      <el-empty v-else description="请先在项目页面选择一个项目">
        <template #extra>
          <el-button type="primary" @click="router.push('/project')">前往项目页</el-button>
        </template>
      </el-empty>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus/es/components/message/index'
import { healthApi } from '@/api/modules/health'
import { searchApi, type PersistedSearchResult, type SearchResultItem } from '@/api/modules/search'
import { safeExternalUrl } from '@/utils/url'
import { useProjectStore } from '@/stores/project'

const router = useRouter()
const projectStore = useProjectStore()

const projectId = computed(() => projectStore.currentProject?.id)
const searchQuery = ref('')
const searchResults = ref<SearchResultItem[]>([])
const persistedResults = ref<PersistedSearchResult[]>([])
const searching = ref(false)
const searchDone = ref(false)
const configMissing = ref(false)
const readinessWarning = ref('')
const searchError = ref('')
const overlayAddingUrl = ref('')
const overlayAddingResultId = ref('')

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
  if (!projectId.value || !searchQuery.value.trim() || configMissing.value || !!readinessWarning.value) return
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
    ElMessage.success(bridged.results[0]?.reused ? '已复用图谱草稿来源' : '已转为图谱草稿来源')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '转为图谱草稿来源失败')
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
.page-container { padding: 20px; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.page-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}
.page-subtitle {
  margin-top: 4px;
  font-size: 13px;
  color: #909399;
}
.tips {
  margin: 12px 0 16px;
  font-size: 13px;
  color: #909399;
}
.resource-route-hints {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
.resource-route-hints article {
  display: grid;
  gap: 4px;
  padding: 10px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fafafa;
}
.resource-route-hints strong {
  color: #303133;
  font-size: 13px;
}
.resource-route-hints span {
  color: #909399;
  font-size: 12px;
  line-height: 1.5;
}
.saved-section {
  margin-top: 20px;
}
.section-title {
  margin-bottom: 10px;
  font-weight: 600;
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
  .resource-route-hints {
    grid-template-columns: 1fr;
  }
}
</style>
