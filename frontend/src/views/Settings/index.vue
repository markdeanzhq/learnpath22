<template>
  <div class="page-container">
    <el-card shadow="never">
      <template #header><span>系统设置</span></template>

      <el-form :model="form" label-width="120px" style="max-width: 600px;">
        <el-form-item label="LLM Base URL">
          <el-input v-model="form.llm_base_url" :placeholder="llmBaseUrlPlaceholder" />
        </el-form-item>

        <el-form-item label="LLM Model">
          <el-input v-model="form.llm_model" :placeholder="llmModelPlaceholder" />
        </el-form-item>

        <el-form-item label="LLM API Key">
          <el-input
            v-model="form.llm_api_key"
            type="password"
            show-password
            :placeholder="llmApiKeyPlaceholder"
          />
        </el-form-item>

        <el-form-item label="搜索 API Key">
          <el-input
            v-model="form.search_api_key"
            type="password"
            show-password
            :placeholder="searchApiKeyPlaceholder"
          />
        </el-form-item>

        <el-form-item label="启用解释润色">
          <el-switch
            v-model="form.llm_explanation_polish"
            active-text="启用 AI 润色"
            aria-label="启用 AI 润色"
          />
          <el-text type="info" size="small" style="margin-left: 12px;">
            开启后，路径解释将经 LLM 自然语言润色（需配置 LLM API Key）。
          </el-text>
        </el-form-item>

        <el-form-item>
          <el-space wrap>
            <el-button type="primary" @click="saveConfig" :loading="saving">
              保存配置
            </el-button>
            <el-button @click="testLlmConnection" :loading="testingLlm">
              测试 LLM 连通性
            </el-button>
            <el-button @click="refreshReadiness" :loading="readinessLoading">
              检查演示主链路
            </el-button>
            <el-button
              v-if="canRepairGraphSync"
              type="warning"
              @click="repairGraphSync"
              :loading="graphSyncRepairing"
            >
              重新同步图谱
            </el-button>
            <el-button @click="clearLocalSavedConfig">清空本地保存</el-button>
          </el-space>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="saveMsg"
        :title="saveMsg"
        type="success"
        show-icon
        closable
        style="margin-top: 12px; max-width: 600px"
      />

      <el-alert
        v-if="llmTestMsg"
        :title="llmTestMsg"
        :type="llmTestStatus"
        show-icon
        closable
        style="margin-top: 12px; max-width: 600px"
      />

      <el-alert
        v-if="readiness || readinessError"
        :title="readinessTitle"
        :type="readiness?.demo_ready ? 'success' : 'warning'"
        show-icon
        :closable="false"
        style="margin-top: 12px; max-width: 720px"
      >
        <template #default>
          <template v-if="readiness">
            <div class="readiness-summary">
              <el-tag size="small" :type="readiness.demo_ready ? 'success' : 'danger'">
                论文主链{{ readiness.demo_ready ? '可演示' : '暂不可演示' }}
              </el-tag>
              <el-tag size="small" :type="readiness.enhanced_ready ? 'success' : 'warning'">
                在线增强{{ readiness.enhanced_ready ? '就绪' : '待完善' }}
              </el-tag>
            </div>
            <div class="readiness-note">
              路径规划主链依赖 SQLite、Neo4j 与图谱同步；LLM 与资料搜索属于在线增强能力，未就绪时不会否定论文主链演示价值。
            </div>
            <div class="readiness-row" v-for="(service, key) in readiness.services" :key="key">
              <span class="readiness-label">{{ serviceLabel(String(key)) }}</span>
              <el-tag size="small" :type="serviceTagType(service.status)">
                {{ serviceStatusText(String(key), service) }}
              </el-tag>
              <span class="readiness-reason">{{ serviceReasonText(String(key), service) }}</span>
            </div>
          </template>
          <template v-else>
            {{ readinessError }}
          </template>
        </template>
      </el-alert>

      <el-divider />

      <el-text type="info" size="small">
        浏览器本地会记住最近一次成功保存的设置；后端运行时配置会持久化到 SQLite；应用加载时会自动回灌本地保存的设置。
      </el-text>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { healthApi, type ReadinessResponse, type ReadinessServiceStatus } from '@/api/modules/health'
