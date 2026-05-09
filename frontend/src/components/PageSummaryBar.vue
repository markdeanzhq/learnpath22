<template>
  <section class="page-summary-bar" aria-label="页面摘要">
    <div class="page-summary-bar__metrics">
      <CompactMetricCard
        v-for="item in items"
        :key="item.label"
        :label="item.label"
        :value="item.value"
        :detail="item.detail"
        :tone="item.tone"
      />
    </div>
    <slot />
  </section>
</template>

<script setup lang="ts">
import CompactMetricCard from './CompactMetricCard.vue'

interface SummaryItem {
  label: string
  value: string | number
  detail?: string
  tone?: 'primary' | 'success' | 'warning' | 'danger' | 'info'
}

defineProps<{
  items: SummaryItem[]
}>()
</script>

<style scoped>
.page-summary-bar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--lp-space-3);
  align-items: stretch;
}

.page-summary-bar__metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--lp-space-3);
  min-width: 0;
}

@media (max-width: 960px) {
  .page-summary-bar {
    grid-template-columns: 1fr;
  }
}
</style>
