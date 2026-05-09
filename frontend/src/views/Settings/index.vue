<template>
  <PageShell
    title="系统设置"
    eyebrow="运行状态"
    subtitle="优先确认本地演示主链；LLM 与搜索属于可选在线增强能力。"
  >
    <template #actions>
      <el-button @click="refreshReadiness" :loading="readinessLoading">检查演示主链路</el-button>
      <el-button type="primary" @click="saveConfig" :loading="saving">保存配置</el-button>
    </template>

    <template #summary>
      <PageSummaryBar :items="settingsSummaryItems">
        <NextActionCard :title="nextSettingsTitle" :description="nextSettingsDescription">
          <el-button
            v-if="canRepairGraphSync"
            size="small"
            type="warning"
            :loading="graphSyncRepairing"
            @click="repairGraphSync"
          >
            重新同步图谱
          </el-button>
          <el-button v-else size="small" type="primary" :loading="readinessLoading" @click="refreshReadiness">
            重新检查
          </el-button>
        </NextActionCard>
      </PageSummaryBar>
    </template>

    <section class="settings-workspace">
      <main class="readiness-panel lp-scroll-panel">
        <header class="panel-heading">
          <div>
            <h3>演示主链路状态</h3>
            <p>本科毕设演示优先看 SQLite、Domain Pack 与路径规划主链；在线增强未配置不代表主链不可用。</p>
          </div>
          <el-tag v-if="readiness" :type="readiness.local_demo_ready ? 'success' : 'danger'">
            {{ readiness.local_demo_ready ? '主链可演示' : '主链待修复' }}
          </el-tag>
        </header>

        <el-alert
          v-if="readiness || readinessError"
          :title="readinessTitle"
          :type="readinessAlertType"
          show-icon
          :closable="false"
        >
          <template #default>
            <template v-if="readiness">
              <div class="readiness-summary">
                <el-tag size="small" :type="readiness.local_demo_ready ? 'success' : 'danger'">
                  本地主链{{ readiness.local_demo_ready ? '可演示' : '暂不可演示' }}
                </el-tag>
                <el-tag size="small" :type="readiness.demo_ready ? 'success' : 'warning'">
                  Neo4j 投影{{ readiness.demo_ready ? '就绪' : '待同步' }}
                </el-tag>
                <el-tag size="small" :type="readiness.enhanced_ready ? 'success' : 'warning'">
                  在线增强{{ readiness.enhanced_ready ? '就绪' : '可选配置' }}
                </el-tag>
              </div>
              <div class="readiness-note">
                本地图谱浏览与路径规划主链优先依赖 SQLite 和本地 Domain Pack；Neo4j 投影用于显式同步、投影诊断和图谱展示/审核流程，LLM 与资料搜索属于在线增强能力。
              </div>
            </template>
            <template v-else>
              {{ readinessError }}
            </template>
          </template>
        </el-alert>

        <section v-else class="readiness-placeholder">
          <h4>尚未完成主链路检查</h4>
          <p>页面打开后会自动检查；也可以手动点击“检查演示主链路”。</p>
          <el-button type="primary" :loading="readinessLoading" @click="refreshReadiness">立即检查</el-button>
        </section>

        <ReadinessCapabilityCards v-if="readiness" :readiness="readiness" />

        <section v-if="readiness" class="service-status-list" aria-label="服务状态明细">
          <div class="readiness-row" v-for="(service, key) in readiness.services" :key="key">
            <span class="readiness-label">{{ serviceLabel(String(key)) }}</span>
            <el-tag size="small" :type="serviceTagType(service.status)">
              {{ serviceStatusText(String(key), service) }}
            </el-tag>
            <span class="readiness-reason">{{ serviceReasonText(String(key), service) }}</span>
          </div>
        </section>
      </main>

      <aside class="settings-side-panel lp-scroll-panel">
        <el-collapse v-model="settingsActivePanels">
          <el-collapse-item title="在线增强配置（可选）" name="enhancement">
            <el-form :model="form" label-width="112px" class="settings-form">
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

              <el-form-item label="解释润色">
                <el-switch
                  v-model="form.llm_explanation_polish"
                  active-text="启用 AI 润色"
                  aria-label="启用 AI 润色"
                />
              </el-form-item>
            </el-form>
          </el-collapse-item>

          <el-collapse-item title="操作与本地缓存" name="actions">
            <el-space wrap>
              <el-button type="primary" @click="saveConfig" :loading="saving">保存配置</el-button>
              <el-button @click="testLlmConnection" :loading="testingLlm">测试 LLM 连通性</el-button>
              <el-button @click="refreshReadiness" :loading="readinessLoading">检查演示主链路</el-button>
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

            <el-alert
              v-if="saveMsg"
              class="settings-message"
              :title="saveMsg"
              type="success"
              show-icon
              closable
            />

            <el-alert
              v-if="llmTestMsg"
              class="settings-message"
              :title="llmTestMsg"
              :type="llmTestStatus"
              show-icon
              closable
            />

            <p class="settings-note">
              浏览器本地会记住最近一次成功保存的设置；后端运行时配置会持久化到 SQLite；应用加载时会自动回灌本地保存的设置。
            </p>
          </el-collapse-item>
        </el-collapse>
      </aside>
    </section>
  </PageShell>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import { healthApi, type ReadinessResponse, type ReadinessServiceStatus } from '@/api/modules/health'