import { graphApi } from '@/api/modules/graph'
import { useSettingsStore } from '@/stores/settings'
import { formatServiceReason } from '@/utils/displayLabels'

const settingsStore = useSettingsStore()
const createEmptyForm = () => ({
  llm_base_url: '',
  llm_model: '',
  llm_api_key: '',
  search_api_key: '',
  llm_explanation_polish: false as boolean,
})

const form = ref(createEmptyForm())
const llmBaseUrlPlaceholder = ref('未配置')
const llmModelPlaceholder = ref('未配置')
const llmApiKeyPlaceholder = ref('未配置')
const searchApiKeyPlaceholder = ref('未配置')
const saving = ref(false)
const testingLlm = ref(false)
const readinessLoading = ref(false)
const graphSyncRepairing = ref(false)
const saveMsg = ref('')
const llmTestMsg = ref('')
const readiness = ref<ReadinessResponse | null>(null)
const readinessError = ref('')
const llmTestStatus = ref<'success' | 'warning' | 'error'>('success')
const readinessTitle = computed(() => {
  if (readiness.value) {
    if (readiness.value.demo_ready && readiness.value.enhanced_ready) {
      return '论文主链与在线增强能力均已就绪'
    }
    if (readiness.value.demo_ready) {
      return '论文主链可演示，在线增强能力待完善'
    }
    return '论文主链暂不可演示'
  }
  return readinessError.value || '演示主链路检查未通过'
})
const canRepairGraphSync = computed(() => {
  const graphSync = readiness.value?.services.graph_sync
  return graphSync?.reason === 'seed_metadata_stale' || graphSync?.status === 'stale'
})

onMounted(async () => {
  Object.assign(form.value, settingsStore.hydrateFromLocal())

  try {
    const data = await healthApi.getConfig()
    llmBaseUrlPlaceholder.value = data.llm_base_url || '未配置'
    llmModelPlaceholder.value = data.llm_model || '未配置'
    llmApiKeyPlaceholder.value = data.llm_api_key_set ? '已配置（留空则不修改）' : '未配置'
    searchApiKeyPlaceholder.value = data.search_api_key_set ? '已配置（留空则不修改）' : '未配置'
    form.value.llm_explanation_polish = data.llm_explanation_polish
    settingsStore.llmApiKeySet = data.llm_api_key_set
    settingsStore.searchApiKeySet = data.search_api_key_set
    settingsStore.llmExplanationPolish = data.llm_explanation_polish
  } catch {}

  await refreshReadiness()
})

async function saveConfig() {
  saving.value = true
  saveMsg.value = ''
  try {
    const payload = Object.fromEntries(
      Object.entries(form.value)
        .filter(([, value]) => {
          if (typeof value === 'boolean') return true
          if (typeof value === 'string') return value.trim() !== ''
          return false
        })
    )

    const data = await healthApi.updateConfig(payload)
    settingsStore.savePatchToLocal(payload)
    saveMsg.value = data.message || '运行时配置已保存'
    llmBaseUrlPlaceholder.value = data.llm_base_url || llmBaseUrlPlaceholder.value
    llmModelPlaceholder.value = data.llm_model || llmModelPlaceholder.value
    llmApiKeyPlaceholder.value = data.llm_api_key_set ? '已配置（留空则不修改）' : '未配置'
    searchApiKeyPlaceholder.value = data.search_api_key_set ? '已配置（留空则不修改）' : '未配置'
    settingsStore.llmApiKeySet = data.llm_api_key_set
    settingsStore.searchApiKeySet = data.search_api_key_set
    settingsStore.llmExplanationPolish = data.llm_explanation_polish
    form.value.llm_api_key = ''
    form.value.search_api_key = ''
    await refreshReadiness()
  } catch {}
  finally {
    saving.value = false
  }
}

