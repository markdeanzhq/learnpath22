<template>
  <section class="overlay-subsection">
    <h4>资源绑定</h4>
    <el-form label-position="top">
      <el-form-item label="资源">
        <el-select :model-value="resourceBinding.resourceId" placeholder="选择资源候选" style="width: 100%" @update:model-value="updateResourceBinding('resourceId', $event)">
          <el-option
            v-for="resource in resources"
            :key="resource.resource_id"
            :label="resource.title"
            :value="resource.resource_id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="绑定目标类型">
        <el-radio-group :model-value="resourceBinding.targetType" @update:model-value="updateResourceBinding('targetType', $event)">
          <el-radio-button value="project_node">项目节点</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="绑定目标">
        <el-select :model-value="resourceBinding.targetId" filterable placeholder="选择知识点或阶段" style="width: 100%" @update:model-value="updateResourceBinding('targetId', $event)">
          <el-option
            v-for="option in resourceTargetOptions"
            :key="option.id"
            :label="option.label"
            :value="option.id"
          >
            <span>{{ option.label }}</span>
            <span class="option-trace-id">{{ option.id }}</span>
          </el-option>
        </el-select>
      </el-form-item>
      <el-button size="small" type="primary" plain @click="emit('bind-resource')">绑定资源</el-button>
    </el-form>
  </section>
</template>

<script setup lang="ts">
import type { OverlayResourceCandidate } from '@/api/modules/graph'
import type { ResourceBindingForm } from './composables/useOverlayPostActions'
import type { ResourceTargetOption } from './overlaySessionPanelTypes'

defineProps<{
  resources: OverlayResourceCandidate[]
  resourceBinding: ResourceBindingForm
  resourceTargetOptions: ResourceTargetOption[]
}>()

const emit = defineEmits<{
  'update-resource-binding': [field: keyof ResourceBindingForm, value: string]
  'bind-resource': []
}>()

function updateResourceBinding(field: keyof ResourceBindingForm, value: unknown) {
  emit('update-resource-binding', field, typeof value === 'string' ? value : String(value ?? ''))
}
</script>

<style scoped>
.overlay-subsection {
  margin-top: 14px;
}

.overlay-subsection h4 {
  margin: 0 0 8px;
  color: #303133;
  font-size: 14px;
}

.option-trace-id {
  float: right;
  margin-left: 12px;
  color: #c0c4cc;
  font-size: 12px;
}
</style>
