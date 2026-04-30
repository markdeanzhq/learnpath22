<template>
  <div v-if="state === 'no-project'" class="graph-state-wrap empty-project-wrap">
    <el-empty description="请先在项目页选择一个项目后再查看知识图谱" />
  </div>

  <div v-else-if="state === 'loading'" class="graph-state-wrap graph-loading-state" data-testid="graph-loading-skeleton">
    <div class="graph-skeleton-panel">
      <div class="graph-skeleton-header"></div>
      <div class="graph-skeleton-body">
        <span v-for="index in 8" :key="index" class="graph-skeleton-node"></span>
      </div>
      <p>正在整理知识节点、审核状态与扩展候选，请稍候。</p>
    </div>
  </div>

  <el-empty
    v-else-if="state === 'empty'"
    class="graph-state-wrap"
    :description="emptyDescription"
  >
    <el-button type="primary" @click="emit('refresh')">刷新</el-button>
    <el-button :loading="syncing" @click="emit('sync')">同步图谱</el-button>
  </el-empty>

  <div v-else class="graph-state-wrap">
    <el-result
      icon="error"
      title="知识图谱加载失败"
      :sub-title="errorMessage || '请稍后重试或重新同步图谱'"
    >
      <template #extra>
        <el-space wrap>
          <el-button type="primary" @click="emit('refresh')">重新加载</el-button>
          <el-button :loading="syncing" @click="emit('sync')">同步图谱</el-button>
        </el-space>
      </template>
    </el-result>
  </div>
</template>

<script setup lang="ts">
type GraphStatePanelState = 'no-project' | 'loading' | 'empty' | 'error'

withDefaults(defineProps<{
  state: GraphStatePanelState
  emptyDescription?: string
  errorMessage?: string
  syncing?: boolean
}>(), {
  emptyDescription: '',
  errorMessage: '',
  syncing: false,
})

const emit = defineEmits<{
  refresh: []
  sync: []
}>()
</script>

<style scoped>
.graph-state-wrap,
.empty-project-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 360px;
}

.graph-loading-state {
  padding: 24px;
}

.graph-skeleton-panel {
  width: min(520px, 80%);
  padding: 24px;
  border: 1px solid #ebeef5;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(31 45 61 / 8%);
}

.graph-skeleton-header {
  width: 42%;
  height: 14px;
  margin: 0 auto 24px;
  border-radius: 999px;
  background: linear-gradient(90deg, #ebeef5 25%, #f5f7fa 50%, #ebeef5 75%);
}

.graph-skeleton-body {
  position: relative;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  padding: 12px 32px;
}

.graph-skeleton-node {
  width: 42px;
  height: 42px;
  margin: 0 auto;
  border-radius: 50%;
  background: linear-gradient(135deg, #d9ecff, #ecf5ff);
}

.graph-skeleton-panel p {
  margin: 22px 0 0;
  color: #909399;
  font-size: 13px;
  text-align: center;
}
</style>
