<template>
  <div class="page-container">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div>
            <div class="page-title">资料搜索</div>
            <div class="page-subtitle">为当前项目搜索相关学习资料</div>
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
              资料搜索属于在线增强能力。请先到“设置”页面填写 `SEARCH_API_KEY`，保存后再使用搜索；这不会影响学习路径规划主链演示。
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
          placeholder="输入关键词搜索学习资料..."
          @keyup.enter="doSearch"
        >
          <template #append>
            <el-button @click="doSearch" :loading="searching" :disabled="configMissing || !!readinessWarning">搜索</el-button>
          </template>
        </el-input>

        <div class="tips">建议输入更具体的目标，如“逻辑回归 分类 原理”</div>

        <el-table v-if="searchResults.length" :data="searchResults" size="small" stripe>
          <el-table-column label="标题" min-width="240">
            <template #default="{ row }">
              <a :href="row.url" target="_blank" rel="noopener" class="search-link">{{ row.title }}</a>
            </template>
          </el-table-column>
          <el-table-column prop="snippet" label="摘要" min-width="360" show-overflow-tooltip />
          <el-table-column label="相关度" width="100">
            <template #default="{ row }">{{ (row.score * 100).toFixed(0) }}%</template>
          </el-table-column>
        </el-table>

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
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { healthApi } from '@/api/modules/health'
import { searchApi } from '@/api/modules/search'
import { useProjectStore } from '@/stores/project'

const router = useRouter()
const projectStore = useProjectStore()

const projectId = computed(() => projectStore.currentProject?.id)
const searchQuery = ref('')
const searchResults = ref<any[]>([])
const searching = ref(false)
const searchDone = ref(false)
const configMissing = ref(false)
const readinessWarning = ref('')
const searchError = ref('')

onMounted(async () => {
  await loadSearchConfig()
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
}
</style>
