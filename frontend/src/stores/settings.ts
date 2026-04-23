import { defineStore } from 'pinia'
import { ref } from 'vue'
import { healthApi, type PutConfigPayload } from '@/api/modules/health'

export interface SettingsLocalSnapshot {
  llm_base_url: string
  llm_model: string
  llm_api_key: string
  search_api_key: string
}

const SETTINGS_STORAGE_KEY = 'learnpath:settings-snapshot'

const createEmptySnapshot = (): SettingsLocalSnapshot => ({
  llm_base_url: '',
  llm_model: '',
  llm_api_key: '',
  search_api_key: '',
})

const SETTINGS_KEYS: Array<keyof SettingsLocalSnapshot> = [
  'llm_base_url',
  'llm_model',
  'llm_api_key',
  'search_api_key',
]

function getStorage() {
  if (typeof window === 'undefined') {
    return null
  }
  return window.localStorage
}

function sanitizeSnapshot(input: unknown): SettingsLocalSnapshot {
  const next = createEmptySnapshot()
  if (!input || typeof input !== 'object') {
    return next
  }

  for (const key of SETTINGS_KEYS) {
    const value = (input as Record<string, unknown>)[key]
    if (typeof value === 'string') {
      next[key] = value.trim()
    }
  }

  return next
}

function sanitizePatch(input: Partial<SettingsLocalSnapshot>): Partial<SettingsLocalSnapshot> {
  const next: Partial<SettingsLocalSnapshot> = {}

  for (const key of SETTINGS_KEYS) {
    const value = input[key]
    if (typeof value === 'string') {
      next[key] = value.trim()
    }
  }

  return next
}

function toPayload(snapshot: SettingsLocalSnapshot): PutConfigPayload {
  return Object.fromEntries(
    Object.entries(snapshot).filter(([, value]) => value.trim()),
  ) as PutConfigPayload
}

export const useSettingsStore = defineStore('settings', () => {
  const savedConfig = ref<SettingsLocalSnapshot>(createEmptySnapshot())
  const llmApiKeySet = ref(false)
  const searchApiKeySet = ref(false)
  const llmExplanationPolish = ref(false)

  function hydrateFromLocal() {
    const storage = getStorage()
    if (!storage) {
      savedConfig.value = createEmptySnapshot()
      return savedConfig.value
    }

    const raw = storage.getItem(SETTINGS_STORAGE_KEY)
    if (!raw) {
      savedConfig.value = createEmptySnapshot()
      return savedConfig.value
    }

    try {
      savedConfig.value = sanitizeSnapshot(JSON.parse(raw))
      return savedConfig.value
    } catch {
      storage.removeItem(SETTINGS_STORAGE_KEY)
      savedConfig.value = createEmptySnapshot()
      return savedConfig.value
    }
  }

  function savePatchToLocal(patch: Partial<SettingsLocalSnapshot>) {
    const storage = getStorage()
    const next = {
      ...savedConfig.value,
      ...sanitizePatch(patch),
    }

    savedConfig.value = next
    storage?.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(next))
    return next
  }

  function clearLocalSavedConfig() {
    savedConfig.value = createEmptySnapshot()
    getStorage()?.removeItem(SETTINGS_STORAGE_KEY)
  }

  async function bootstrapSyncToBackend() {
    const snapshot = hydrateFromLocal()
    const payload = toPayload(snapshot)

    if (!Object.keys(payload).length) {
      return
    }

    try {
      await healthApi.updateConfigSilently(payload)
    } catch (error) {
      console.warn('Failed to bootstrap local settings to backend.', error)
    }
  }

  async function refreshServerStatus() {
    try {
      const data = await healthApi.getConfigSilently()
      llmApiKeySet.value = data.llm_api_key_set
      searchApiKeySet.value = data.search_api_key_set
      llmExplanationPolish.value = data.llm_explanation_polish
    } catch {
      // keep last known values on failure
    }
  }

  return {
    savedConfig,
    llmApiKeySet,
    searchApiKeySet,
    llmExplanationPolish,
    hydrateFromLocal,
    savePatchToLocal,
    clearLocalSavedConfig,
    bootstrapSyncToBackend,
    refreshServerStatus,
  }
})
