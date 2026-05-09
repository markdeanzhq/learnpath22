<template>
  <article class="compact-metric-card" :class="toneClass">
    <span class="compact-metric-card__label">{{ label }}</span>
    <strong>{{ value }}</strong>
    <small v-if="detail">{{ detail }}</small>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  label: string
  value: string | number
  detail?: string
  tone?: 'primary' | 'success' | 'warning' | 'danger' | 'info'
}>(), {
  detail: '',
  tone: 'info',
})

const toneClass = computed(() => `compact-metric-card--${props.tone}`)
</script>

<style scoped>
.compact-metric-card {
  min-width: 0;
  padding: var(--lp-space-3);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--lp-radius-md);
  background: var(--el-fill-color-light);
}

.compact-metric-card__label,
.compact-metric-card small {
  display: block;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.compact-metric-card strong {
  display: block;
  margin: 3px 0;
  overflow: hidden;
  color: var(--el-text-color-primary);
  font-size: 20px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.compact-metric-card--primary { background: var(--el-color-primary-light-9); }
.compact-metric-card--success { background: var(--el-color-success-light-9); }
.compact-metric-card--warning { background: var(--el-color-warning-light-9); }
.compact-metric-card--danger { background: var(--el-color-danger-light-9); }
</style>
