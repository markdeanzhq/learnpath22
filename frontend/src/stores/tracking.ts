import { defineStore } from 'pinia'
import { ref } from 'vue'
import { trackingApi, type TrackingEvent, type TrackingEventResponse, type TrackingSummary } from '@/api/modules/tracking'

export const useTrackingStore = defineStore('tracking', () => {
  const events = ref<TrackingEventResponse[]>([])
  const summary = ref<TrackingSummary | null>(null)
  const loading = ref(false)

  async function addEvent(projectId: string, data: TrackingEvent) {
    loading.value = true
    try {
      await trackingApi.addEvent(projectId, data)
    } finally {
      loading.value = false
    }
  }

  async function loadEvents(projectId: string) {
    loading.value = true
    try {
      events.value = await trackingApi.getEvents(projectId)
    } finally {
      loading.value = false
    }
  }

  async function loadSummary(projectId: string) {
    loading.value = true
    try {
      summary.value = await trackingApi.getSummary(projectId)
    } finally {
      loading.value = false
    }
  }

  function reset() {
    events.value = []
    summary.value = null
  }

  return { events, summary, loading, addEvent, loadEvents, loadSummary, reset }
})
