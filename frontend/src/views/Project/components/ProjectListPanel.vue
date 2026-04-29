<template>
  <el-card shadow="never" class="project-list-card">
    <template #header>
      <div class="card-header">
        <div>
          <span class="card-title">我的项目</span>
          <p>选择一个项目继续学习，或创建新的学习路径。</p>
        </div>
        <div class="header-actions">
          <el-button size="small" @click="$emit('search')">搜索资料</el-button>
          <el-button type="primary" size="small" :icon="Plus" @click="$emit('create')">新建</el-button>
        </div>
      </div>
    </template>

    <div v-loading="loading || deletingProjectId !== ''" class="project-card-list">
      <el-empty v-if="!projects.length" description="还没有学习项目">
        <template #default>
          <p class="empty-hint">先创建一个机器学习基础学习计划，系统会引导你完成目标确认和画像采集。</p>
          <el-button type="primary" :icon="Plus" @click="$emit('create')">创建学习项目</el-button>
        </template>
      </el-empty>

      <template v-else>
        <article
          v-for="project in projects"
          :key="project.id"
          class="project-card-item"
          role="button"
          tabindex="0"
          @click="$emit('select', project)"
          @keydown.enter.prevent="$emit('select', project)"
          @keydown.space.prevent="$emit('select', project)"
        >
          <div class="project-card-main">
            <div class="project-card-title-row">
              <h3>{{ project.title }}</h3>
              <el-tag :type="projectStatusMeta(project.status).tagType" size="small" :title="projectStatusMeta(project.status).detail">
                {{ projectStatusMeta(project.status).label }}
              </el-tag>
            </div>
            <p class="project-goal">{{ project.goal_text || '暂未填写学习目标' }}</p>
            <div class="project-meta-row">
              <el-tag size="small" effect="plain">{{ goalTypeLabel(project.goal_type) }}</el-tag>
              <span>{{ projectActionHint(project) }}</span>
            </div>
          </div>
          <div class="project-card-actions">
            <el-button type="primary" link @click.stop="$emit('select', project)">
              {{ project.status === 'extension_review' ? '审核草稿' : '继续学习' }}
            </el-button>
            <el-button
              type="danger"
              link
              :loading="deletingProjectId === project.id"
              @click.stop="$emit('delete', project)"
            >
              删除
            </el-button>
          </div>
        </article>
      </template>
    </div>
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
  const map: Record<string, string> = { domain: '领域型', concept: '概念型', problem: '问题型' }
  return map[type] || '未确定类型'
}

function projectActionHint(project: Project) {
  if (project.status === 'extension_review') {
    return '需要先审核扩展草稿，再考虑增强路径。'
  }
  if (project.status === 'active') {
    return '已有路径进行中，可以继续学习。'
  }
  if (project.status === 'completed') {
    return '学习路径已完成，可回顾进度。'
  }
  return '可继续完成画像或生成学习路径。'
}
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.card-title {
  font-weight: 700;
}

.card-header p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.project-card-list {
  min-height: 160px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty-hint {
  max-width: 280px;
  margin: 0 auto 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.project-card-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: var(--el-fill-color-blank);
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.project-card-item:hover,
.project-card-item:focus-visible {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 8px 18px rgb(64 158 255 / 10%);
  transform: translateY(-1px);
  outline: none;
}

.project-card-main {
  min-width: 0;
  flex: 1;
}

.project-card-title-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: flex-start;
}

.project-card-title-row h3 {
  margin: 0;
  font-size: 15px;
  line-height: 1.4;
}

.project-goal {
  margin: 8px 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.project-meta-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.project-card-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  justify-content: center;
  gap: 4px;
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .card-header {
    gap: 8px;
    flex-wrap: wrap;
  }

  .header-actions {
    justify-content: flex-start;
  }

  .project-card-item,
  .project-card-title-row {
    flex-direction: column;
  }

  .project-card-actions {
    flex-direction: row;
    align-items: center;
    justify-content: flex-start;
  }
}
</style>
