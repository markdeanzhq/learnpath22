<template>
  <div class="readiness-capabilities">
    <article
      v-for="card in readinessCapabilityCards"
      :key="card.key"
      class="readiness-capability-card"
    >
      <div class="readiness-capability-header">
        <strong>{{ card.title }}</strong>
        <el-tag size="small" :type="serviceTagType(card.service.status)">
          {{ serviceStatusText(card.key, card.service) }}
        </el-tag>
      </div>
      <p>{{ card.description }}</p>
      <span>{{ serviceReasonText(card.key, card.service) }}</span>
    </article>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ReadinessResponse, ReadinessServiceStatus } from '@/api/modules/health'
import { formatServiceReason } from '@/utils/displayLabels'

const props = defineProps<{
  readiness: ReadinessResponse
}>()

const readinessCapabilityCards = computed(() => {
  const capabilities = props.readiness.capabilities
  return [
    {
      key: 'local_graph_read',
      title: '本地主链',
      description: '项目创建、图谱浏览与路径规划优先走 SQLite 本地读模型和 Domain Pack。',
      service: capabilities.local_graph_read,
    },
    {
      key: 'neo4j_projection',
      title: 'Neo4j 投影',
      description: '仅用于显式同步、投影诊断和图谱展示/审核流程，不阻塞本地主链演示。',
      service: capabilities.neo4j_projection,
    },
    {
      key: 'online_enhancement',
      title: '在线增强',
      description: 'LLM 润色、抽取预览和资料搜索能力，可按网络与密钥情况选择启用。',
      service: capabilities.online_enhancement,
    },
  ]
})

function serviceTagType(status: string) {
  if (status === 'ok') return 'success'
  if (status === 'skipped' || status === 'blocked' || status === 'unknown') return 'warning'
  return 'danger'
}

function serviceStatusText(key: string, service: ReadinessServiceStatus) {
  if (service.ready) {
    return service.status === 'unknown' ? '兼容估算' : '就绪'
  }
  if (key === 'online_enhancement') return '可选配置'
  if (key === 'neo4j_projection') return service.status === 'stale' ? '需同步' : '待同步'
  if (key === 'local_graph_read') return '受阻'
  return '异常'
}

function serviceReasonText(key: string, service: ReadinessServiceStatus) {
  return formatServiceReason(service.reason) || serviceDetail(key, service)
}

function serviceDetail(key: string, service: ReadinessServiceStatus) {
  if (key === 'local_graph_read') {
    return service.reason || 'SQLite 与本地 Domain Pack 组成可演示主链'
  }
  if (key === 'online_enhancement') {
    return service.reason || '在线增强未配置时不影响本地图谱浏览与路径规划'
  }
  if (key === 'neo4j_projection') {
    if (service.in_sync) {
      const domainLabel = service.domain || '当前默认领域'
      return `${domainLabel} Neo4j 投影已同步；本地读模型不依赖该投影`
    }
    return service.reason || '仅影响显式同步、投影诊断和图谱展示/审核流程'
  }
  return service.reason || '能力状态待确认'
}
</script>

<style scoped>
.readiness-capabilities {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
  margin: 10px 0;
}
.readiness-capability-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 10px;
  background: #fafafa;
}
.readiness-capability-header {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}
.readiness-capability-card p {
  margin: 0 0 6px;
  color: #606266;
  line-height: 1.5;
}
.readiness-capability-card span {
  color: #909399;
  font-size: 12px;
}
</style>
