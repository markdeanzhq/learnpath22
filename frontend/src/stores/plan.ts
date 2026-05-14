import { defineStore } from 'pinia'
import { ref } from 'vue'
import { planApi, type LearningPlan, type PathMode, type ReplanResult } from '@/api/modules/plan'

export const usePlanStore = defineStore('plan', () => {
  const currentPlan = ref<LearningPlan | null>(null)
  const loading = ref(false)
  const lastReplanResult = ref<ReplanResult | null>(null)

  async function generate(projectId: string) {
    loading.value = true
    try {
      currentPlan.value = await planApi.generate(projectId)
    } finally {
      loading.value = false
    }
  }

  async function loadLatest(projectId: string) {
    loading.value = true
    try {
      currentPlan.value = await planApi.getLatest(projectId)
    } finally {
      loading.value = false
    }
  }

  async function replan(
    projectId: string,
    mode: 'progress_aware' | 'profile_update',
    options: { reason?: string; pathMode?: PathMode | string | null } = {},
  ) {
    loading.value = true
    try {
      const result = await planApi.replan(projectId, mode, options.reason, options.pathMode)
      lastReplanResult.value = result
      try {
        currentPlan.value = await planApi.getLatest(projectId)
      } catch (error: any) {
        result.refresh_error = error?.response?.data?.error || '新版路径已保存，但刷新最新路径失败'
      }
      return result
    } finally {
      loading.value = false
    }
  }

  function setLastReplanResult(result: ReplanResult | null) {
    lastReplanResult.value = result
  }

  function clearLastReplanResult() {
    lastReplanResult.value = null
  }

  function reset() {
    currentPlan.value = null
    lastReplanResult.value = null
  }

  return { currentPlan, loading, lastReplanResult, generate, loadLatest, replan, setLastReplanResult, clearLastReplanResult, reset }
})
