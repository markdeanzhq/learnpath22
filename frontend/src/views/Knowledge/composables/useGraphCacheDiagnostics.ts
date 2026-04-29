import { computed, ref } from 'vue'
import type { GraphCacheCounterStats, GraphCacheStatsData } from '@/api/modules/graph'

type CacheStatsFetcher = () => Promise<GraphCacheStatsData>

export interface GraphCacheDiagnosticItem {
  key: keyof GraphCacheStatsData
  label: string
  hitRateLabel: string
  sizeLabel: string
}

const CACHE_LABELS: Record<keyof GraphCacheStatsData, string> = {
  pack_graph_elements: '领域图缓存',
  project_graph_snapshot: '项目快照缓存',
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`
}

function formatCacheItem(key: keyof GraphCacheStatsData, stats: GraphCacheCounterStats): GraphCacheDiagnosticItem {
  return {
    key,
    label: CACHE_LABELS[key],
    hitRateLabel: `命中 ${formatPercent(stats.hit_rate)}`,
    sizeLabel: `${stats.size}/${stats.max_size}`,
  }
}

export function useGraphCacheDiagnostics(fetchStats: CacheStatsFetcher, enabled = import.meta.env.DEV) {
  const graphCacheStats = ref<GraphCacheStatsData | null>(null)
  const graphCacheStatsLoading = ref(false)
  const graphCacheStatsError = ref('')

  const graphCacheDiagnosticItems = computed<GraphCacheDiagnosticItem[]>(() => {
    if (!graphCacheStats.value) return []
    return (Object.keys(CACHE_LABELS) as Array<keyof GraphCacheStatsData>).map((key) => formatCacheItem(key, graphCacheStats.value![key]))
  })

  const showGraphCacheDiagnostics = computed(() => Boolean(
    enabled && (graphCacheStatsLoading.value || graphCacheStatsError.value || graphCacheDiagnosticItems.value.length),
  ))

  async function refreshGraphCacheStats() {
    if (!enabled) return
    graphCacheStatsLoading.value = true
    graphCacheStatsError.value = ''
    try {
      graphCacheStats.value = await fetchStats()
    } catch (error: any) {
      graphCacheStatsError.value = error?.response?.data?.error || error?.message || '缓存诊断读取失败'
    } finally {
      graphCacheStatsLoading.value = false
    }
  }

  return {
    graphCacheStats,
    graphCacheStatsLoading,
    graphCacheStatsError,
    graphCacheDiagnosticItems,
    showGraphCacheDiagnostics,
    refreshGraphCacheStats,
  }
}