function clearLocalSavedConfig() {
  settingsStore.clearLocalSavedConfig()
  form.value = createEmptyForm()
  saveMsg.value = '仅已清空浏览器本地保存，未清空当前后端运行时配置'
}

async function testLlmConnection() {
  testingLlm.value = true
  llmTestMsg.value = ''
  try {
    const data = await healthApi.testLlm()
    if (data.status === 'ok') {
      llmTestStatus.value = 'success'
      llmTestMsg.value = `LLM 连通性正常：${data.model} @ ${data.base_url}`
      return
    }
    if (data.status === 'skipped') {
      llmTestStatus.value = 'warning'
      llmTestMsg.value = data.reason || 'LLM 连通性测试已跳过'
      return
    }
    llmTestStatus.value = 'error'
    llmTestMsg.value = data.reason || 'LLM 连通性测试失败'
  } catch {
    llmTestStatus.value = 'error'
    llmTestMsg.value = 'LLM 连通性测试失败'
  } finally {
    testingLlm.value = false
  }
}

async function refreshReadiness() {
  readinessLoading.value = true
  readinessError.value = ''
  try {
    readiness.value = await healthApi.getReadiness()
  } catch {
    readiness.value = null
    readinessError.value = '演示主链路检查失败，请稍后重试'
  } finally {
    readinessLoading.value = false
  }
}

async function repairGraphSync() {
  graphSyncRepairing.value = true
  try {
    await graphApi.seedGraph()
    ElMessage.success('图谱已重新同步，请重新检查演示主链路')
    await refreshReadiness()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.error || error?.message || '图谱重新同步失败')
  } finally {
    graphSyncRepairing.value = false
  }
}

function serviceLabel(key: string) {
  if (key === 'sqlite') return 'SQLite'
  if (key === 'neo4j') return 'Neo4j'
  if (key === 'graph_sync') return '图谱同步'
  if (key === 'llm') return 'LLM'
  if (key === 'search') return '搜索'
  return key
}

function serviceTagType(status: string) {
  if (status === 'ok') return 'success'
  if (status === 'skipped' || status === 'blocked' || status === 'unknown') return 'warning'
  return 'danger'
}

function serviceStatusText(key: string, service: ReadinessServiceStatus) {
  if (service.ready) {
    return service.status === 'unknown' ? '兼容估算' : '就绪'
  }
  if (service.status === 'skipped') return key === 'llm' || key === 'search' ? '在线增强未配置' : '待配置'
  if (service.status === 'blocked') return key === 'graph_sync' ? '受阻' : '受限'
  if (service.status === 'missing') return '缺失'
  if (service.status === 'stale') return '需同步'
  if (service.status === 'drifted') return '有漂移'
  if (service.status === 'unknown') return '待确认'
  return '异常'
}

function serviceReasonText(key: string, service: ReadinessServiceStatus) {
  return formatServiceReason(service.reason) || serviceDetail(key, service)
}

function serviceDetail(key: string, service: ReadinessServiceStatus) {
  if (key === 'graph_sync') {
    if (service.in_sync) {
      const domainLabel = service.domain || '当前默认领域'
      return `${domainLabel} 已同步，可支撑论文主链演示`
    }
    return service.reason || '需先完成 Domain Pack 到 Neo4j 的同步'
  }
  if (key === 'llm') {
    if (service.base_url && service.model) return `${service.model} @ ${service.base_url}`
    return service.reason || 'LLM 仅用于在线增强解释，不影响路径规划主链'
  }
  if (key === 'search') {
    if (service.provider) return `${service.provider} 在线搜索能力可单独检查`
    return service.reason || '资料搜索属于在线增强能力，不影响路径规划主链'
  }
  if (service.provider) return `${service.provider} 可用性检查完成`
  return '论文主链基础依赖可用'
}
</script>

<style scoped>
.page-container { padding: 20px; }
.readiness-summary {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.readiness-note {
  margin-bottom: 8px;
  color: #606266;
  line-height: 1.6;
}
.readiness-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.readiness-label {
  min-width: 56px;
  font-weight: 600;
}
.readiness-reason {
  color: #606266;
}
</style>
