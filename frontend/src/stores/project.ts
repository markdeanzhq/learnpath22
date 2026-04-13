import { defineStore } from 'pinia'
import { ref } from 'vue'
import { projectApi, type Project, type CreateProjectDto } from '@/api/modules/project'

const CURRENT_PROJECT_STORAGE_KEY = 'learnpath:current-project'

function getStorage() {
  if (typeof window === 'undefined') {
    return null
  }
  return window.localStorage
}

function sanitizeProject(input: unknown): Project | null {
  if (!input || typeof input !== 'object') {
    return null
  }

  const raw = input as Record<string, unknown>
  if (typeof raw.id !== 'string' || !raw.id.trim()) {
    return null
  }

  return {
    id: raw.id,
    title: typeof raw.title === 'string' ? raw.title : '',
    goal_text: typeof raw.goal_text === 'string' ? raw.goal_text : '',
    goal_type: typeof raw.goal_type === 'string' ? raw.goal_type : '',
    domain: typeof raw.domain === 'string' ? raw.domain : '',
    status: typeof raw.status === 'string' ? raw.status : '',
    created_at: typeof raw.created_at === 'string' ? raw.created_at : '',
  }
}

function readStoredCurrentProject(): Project | null {
  const storage = getStorage()
  const raw = storage?.getItem(CURRENT_PROJECT_STORAGE_KEY)

  if (!raw) {
    return null
  }

  try {
    const project = sanitizeProject(JSON.parse(raw))
    if (!project) {
      storage?.removeItem(CURRENT_PROJECT_STORAGE_KEY)
    }
    return project
  } catch {
    storage?.removeItem(CURRENT_PROJECT_STORAGE_KEY)
    return null
  }
}

function persistCurrentProject(project: Project | null) {
  const storage = getStorage()
  if (!storage) {
    return
  }

  if (!project) {
    storage.removeItem(CURRENT_PROJECT_STORAGE_KEY)
    return
  }

  storage.setItem(CURRENT_PROJECT_STORAGE_KEY, JSON.stringify(project))
}

export const useProjectStore = defineStore('project', () => {
  const currentProject = ref<Project | null>(readStoredCurrentProject())
  const projects = ref<Project[]>([])
  const loading = ref(false)

  function setCurrentProject(project: Project | null) {
    currentProject.value = project
    persistCurrentProject(project)
  }

  function clearCurrentProject() {
    setCurrentProject(null)
  }

  async function create(data: CreateProjectDto) {
    loading.value = true
    try {
      const project = await projectApi.create(data)
      setCurrentProject(project)
      return project
    } finally {
      loading.value = false
    }
  }

  async function loadById(id: string) {
    loading.value = true
    try {
      const project = await projectApi.get(id)
      setCurrentProject(project)
    } finally {
      loading.value = false
    }
  }

  async function loadList() {
    loading.value = true
    try {
      const nextProjects = await projectApi.list()
      projects.value = nextProjects

      if (!currentProject.value) {
        return
      }

      const matchedProject = nextProjects.find((project) => project.id === currentProject.value?.id)
      if (!matchedProject) {
        clearCurrentProject()
        return
      }

      setCurrentProject(matchedProject)
    } finally {
      loading.value = false
    }
  }

  async function restoreCurrentProject() {
    const storedProjectId = currentProject.value?.id
    if (!storedProjectId) {
      return null
    }

    loading.value = true
    try {
      const project = await projectApi.get(storedProjectId)
      setCurrentProject(project)
      return project
    } catch {
      clearCurrentProject()
      return null
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
    restoreCurrentProject,
    deleteProject,
  }
})
