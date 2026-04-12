import { defineStore } from 'pinia'
import { ref } from 'vue'
import { planApi, type LearningPlan, type ReplanResult } from '@/api/modules/plan'

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

  async function replan(projectId: string, mode: 'progress_aware' | 'profile_update') {
    loading.value = true
    try {
      const result = await planApi.replan(projectId, mode)
      lastReplanResult.value = result
      // 重新加载最新路径
      await loadLatest(projectId)
      return result
    } finally {
      loading.value = false
    }
  }

  function reset() {
    currentPlan.value = null
    lastReplanResult.value = null
  }

  return { currentPlan, loading, lastReplanResult, generate, loadLatest, replan, reset }
})