import { graphApi } from '@/api/modules/graph'
import { useSettingsStore } from '@/stores/settings'
import { formatServiceReason } from '@/utils/displayLabels'
import PageShell from '@/components/Layout/PageShell.vue'
import PageSummaryBar from '@/components/PageSummaryBar.vue'
import NextActionCard from '@/components/NextActionCard.vue'
import ReadinessCapabilityCards from './components/ReadinessCapabilityCards.vue'

type SummaryTone = 'primary' | 'success' | 'warning' | 'danger' | 'info'

const settingsStore = useSettingsStore()
const createEmptyForm = () => ({
  llm_base_url: '',
  llm_model: '',
  llm_api_key: '',
  search_api_key: '',
  llm_explanation_polish: false as boolean,
})

const form = ref(createEmptyForm())
const settingsActivePanels = ref(['enhancement', 'actions'])
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
const readinessAlertType = computed<'success' | 'warning'>(() => readiness.value?.local_demo_ready ? 'success' : 'warning')
const readinessTitle = computed(() => {
  if (readiness.value) {
    if (readiness.value.local_demo_ready && readiness.value.enhanced_ready) {
      return '本地主链可演示，在线增强能力已就绪'
    }
    if (readiness.value.local_demo_ready) {
      return '本地主链可演示，Neo4j 投影或在线增强可按需完善'
    }
    return '本地主链暂不可演示'
  }
  return readinessError.value || '演示主链路检查未通过'
})
const canRepairGraphSync = computed(() => {
  const graphSync = readiness.value?.services.graph_sync
  return graphSync?.reason === 'seed_metadata_stale' || graphSync?.status === 'stale'
})
const mainChainSummary = computed(() => {
  if (!readiness.value) return { value: '未检查', tone: 'info' as SummaryTone, detail: readinessError.value || '等待主链路检查' }
  return readiness.value.local_demo_ready
    ? { value: '可演示', tone: 'success' as SummaryTone, detail: 'SQLite 与 Domain Pack 主链可用' }
    : { value: '待修复', tone: 'danger' as SummaryTone, detail: '需优先处理本地主链依赖' }
})
const projectionSummary = computed(() => {
  if (!readiness.value) return { value: '未检查', tone: 'info' as SummaryTone, detail: '用于图谱投影诊断' }
  return readiness.value.demo_ready
    ? { value: '就绪', tone: 'success' as SummaryTone, detail: 'Neo4j 投影状态正常' }
    : { value: '可同步', tone: canRepairGraphSync.value ? 'warning' as SummaryTone : 'info' as SummaryTone, detail: '不阻塞本地规划主链' }
})
const enhancementSummary = computed(() => {
  if (!readiness.value) return { value: '未检查', tone: 'info' as SummaryTone, detail: 'LLM 与搜索按需配置' }
  return readiness.value.enhanced_ready
    ? { value: '就绪', tone: 'success' as SummaryTone, detail: 'LLM 或搜索增强可用' }
    : { value: '可选', tone: 'warning' as SummaryTone, detail: '未配置也不影响主链演示' }
})
const settingsSummaryItems = computed<Array<{ label: string; value: string; detail: string; tone: SummaryTone }>>(() => [
  {
    label: '本地主链',
    ...mainChainSummary.value,
  },
  {
    label: 'Neo4j 投影',
    ...projectionSummary.value,
  },
  {
    label: '在线增强',
    ...enhancementSummary.value,
  },
  {
    label: '解释润色',
    value: form.value.llm_explanation_polish ? '已开启' : '未开启',
    detail: form.value.llm_explanation_polish ? '仅润色解释文本' : '路径解释使用规则输出',
    tone: form.value.llm_explanation_polish ? 'primary' : 'info',
  },
])
const nextSettingsTitle = computed(() => {
  if (!readiness.value && !readinessError.value) return '先检查演示主链路'
  if (readiness.value && !readiness.value.local_demo_ready) return '优先修复本地主链'
  if (canRepairGraphSync.value) return '可重新同步图谱投影'
  if (readiness.value && !readiness.value.enhanced_ready) return '在线增强可按需配置'
  return '当前配置满足演示'
})
const nextSettingsDescription = computed(() => {
  if (!readiness.value && !readinessError.value) return '检查结果会告诉你哪些能力影响主链，哪些只是可选增强。'
  if (readiness.value && !readiness.value.local_demo_ready) return '本地主链不可用时，应先处理 SQLite、Domain Pack 或后端服务状态。'
  if (canRepairGraphSync.value) return 'Neo4j 投影可重新同步；即使未同步，也不裁剪本地路径规划主链。'
  if (readiness.value && !readiness.value.enhanced_ready) return '需要在线搜索或 LLM 润色时，再展开右侧可选配置。'
  return '可以回到项目页、路径页或图谱页继续演示完整流程。'
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
  if (key === 'graph_sync') return 'Neo4j 投影'
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
  if (key === 'online_enhancement') return '可选配置'
  if (key === 'neo4j_projection') return service.status === 'stale' ? '需同步' : '待同步'
  if (key === 'local_graph_read') return '受阻'
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
  if (key === 'local_graph_read') {
    return service.reason || 'SQLite 与本地 Domain Pack 组成可演示主链'
  }
  if (key === 'online_enhancement') {
    return service.reason || '在线增强未配置时不影响本地图谱浏览与路径规划'
  }
  if (key === 'graph_sync' || key === 'neo4j_projection') {
    if (service.in_sync) {
      const domainLabel = service.domain || '当前默认领域'
      return `${domainLabel} Neo4j 投影已同步；本地读模型不依赖该投影`
    }
    return service.reason || '仅影响显式同步、投影诊断和图谱展示/审核流程'
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
.settings-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(340px, 0.75fr);
  gap: var(--lp-space-4);
  height: calc(100vh - var(--lp-header-height) - 228px);
  min-height: 440px;
}

.readiness-panel,
.settings-side-panel {
  min-width: 0;
  min-height: 0;
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

.panel-heading h3 {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 16px;
}

.panel-heading p {
  max-width: 720px;
  margin: 4px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.readiness-summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--lp-space-2);
  margin-bottom: var(--lp-space-2);
}

.readiness-note {
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

.readiness-placeholder {
  padding: var(--lp-space-5);
  border: 1px dashed var(--el-border-color);
  border-radius: var(--lp-radius-md);
  background: var(--el-fill-color-light);
  text-align: center;
}

.readiness-placeholder h4 {
  margin: 0 0 var(--lp-space-2);
  color: var(--el-text-color-primary);
}

.readiness-placeholder p {
  margin: 0 0 var(--lp-space-3);
  color: var(--el-text-color-secondary);
}

.service-status-list {
  display: grid;
  gap: var(--lp-space-2);
  margin-top: var(--lp-space-3);
}

.readiness-row {
  display: grid;
  grid-template-columns: 92px 88px minmax(0, 1fr);
  gap: var(--lp-space-2);
  align-items: center;
  padding: var(--lp-space-2);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--lp-radius-md);
  background: var(--el-fill-color-light);
}

.readiness-label {
  color: var(--el-text-color-primary);
  font-weight: 600;
}

.readiness-reason {
  overflow: hidden;
  color: var(--el-text-color-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.settings-form {
  padding-top: var(--lp-space-2);
}

.settings-message {
  margin-top: var(--lp-space-3);
}

.settings-note {
  margin: var(--lp-space-3) 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

@media (max-width: 960px) {
  .settings-workspace {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 0;
  }

  .readiness-row {
    grid-template-columns: 1fr;
  }

  .readiness-reason {
    white-space: normal;
  }
}
</style>
