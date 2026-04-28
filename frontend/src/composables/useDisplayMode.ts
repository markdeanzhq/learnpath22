import { computed, ref, watch } from 'vue'

export type DisplayMode = 'simple' | 'defense' | 'debug'

export interface DisplayModeOption {
  value: DisplayMode
  label: string
  description: string
}

const STORAGE_KEY = 'learnpath:display-mode'

export const DISPLAY_MODE_OPTIONS: DisplayModeOption[] = [
  { value: 'simple', label: '普通', description: '只展示用户决策所需信息' },
  { value: 'defense', label: '答辩', description: '展示算法依据与可解释链路' },
  { value: 'debug', label: '调试', description: '展示哈希、审计与内部字段' },
]

function readStoredMode(): DisplayMode {
  if (typeof window === 'undefined') return 'simple'
  const stored = window.localStorage.getItem(STORAGE_KEY)
  return stored === 'defense' || stored === 'debug' ? stored : 'simple'
}

const displayMode = ref<DisplayMode>(readStoredMode())

watch(displayMode, (mode) => {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, mode)
  }
})

export function useDisplayMode() {
  const isSimpleMode = computed(() => displayMode.value === 'simple')
  const isDefenseMode = computed(() => displayMode.value === 'defense')
  const isDebugMode = computed(() => displayMode.value === 'debug')
  const showAuditDetails = computed(() => displayMode.value === 'defense' || displayMode.value === 'debug')
  const showTechnicalDetails = computed(() => displayMode.value === 'debug')

  return {
    displayMode,
    displayModeOptions: DISPLAY_MODE_OPTIONS,
    isSimpleMode,
    isDefenseMode,
    isDebugMode,
    showAuditDetails,
    showTechnicalDetails,
  }
}
