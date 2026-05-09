<template>
  <div class="page-shell" :class="{ 'page-shell--fill': fill }">
    <section class="page-shell__header">
      <div class="page-shell__title-block">
        <p v-if="eyebrow" class="page-shell__eyebrow">{{ eyebrow }}</p>
        <h1>{{ title }}</h1>
        <p v-if="subtitle" class="page-shell__subtitle">{{ subtitle }}</p>
      </div>
      <div class="page-shell__actions">
        <slot name="actions" />
      </div>
    </section>

    <section v-if="$slots.summary" class="page-shell__summary">
      <slot name="summary" />
    </section>

    <section class="page-shell__main">
      <slot />
    </section>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  title: string
  subtitle?: string
  eyebrow?: string
  fill?: boolean
}>(), {
  subtitle: '',
  eyebrow: '',
  fill: true,
})
</script>

<style scoped>
.page-shell {
  display: flex;
  flex-direction: column;
  gap: var(--lp-space-4);
  padding: var(--lp-page-padding);
}

.page-shell--fill {
  min-height: calc(100vh - var(--lp-header-height));
}

.page-shell__header,
.page-shell__summary,
.page-shell__main {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--lp-radius-lg);
  background: var(--el-fill-color-blank);
}

.page-shell__header {
  display: flex;
  justify-content: space-between;
  gap: var(--lp-space-4);
  align-items: center;
  min-height: 76px;
  padding: var(--lp-space-4) var(--lp-space-5);
}

.page-shell__title-block {
  min-width: 0;
}

.page-shell__eyebrow {
  margin: 0 0 var(--lp-space-1);
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.page-shell__header h1 {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: var(--lp-font-xl);
  line-height: 1.3;
}

.page-shell__subtitle {
  display: -webkit-box;
  max-width: 760px;
  margin: var(--lp-space-1) 0 0;
  overflow: hidden;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.page-shell__actions {
  display: flex;
  flex-wrap: wrap;
  flex-shrink: 0;
  justify-content: flex-end;
  gap: var(--lp-space-2);
}

.page-shell__summary {
  padding: var(--lp-space-3) var(--lp-space-4);
}

.page-shell__main {
  flex: 1;
  min-height: 0;
  padding: var(--lp-space-4);
  overflow: hidden;
}

@media (max-width: 768px) {
  .page-shell {
    padding: var(--lp-space-3);
  }

  .page-shell--fill {
    min-height: auto;
  }

  .page-shell__header {
    align-items: flex-start;
    flex-direction: column;
  }

  .page-shell__actions {
    justify-content: flex-start;
  }

  .page-shell__main {
    overflow: visible;
  }
}
</style>
