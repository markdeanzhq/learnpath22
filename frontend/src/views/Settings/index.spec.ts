import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SettingsIndex from './index.vue'

const {
  healthGetConfigMock,
  healthGetReadinessMock,
  healthUpdateConfigMock,
  healthTestLlmMock,
  graphSeedGraphMock,
  hydrateFromLocalMock,
  savePatchToLocalMock,
  clearLocalSavedConfigMock,
  successMock,
  errorMock,
} = vi.hoisted(() => ({
  healthGetConfigMock: vi.fn(),
  healthGetReadinessMock: vi.fn(),
  healthUpdateConfigMock: vi.fn(),
  healthTestLlmMock: vi.fn(),
  graphSeedGraphMock: vi.fn(),
  hydrateFromLocalMock: vi.fn(),
  savePatchToLocalMock: vi.fn(),
  clearLocalSavedConfigMock: vi.fn(),
  successMock: vi.fn(),
  errorMock: vi.fn(),
}))

vi.mock('@/api/modules/health', () => ({
  healthApi: {
    getConfig: healthGetConfigMock,
    getReadiness: healthGetReadinessMock,
    updateConfig: healthUpdateConfigMock,
    testLlm: healthTestLlmMock,
  },
}))

vi.mock('@/api/modules/graph', () => ({
  graphApi: {
    seedGraph: graphSeedGraphMock,
  },
}))

vi.mock('@/stores/settings', () => ({
  useSettingsStore: () => ({
    hydrateFromLocal: hydrateFromLocalMock,
    savePatchToLocal: savePatchToLocalMock,
    clearLocalSavedConfig: clearLocalSavedConfigMock,
    llmApiKeySet: false,
    searchApiKeySet: false,
    llmExplanationPolish: false,
  }),
}))

vi.mock('element-plus/es/components/message/index', () => ({
  ElMessage: {
    success: successMock,
    error: errorMock,
  },
}))

function mountSettings() {
  return shallowMount(SettingsIndex, {
    global: {
      stubs: {
        ElCard: { template: '<section><slot name="header" /><slot /></section>' },
        ElForm: { template: '<form><slot /></form>' },
        ElFormItem: { template: '<label><slot /></label>' },
        ElInput: { template: '<input />' },
        ElSwitch: { template: '<input type="checkbox" />' },
        ElText: { template: '<span><slot /></span>' },
        ElSpace: { template: '<div><slot /></div>' },
        ElButton: { template: '<button><slot /></button>' },
        ElAlert: { props: ['title'], template: '<div><strong>{{ title }}</strong><slot /></div>' },
        ElTag: { props: ['type'], template: '<span><slot /></span>' },
        ElDivider: { template: '<hr />' },
      },
    },
  })
}

describe('Settings readiness display', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    hydrateFromLocalMock.mockReturnValue({})
    healthGetConfigMock.mockResolvedValue({
      llm_base_url: 'https://api.example.com/v1',
      llm_model: 'demo-model',
      llm_api_key_set: false,
      search_api_key_set: false,
      llm_explanation_polish: false,
    })
    healthUpdateConfigMock.mockResolvedValue({ message: 'ok' })
    healthTestLlmMock.mockResolvedValue({ status: 'skipped', reason: 'LLM_API_KEY not configured' })
    graphSeedGraphMock.mockResolvedValue({})
  })

  it('separates local demo readiness from optional Neo4j projection and online enhancement', async () => {
    healthGetReadinessMock.mockResolvedValue({
      status: 'degraded',
      ready: false,
      core_ready: false,
      demo_ready: false,
      local_demo_ready: true,
      enhanced_ready: false,
      capabilities: {
        local_graph_read: { status: 'ok', ready: true, reason: 'local_read_model_ready' },
        neo4j_projection: { status: 'blocked', ready: false, in_sync: false, reason: 'neo4j_unavailable' },
        online_enhancement: { status: 'degraded', ready: false, reason: 'online_enhancement_optional' },
      },
      services: {
        sqlite: { status: 'ok', ready: true },
        neo4j: { status: 'error', ready: false, reason: 'offline' },
        graph_sync: { status: 'blocked', ready: false, in_sync: false, reason: 'neo4j_unavailable' },
        llm: { status: 'skipped', ready: false, reason: 'LLM_API_KEY not configured' },
        search: { status: 'skipped', ready: false, provider: 'tavily', reason: '搜索服务未配置' },
      },
    })

    const wrapper = mountSettings()
    await flushPromises()

    expect(wrapper.text()).toContain('本地主链可演示，Neo4j 投影或在线增强可按需完善')
    expect(wrapper.text()).toContain('本地主链可演示')
    expect(wrapper.text()).toContain('Neo4j 投影待同步')
    expect(wrapper.text()).toContain('在线增强可选配置')
    expect(wrapper.text()).toContain('本地图谱浏览与路径规划主链优先依赖 SQLite 和本地 Domain Pack')
    expect(wrapper.text()).not.toContain('论文主链暂不可演示')
  })
})
