<template>
  <div class="graph-toolbar">
    <el-space wrap>
      <el-radio-group :model-value="scope" size="small" @change="handleScopeChange">
        <el-radio-button value="project">项目子图</el-radio-button>
        <el-radio-button value="domain">完整领域图</el-radio-button>
      </el-radio-group>

      <el-button-group>
        <el-button size="small" :icon="RefreshRight" :loading="loading" :disabled="syncing" @click="emit('refresh')">
          刷新
        </el-button>
        <el-button size="small" :icon="Connection" :loading="syncing" :disabled="loading || syncing" @click="emit('sync')">
          同步
        </el-button>
      </el-button-group>

      <el-divider direction="vertical" />

      <el-radio-group :model-value="currentLayout" size="small" @change="handleLayoutChange">
        <el-radio-button value="cose">力导向</el-radio-button>
        <el-radio-button value="breadthfirst">层次</el-radio-button>
      </el-radio-group>

      <el-divider direction="vertical" />

      <el-button-group>
        <el-button size="small" :icon="ZoomIn" @click="emit('zoomIn')" />
        <el-button size="small" :icon="ZoomOut" @click="emit('zoomOut')" />
        <el-button size="small" @click="emit('fitView')">适应</el-button>
      </el-button-group>

      <el-divider direction="vertical" />

      <el-input
        v-model="searchKeyword"
        placeholder="搜索节点..."
        size="small"
        :prefix-icon="Search"
        clearable
        style="width: 180px"
        @input="handleSearch"
        @clear="handleSearch"
      />

      <el-button size="small" :icon="FullScreen" @click="emit('toggleFullscreen')" />

      <el-divider direction="vertical" />

      <el-switch
        :model-value="reviewMode"
        active-text="审核"
        inactive-text=""
        size="small"
        @change="handleReviewToggle"
      />
      <span v-if="reviewMode" class="review-hint">审核模式下右键节点/边打开审核菜单</span>
    </el-space>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ZoomIn, ZoomOut, Search, FullScreen, RefreshRight, Connection } from '@element-plus/icons-vue'

type GraphScope = 'project' | 'domain'
type GraphLayout = 'cose' | 'breadthfirst'

defineProps<{
  scope: GraphScope
  currentLayout: GraphLayout
  reviewMode?: boolean
  loading?: boolean
  syncing?: boolean
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

function handleReviewToggle(val: string | number | boolean) {
  emit('toggleReview', Boolean(val))
}

function handleSearch() {
  emit('search', searchKeyword.value)
}
</script>

<style scoped>
.graph-toolbar {
  padding: 10px 16px;
  background: #fff;
  border-bottom: 1px solid #eee;
}
.review-hint {
  font-size: 12px;
  color: #909399;
}
</style>
