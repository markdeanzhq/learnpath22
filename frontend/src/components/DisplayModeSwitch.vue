<template>
  <div class="display-mode-switch">
    <span class="display-mode-switch__label">展示模式</span>
    <el-radio-group :model-value="modelValue" size="small" @update:model-value="emitMode">
      <el-radio-button
        v-for="option in displayModeOptions"
        :key="option.value"
        :value="option.value"
        :title="option.description"
      >
        {{ option.label }}
      </el-radio-button>
    </el-radio-group>
  </div>
</template>

<script setup lang="ts">
import { DISPLAY_MODE_OPTIONS, type DisplayMode } from '@/composables/useDisplayMode'

defineProps<{
  modelValue: DisplayMode
}>()

const emit = defineEmits<{
  'update:modelValue': [mode: DisplayMode]
}>()

const displayModeOptions = DISPLAY_MODE_OPTIONS

function emitMode(value: string | number | boolean | undefined) {
  if (value === 'simple' || value === 'defense' || value === 'debug') {
    emit('update:modelValue', value)
  }
}
</script>

<style scoped>
.display-mode-switch {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.display-mode-switch__label {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
