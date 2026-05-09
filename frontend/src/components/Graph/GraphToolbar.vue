<template>
  <div class="graph-toolbar">
    <div class="toolbar-main-row">
      <div class="toolbar-primary-group">
        <el-radio-group :model-value="scope" size="small" @change="handleScopeChange">
          <el-radio-button value="path">路径子图</el-radio-button>
          <el-radio-button value="project">项目全图</el-radio-button>
          <el-radio-button value="domain">完整领域图</el-radio-button>
        </el-radio-group>

        <el-input
          v-model="searchKeyword"
          class="toolbar-search"
          placeholder="搜索节点..."
          size="small"
          :prefix-icon="Search"
          clearable
          @input="handleSearch"
          @clear="handleSearch"
        />
      </div>

      <div class="toolbar-action-group">
        <el-button-group>
          <el-button size="small" :icon="ZoomIn" aria-label="放大图谱" @click="emit('zoomIn')" />
          <el-button size="small" :icon="ZoomOut" aria-label="缩小图谱" @click="emit('zoomOut')" />
          <el-button size="small" @click="emit('fitView')">适应</el-button>
        </el-button-group>

        <el-button size="small" :icon="RefreshRight" :loading="loading" :disabled="syncing" @click="emit('refresh')">
          刷新
        </el-button>
        <el-button size="small" type="primary" plain :icon="FullScreen" @click="emit('toggleFullscreen')">
          全屏
        </el-button>

        <el-dropdown trigger="click" @command="handleMoreCommand">
          <el-button size="small" :icon="MoreFilled">更多</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="sync" :disabled="loading || syncing">
                {{ syncing ? '同步中...' : '同步 Neo4j 投影' }}
              </el-dropdown-item>
              <el-dropdown-item command="layout:cose" :disabled="currentLayout === 'cose'">
                布局：力导向
              </el-dropdown-item>
              <el-dropdown-item command="layout:breadthfirst" :disabled="currentLayout === 'breadthfirst'">
                布局：层次
              </el-dropdown-item>
              <el-dropdown-item command="entities" :disabled="entityLoading">
                {{ entityLoading ? '扩展实体加载中...' : '查看扩展实体' }}
              </el-dropdown-item>
              <el-dropdown-item command="overlay">创建图谱扩展草稿</el-dropdown-item>
              <el-dropdown-item :command="reviewMode ? 'review:off' : 'review:on'">
                {{ reviewMode ? '关闭审核模式' : '开启审核模式' }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <div v-if="reviewMode" class="toolbar-review-hint">
      审核模式已开启：右键节点或关系可打开审核菜单。
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ZoomIn, ZoomOut, Search, FullScreen, RefreshRight, MoreFilled } from '@element-plus/icons-vue'
import type { GraphScope } from '@/api/modules/graph'

type GraphLayout = 'cose' | 'breadthfirst'

defineProps<{
  scope: GraphScope
  currentLayout: GraphLayout
  reviewMode?: boolean
  loading?: boolean
  syncing?: boolean
  entityLoading?: boolean
}>()

const emit = defineEmits<{
  scopeChange: [scope: GraphScope]
  refresh: []
  sync: []
  layoutChange: [layout: GraphLayout]
  zoomIn: []
  zoomOut: []
  fitView: []
  search: [keyword: string]
  showEntities: []
  createOverlay: []
  toggleFullscreen: []
  toggleReview: [enabled: boolean]
}>()

const searchKeyword = ref('')

function handleScopeChange(val: string | number | boolean) {
  emit('scopeChange', val as GraphScope)
}

function handleLayoutChange(val: string | number | boolean) {
  emit('layoutChange', val as GraphLayout)
}

function handleMoreCommand(command: string | number | object) {
  const nextCommand = String(command)
  if (nextCommand === 'sync') {
    emit('sync')
    return
  }
  if (nextCommand === 'entities') {
    emit('showEntities')
    return
  }
  if (nextCommand === 'overlay') {
    emit('createOverlay')
    return
  }
  if (nextCommand === 'review:on') {
    emit('toggleReview', true)
    return
  }
  if (nextCommand === 'review:off') {
    emit('toggleReview', false)
    return
  }
  if (nextCommand.startsWith('layout:')) {
    handleLayoutChange(nextCommand.replace('layout:', ''))
  }
}

function handleSearch() {
  emit('search', searchKeyword.value)
}
</script>

<style scoped>
.graph-toolbar {
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-blank);
}

.toolbar-main-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.toolbar-primary-group,
.toolbar-action-group {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.toolbar-primary-group {
  flex: 1;
}

.toolbar-search {
  width: min(260px, 32vw);
}

.toolbar-review-hint {
  margin-top: 6px;
  color: var(--el-color-warning-dark-2);
  font-size: 12px;
}

@media (max-width: 960px) {
  .toolbar-main-row,
  .toolbar-primary-group,
  .toolbar-action-group {
    align-items: flex-start;
    flex-direction: column;
  }

  .toolbar-search {
    width: 100%;
  }
}
</style>
