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

        <el-form-item>
          <el-space wrap>
            <el-button type="primary" @click="saveConfig" :loading="saving">
              保存配置
            </el-button>
            <el-button @click="testLlmConnection" :loading="testingLlm">
              测试 LLM 连通性
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

      <el-divider />

      <el-text type="info" size="small">
        浏览器本地会记住最近一次成功保存的设置；后端仍使用运行时配置；应用加载时会自动回灌本地保存的设置。
      </el-text>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { healthApi } from '@/api/modules/health'
import { useSettingsStore } from '@/stores/settings'

const settingsStore = useSettingsStore()
const createEmptyForm = () => ({
  llm_base_url: '',
  llm_model: '',
  llm_api_key: '',
  search_api_key: '',
})

const form = ref(createEmptyForm())
const llmBaseUrlPlaceholder = ref('未配置')
const llmModelPlaceholder = ref('未配置')
const llmApiKeyPlaceholder = ref('未配置')
const searchApiKeyPlaceholder = ref('未配置')
const saving = ref(false)
const testingLlm = ref(false)
const saveMsg = ref('')
const llmTestMsg = ref('')
const llmTestStatus = ref<'success' | 'warning' | 'error'>('success')

onMounted(async () => {
  Object.assign(form.value, settingsStore.hydrateFromLocal())

  try {
    const data = await healthApi.getConfig()
    llmBaseUrlPlaceholder.value = data.llm_base_url || '未配置'
    llmModelPlaceholder.value = data.llm_model || '未配置'
    llmApiKeyPlaceholder.value = data.llm_api_key_set ? '已配置（留空则不修改）' : '未配置'
    searchApiKeyPlaceholder.value = data.search_api_key_set ? '已配置（留空则不修改）' : '未配置'
  } catch {}
})

async function saveConfig() {
  saving.value = true
  saveMsg.value = ''
  try {
    const payload = Object.fromEntries(
      Object.entries(form.value)
        .filter(([, value]) => value.trim())
    )

    const data = await healthApi.updateConfig(payload)
    settingsStore.savePatchToLocal(payload)
    saveMsg.value = data.message || '运行时配置已保存'
    llmBaseUrlPlaceholder.value = data.llm_base_url || llmBaseUrlPlaceholder.value
    llmModelPlaceholder.value = data.llm_model || llmModelPlaceholder.value
    llmApiKeyPlaceholder.value = data.llm_api_key_set ? '已配置（留空则不修改）' : '未配置'
    searchApiKeyPlaceholder.value = data.search_api_key_set ? '已配置（留空则不修改）' : '未配置'
    form.value.llm_api_key = ''
    form.value.search_api_key = ''
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
</script>

<style scoped>
.page-container { padding: 20px; }
</style>
