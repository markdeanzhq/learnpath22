<template>
  <el-drawer v-model="visible" title="扩展实体" :size="520" direction="rtl">
    <div class="drawer-content" v-loading="loading">
      <template v-if="metadata && !metadata.is_empty">
        <section class="drawer-section">
          <div class="section-header">
            <div>
              <h3>Stage 模板</h3>
              <p>领域级默认阶段模板，只读展示，不进入审核流程</p>
            </div>
            <el-tag type="info">{{ metadata.stages.length }} 个</el-tag>
          </div>

          <div class="entity-list">
            <article v-for="stage in metadata.stages" :key="stage.id" class="entity-card">
              <div class="entity-card-header">
                <div>
                  <div class="entity-title">{{ stage.order }}. {{ stage.name }}</div>
                  <div class="entity-subtitle">追溯 ID：{{ stage.id }}</div>
                </div>
                <el-tag size="small">{{ stage.node_ids.length }} 节点</el-tag>
              </div>
              <p class="entity-description">{{ stage.description || '未提供说明' }}</p>
              <div class="entity-meta-row">
                <span class="meta-label">分类键</span>
                <div class="chip-list">
                  <el-tag v-for="category in stage.category_keys" :key="category" size="small" effect="plain">
                    {{ category }}
                  </el-tag>
                </div>
              </div>
              <div class="entity-meta-row">
                <span class="meta-label">资源</span>
                <div class="chip-list">
                  <el-tag
                    v-for="resourceId in stage.resource_ids"
                    :key="resourceId"
                    size="small"
                    type="success"
                    effect="plain"
                  >
                    {{ resourceTitleById.get(resourceId) || resourceId }}
                  </el-tag>
                  <span v-if="stage.resource_ids.length === 0" class="meta-empty">暂无关联资源</span>
                </div>
              </div>
            </article>
          </div>
        </section>

        <section class="drawer-section">
          <div class="section-header">
            <div>
              <h3>Curated Resource</h3>
              <p>领域级资料元数据，只读展示，不写回审核状态</p>
            </div>
            <el-tag type="success">{{ metadata.resources.length }} 个</el-tag>
          </div>

          <div class="entity-list">
            <article v-for="resource in metadata.resources" :key="resource.id" class="entity-card">
              <div class="entity-card-header">
                <div>
                  <div class="entity-title">{{ resource.title }}</div>
                  <div class="entity-subtitle">追溯 ID：{{ resource.id }}</div>
                </div>
                <el-tag size="small" :type="resourceTypeMeta(resource.resource_type).tagType" :title="resource.resource_type">
                  {{ resourceTypeMeta(resource.resource_type).label }}
                </el-tag>
              </div>
              <p class="entity-description">{{ resource.description || '未提供说明' }}</p>
              <div class="entity-meta-row">
                <span class="meta-label">Stage</span>
                <div class="chip-list">
                  <el-tag v-for="stageId in resource.stage_ids" :key="stageId" size="small" effect="plain">
                    {{ stageId }}
                  </el-tag>
                </div>
              </div>
              <div class="entity-meta-row">
                <span class="meta-label">节点数</span>
                <span>{{ resource.node_ids.length }}</span>
              </div>
            </article>
          </div>
        </section>
      </template>

      <el-empty
        v-else-if="!loading"
        description="当前领域暂无扩展实体数据，可先同步图谱后再查看"
      />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { GraphEntityMetadata } from '@/api/modules/graph'
import { resourceTypeMeta } from '@/utils/displayLabels'

const props = defineProps<{
  modelValue: boolean
  loading?: boolean
  metadata: GraphEntityMetadata | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const resourceTitleById = computed(() => new Map(
  (props.metadata?.resources ?? []).map((resource) => [resource.id, resource.title]),
))
</script>

<style scoped>
.drawer-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 200px;
}

.drawer-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.section-header h3 {
  margin: 0;
  font-size: 16px;
  color: #303133;
}

.section-header p {
  margin: 4px 0 0;
  font-size: 12px;
  color: #909399;
}

.entity-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.entity-card {
  border: 1px solid #ebeef5;
  border-radius: 12px;
  padding: 14px;
  background: #fff;
}

.entity-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.entity-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.entity-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}

.entity-description {
  margin: 12px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: #606266;
}

.entity-meta-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 12px;
}

.meta-label {
  min-width: 52px;
  font-size: 12px;
  color: #909399;
  line-height: 24px;
}

.chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.meta-empty {
  font-size: 12px;
  color: #c0c4cc;
  line-height: 24px;
}
</style>
