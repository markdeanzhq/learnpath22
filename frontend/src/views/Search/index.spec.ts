import { flushPromises, shallowMount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SearchIndex from './index.vue'
import { safeExternalUrl } from '@/utils/url'

const {
  searchMock,
  persistResultMock,
  listPersistedResultsMock,
  bridgeOverlaySourcesMock,
  configMock,
  readinessMock,
  currentProjectState,
  successMock,
} = vi.hoisted(() => ({
  searchMock: vi.fn(),
  persistResultMock: vi.fn(),
  listPersistedResultsMock: vi.fn(),
  bridgeOverlaySourcesMock: vi.fn(),
  configMock: vi.fn(),
  readinessMock: vi.fn(),
  currentProjectState: {
    value: {
      id: 'project-001',
      title: '机器学习基础学习计划',
    },
    set: undefined as undefined | ((project: { id: string; title: string }) => void),
  },
  successMock: vi.fn(),
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('element-plus/es/components/message/index', () => ({
  ElMessage: {
    success: successMock,
    error: vi.fn(),
  },
}))

vi.mock('@/stores/project', async () => {
  const { ref } = await import('vue')
  const currentProjectRef = ref(currentProjectState.value)
  currentProjectState.set = (project: typeof currentProjectState.value) => {
    currentProjectState.value = project
    currentProjectRef.value = project
  }
  return {
    useProjectStore: () => ({
      get currentProject() {
        return currentProjectRef.value
      },
    }),
  }
})

vi.mock('@/api/modules/health', () => ({
  healthApi: {
    getConfigSilently: configMock,
    getSearchReadiness: readinessMock,
  },
}))

vi.mock('@/api/modules/search', () => ({
  searchApi: {
    search: searchMock,
    persistResult: persistResultMock,
    listPersistedResults: listPersistedResultsMock,
    bridgeOverlaySources: bridgeOverlaySourcesMock,
  },
}))

const slotStub = (tag: string) => ({ template: `<${tag}><slot /></${tag}>` })
const cardStub = { template: '<section><slot name="header" /><slot /></section>' }
const tableColumnStub = { template: '<div />' }

function mountSearch() {
  return shallowMount(SearchIndex, {
    global: {
      stubs: {
        ElCard: cardStub,
        ElTag: slotStub('span'),
        ElAlert: slotStub('div'),
        ElButton: slotStub('button'),
        ElInput: slotStub('input'),
        ElTable: slotStub('div'),
        ElTableColumn: tableColumnStub,
        ElEmpty: slotStub('div'),
      },
    },
  })
}

describe('Search overlay bridge flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    currentProjectState.set?.({
      id: 'project-001',
      title: '机器学习基础学习计划',
    })
    configMock.mockResolvedValue({ search_api_key_set: true })
    readinessMock.mockResolvedValue({ ready: true })
    listPersistedResultsMock.mockResolvedValue([])
    searchMock.mockResolvedValue({
      query: '逻辑回归',
      results: [
        {
          title: '逻辑回归资料',
          url: 'https://example.com/logistic',
          snippet: '资料摘要',
          score: 0.9,
          provider: 'tavily',
        },
      ],
      count: 1,
      source: 'tavily',
    })
    persistResultMock.mockResolvedValue({
      result_id: 'result-001',
      query: '逻辑回归',
      provider: 'tavily',
      url: 'https://example.com/logistic',
      title: '逻辑回归资料',
      is_selected: true,
      binding_count: 0,
      created_at: '2026-04-22T09:00:00Z',
    })
    bridgeOverlaySourcesMock.mockResolvedValue({
      source_ids: ['src-001'],
      results: [{ result_id: 'result-001', source_id: 'src-001', source_type: 'search_url', reused: false, repaired: false }],
    })
  })

  it('renders project resource library and search history semantics', async () => {
    const wrapper = mountSearch()
    await flushPromises()

    expect(wrapper.text()).toContain('项目资料库')
    expect(wrapper.text()).toContain('搜索、保存并回看当前项目的学习资料')
    expect(wrapper.text()).toContain('项目资料库与搜索历史')
    expect(wrapper.text()).toContain('路径页负责绑定到知识点')
    expect(wrapper.text()).toContain('知识图谱页负责把资料转为 overlay 候选')
    expect(wrapper.text()).toContain('留在资料库')
    expect(wrapper.text()).toContain('去路径页绑定')
    expect(wrapper.text()).toContain('去知识图谱页生成候选')
  })

  it('persists a search result then bridges it to one overlay source', async () => {
    const wrapper = mountSearch()
    await flushPromises()

    ;(wrapper.vm as any).searchQuery = '逻辑回归'
    await (wrapper.vm as any).doSearch()
    await (wrapper.vm as any).addResultToOverlay((wrapper.vm as any).searchResults[0], 0)

    expect(persistResultMock).toHaveBeenCalledWith('project-001', {
      query: '逻辑回归',
      provider: 'tavily',
      url: 'https://example.com/logistic',
      title: '逻辑回归资料',
      snippet: '资料摘要',
      result_rank: 1,
      is_selected: true,
    })
    expect(bridgeOverlaySourcesMock).toHaveBeenCalledWith('project-001', ['result-001'])
    expect(listPersistedResultsMock).toHaveBeenCalledTimes(2)
    expect(successMock).toHaveBeenCalled()
  })

  it('clears persisted results when project changes', async () => {
    const wrapper = mountSearch()
    await flushPromises()
    ;(wrapper.vm as any).searchResults = [{ title: '旧资料', url: 'https://example.com/old' }]
    ;(wrapper.vm as any).persistedResults = [{ result_id: 'old-result', title: '旧保存', url: 'https://example.com/old' }]

    currentProjectState.set?.({ id: 'project-002', title: '新项目' })
    await wrapper.vm.$nextTick()
    await flushPromises()

    expect((wrapper.vm as any).persistedResults).toEqual([])
    expect(listPersistedResultsMock).toHaveBeenLastCalledWith('project-002')
  })

  it('allows only http and https external links', () => {
    expect(safeExternalUrl('https://example.com/a')).toBe('https://example.com/a')
    expect(safeExternalUrl('javascript:alert(1)')).toBe('')
    expect(safeExternalUrl('data:text/html,boom')).toBe('')
  })
})
