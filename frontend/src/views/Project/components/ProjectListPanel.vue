<template>
  <el-card shadow="never">
    <template #header>
      <div class="card-header">
        <span>我的项目</span>
        <div class="header-actions">
          <el-button size="small" @click="$emit('search')">搜索资料</el-button>
          <el-button type="primary" size="small" :icon="Plus" @click="$emit('create')">新建</el-button>
        </div>
      </div>
    </template>

    <el-table
      :data="projects"
      v-loading="loading || deletingProjectId !== ''"
      empty-text="暂无项目"
      highlight-current-row
      style="cursor: pointer"
      @row-click="$emit('select', $event)"
    >
      <el-table-column prop="title" label="标题" />
      <el-table-column prop="goal_type" label="类型" width="80">
        <template #default="{ row }">
          <el-tag size="small">{{ goalTypeLabel(row.goal_type) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="projectStatusMeta(row.status).tagType" size="small" :title="projectStatusMeta(row.status).detail">
            {{ projectStatusMeta(row.status).label }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="90" align="center">
        <template #default="{ row }">
          <el-button
            type="danger"
            link
            :loading="deletingProjectId === row.id"
            @click.stop="$emit('delete', row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
import { Plus } from '@element-plus/icons-vue'
import type { Project } from '@/api/modules/project'
import { projectStatusMeta } from '@/utils/displayLabels'

defineProps<{
  projects: Project[]
  loading: boolean
  deletingProjectId: string
}>()

defineEmits<{
  search: []
  create: []
  select: [project: Project]
  delete: [project: Project]
}>()

function goalTypeLabel(type: string) {
  const map: Record<string, string> = { domain: '领域', concept: '概念', problem: '问题' }
  return map[type] || type
}
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .card-header {
    gap: 8px;
    flex-wrap: wrap;
  }
}
</style>
