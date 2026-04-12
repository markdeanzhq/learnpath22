<template>
  <el-drawer v-model="visible" title="节点详情" :size="320" direction="rtl">
    <template v-if="node">
      <div class="detail-content">
        <h3>{{ node.label }}</h3>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="类别">
            <el-tag :color="categoryColor" effect="dark" size="small" style="color: #fff">
              {{ categoryLabel }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="难度">
            <el-rate :model-value="node.difficulty" disabled :max="5" size="small" />
          </el-descriptions-item>
          <el-descriptions-item label="重要性">
            <el-rate :model-value="node.importance" disabled :max="5" size="small" />
          </el-descriptions-item>
          <el-descriptions-item v-if="node.estimated_hours" label="预计学时">
            {{ node.estimated_hours }} 小时
          </el-descriptions-item>
          <el-descriptions-item label="主路径">
            <el-tag :type="node.is_main_path ? 'success' : 'info'" size="small">
              {{ node.is_main_path ? '是' : '否' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const CATEGORY_COLORS: Record<string, string> = {
  foundation: '#E6A23C',
  math_foundation: '#409EFF',
  ml_core: '#F56C6C',
  algorithm: '#8B5CF6',
  evaluation: '#909399',
  practice: '#67C23A',
}

const CATEGORY_LABELS: Record<string, string> = {
  foundation: '编程基础',
  math_foundation: '数学基础',
  ml_core: '机器学习核心',
  algorithm: '核心算法',
  evaluation: '评估与泛化',
  practice: '实践应用',
}

const props = defineProps<{ node: any | null }>()
const visible = ref(false)

watch(() => props.node, (val) => {
  visible.value = !!val
})

const categoryColor = computed(() => CATEGORY_COLORS[props.node?.category] || '#909399')
const categoryLabel = computed(() => CATEGORY_LABELS[props.node?.category] || props.node?.category || '')
</script>

<style scoped>
.detail-content { padding: 0 10px; }
.detail-content h3 { margin: 0 0 16px 0; font-size: 18px; color: #303133; }
</style>
