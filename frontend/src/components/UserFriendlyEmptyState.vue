<template>
  <section class="user-empty-state">
    <el-empty :description="description" :image-size="imageSize">
      <template #default>
        <p v-if="hint" class="user-empty-state__hint">{{ hint }}</p>
        <slot />
      </template>
    </el-empty>
  </section>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  description: string
  hint?: string
  imageSize?: number
}>(), {
  hint: '',
  imageSize: 72,
})
</script>

<style scoped>
.user-empty-state {
  display: grid;
  min-height: 220px;
  place-items: center;
}

.user-empty-state__hint {
  max-width: 420px;
  margin: 0 auto var(--lp-space-3);
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.7;
  text-align: center;
}
</style>
