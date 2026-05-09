<template>
  <article class="next-action-card">
    <span class="next-action-card__eyebrow">下一步建议</span>
    <strong>{{ title }}</strong>
    <p v-if="description">{{ description }}</p>
    <div v-if="$slots.default" class="next-action-card__actions">
      <slot />
    </div>
  </article>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<style scoped>
.next-action-card {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 260px;
  max-width: 360px;
  padding: var(--lp-space-3);
  border: 1px solid var(--el-color-success-light-5);
  border-radius: var(--lp-radius-md);
  background: linear-gradient(135deg, var(--el-color-success-light-9), var(--el-fill-color-blank));
}

.next-action-card__eyebrow {
  color: var(--el-color-success);
  font-size: 12px;
  font-weight: 700;
}

.next-action-card strong {
  margin-top: 4px;
  color: var(--el-text-color-primary);
  font-size: 16px;
  line-height: 1.4;
}

.next-action-card p {
  display: -webkit-box;
  margin: 5px 0 0;
  overflow: hidden;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.next-action-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--lp-space-2);
  margin-top: var(--lp-space-2);
}

@media (max-width: 960px) {
  .next-action-card {
    max-width: none;
  }
}
</style>
