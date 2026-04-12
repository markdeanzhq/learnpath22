import { defineStore } from 'pinia'
import { ref } from 'vue'
import { profileApi, type LearnerProfile, type SubmitProfileDto, type QuestionItem } from '@/api/modules/profile'

export const useProfileStore = defineStore('profile', () => {
  const currentProfile = ref<LearnerProfile | null>(null)
  const questions = ref<QuestionItem[]>([])
  const loading = ref(false)

  async function submit(projectId: string, data: SubmitProfileDto) {
    loading.value = true
    try {
      currentProfile.value = await profileApi.submit(projectId, data)
    } finally {
      loading.value = false
    }
  }

  async function loadLatest(projectId: string) {
    loading.value = true
    try {
      currentProfile.value = await profileApi.getLatest(projectId)
    } finally {
      loading.value = false
    }
  }

  async function loadQuestions(projectId: string) {
    loading.value = true
    try {
      const data = await profileApi.getQuestions(projectId)
      questions.value = data.questions ?? []
    } finally {
      loading.value = false
    }
  }

  return { currentProfile, questions, loading, submit, loadLatest, loadQuestions }
})
