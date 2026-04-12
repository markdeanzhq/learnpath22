import { defineStore } from 'pinia'
import { ref } from 'vue'
import { projectApi, type Project, type CreateProjectDto } from '@/api/modules/project'

export const useProjectStore = defineStore('project', () => {
  const currentProject = ref<Project | null>(null)
  const projects = ref<Project[]>([])
  const loading = ref(false)

  function setCurrentProject(project: Project | null) {
    currentProject.value = project
  }

  function clearCurrentProject() {
    currentProject.value = null
  }

  async function create(data: CreateProjectDto) {
    loading.value = true
    try {
      currentProject.value = await projectApi.create(data)
      return currentProject.value
    } finally {
      loading.value = false
    }
  }

  async function loadById(id: string) {
    loading.value = true
    try {
      currentProject.value = await projectApi.get(id)
    } finally {
      loading.value = false
    }
  }

  async function loadList() {
    loading.value = true
    try {
      projects.value = await projectApi.list()
    } finally {
      loading.value = false
    }
  }

  async function deleteProject(id: string) {
    loading.value = true
    try {
      await projectApi.delete(id)
      projects.value = projects.value.filter((project) => project.id !== id)
      if (currentProject.value?.id === id) {
        clearCurrentProject()
      }
    } finally {
      loading.value = false
    }
  }

  return {
    currentProject,
    projects,
    loading,
    setCurrentProject,
    clearCurrentProject,
    create,
    loadById,
    loadList,
    deleteProject,
  }
})
