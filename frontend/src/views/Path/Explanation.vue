<template>
  <div
    class="explanation-section"
    v-loading="loading"
    element-loading-text="正在加载规划解释..."
  >
    <el-alert
      v-if="showPolishUnavailable"
      type="warning"
      title="当前无法应用 AI 润色"
      :closable="false"
      show-icon
      class="section-gap"
    >
      <template #default>
        {{ polishUnavailableMessage }}
      </template>
    </el-alert>

    <el-alert
      v-if="error"
      type="error"
      :title="error"
      :closable="false"
      show-icon
      class="section-gap"
    >
      <template #default>
        {{ explanation ? '解释刷新失败，当前保留最近一次成功结果。' : '解释加载失败，请关闭 AI 润色或稍后重试。' }}
        <el-button link type="primary" @click="emit('retry')">重试</el-button>
      </template>
    </el-alert>

    <el-empty v-if="!explanation && !loading" description="暂无路径解释数据" />

    <div v-if="isPolishLoading" class="polish-loading-card section-gap" role="status" aria-live="polite">
      <div class="polish-loading-card__halo">AI</div>
      <div class="polish-loading-card__body">
        <div class="polish-loading-card__title">正在润色路径解释</div>
        <p>{{ polishLoadingMessage }}</p>
        <div class="polish-loading-steps">
          <span>规则解释已生成</span>
          <span>发送给 LLM</span>
          <span>等待自然语言改写</span>
        </div>
        <div class="polish-loading-bar"><span /></div>
      </div>
    </div>

    <div v-if="showInitialPolishSkeleton" class="polish-skeleton section-gap" aria-hidden="true">
      <div class="skeleton-line skeleton-line-title" />
      <div class="skeleton-line" />
      <div class="skeleton-line skeleton-line-short" />
    </div>

    <template v-else-if="explanation">
      <div class="polish-toolbar section-gap">
        <el-switch
          :model-value="polishRequested"
          active-text="AI 润色"
          inline-prompt
          @change="onPolishChange"
        />
        <el-tag v-if="polishStatusLabel" size="small" :type="polishStatusType">
          {{ polishStatusLabel }}
        </el-tag>
        <span class="polish-hint" v-if="polishHint">
          {{ polishHint }}
        </span>
      </div>

      <section class="defense-guide section-gap" aria-label="规划解释答辩导览">
        <div class="defense-guide-main">
          <p class="defense-eyebrow">答辩导览</p>
          <h3>路径为何成立</h3>
          <p>{{ overview.headline }}</p>
        </div>
        <div class="defense-card-grid">
          <article v-for="item in defenseGuideCards" :key="item.title" class="defense-card">
            <span>{{ item.title }}</span>
            <strong>{{ item.value }}</strong>
            <small>{{ item.detail }}</small>
          </article>
        </div>
        <div class="defense-talking-points" aria-label="推荐讲述顺序">
          <strong>推荐讲述顺序</strong>
          <ol>
            <li v-for="point in defenseTalkingPoints" :key="point">{{ point }}</li>
          </ol>
        </div>
      </section>

      <el-card shadow="never" class="overview-card section-gap">
        <template #header>
          <div class="section-header">
            <span>路径解释摘要</span>
            <el-tag size="small" type="info">规则优先</el-tag>
          </div>
        </template>
        <h3 class="headline">{{ overview.headline }}</h3>
        <div class="overview-tags">
          <el-tag v-for="goal in overview.goalNames" :key="goal" type="success" effect="plain">
            {{ goal }}
          </el-tag>
          <el-tag :type="budgetTagTypeByStatus(overview.budgetStatus)" effect="plain">
            {{ formatBudgetStatus(overview.budgetStatus) }}
          </el-tag>
          <el-tag effect="plain">{{ formatPathMode(overview.pathMode) }}</el-tag>
        </div>
        <el-row :gutter="12" class="metric-grid">
          <el-col :xs="12" :sm="6">
            <div class="metric-card">
              <span class="metric-label">知识点数</span>
              <strong>{{ overview.nodeCount }}</strong>
            </div>
          </el-col>
          <el-col :xs="12" :sm="6">
            <div class="metric-card">
              <span class="metric-label">总学时</span>
              <strong>{{ formatHours(overview.totalHours) }}</strong>
            </div>
          </el-col>
          <el-col :xs="12" :sm="6">
            <div class="metric-card">
              <span class="metric-label">润色状态</span>
              <strong>{{ polishApplied ? '已应用' : '规则文本' }}</strong>
            </div>
          </el-col>
          <el-col v-if="showAuditDetails" :xs="12" :sm="6">
            <div class="metric-card">
              <span class="metric-label">追溯来源</span>
              <strong>{{ traceSourceLabel }}</strong>
            </div>
          </el-col>
        </el-row>
        <ul v-if="overview.notes.length" class="note-list">
          <li v-for="note in overview.notes" :key="note">{{ note }}</li>
        </ul>
      </el-card>

      <el-card v-if="showAuditDetails" shadow="never" class="section-gap">
        <template #header>
          <div class="section-header">
            <span>路径生成流程</span>
            <el-tag size="small" type="success">固定 6 步</el-tag>
          </div>
        </template>
        <el-timeline v-if="displayGenerationSteps.length">
          <el-timeline-item
            v-for="step in displayGenerationSteps"
            :key="step.step_id"
            :timestamp="step.title"
            placement="top"
          >
            <p class="step-summary">{{ step.summary }}</p>
            <div class="evidence-list" v-if="step.evidence_items.length || step.nodeRefs.length">
              <el-tag v-for="item in step.evidence_items" :key="item" size="small" effect="plain">
                {{ item }}
              </el-tag>
              <el-tag
                v-for="node in step.nodeRefs"
                :key="node.node_id"
                size="small"
                :type="node.unresolved ? 'warning' : 'info'"
                effect="plain"
                class="node-name-tag"
                :title="node.traceTitle"
                :aria-label="node.traceTitle"
              >
                {{ node.label }}
              </el-tag>
            </div>
          </el-timeline-item>
        </el-timeline>
        <p v-if="hasGenerationStepNodeRefs" class="node-id-note">
          说明：知识点标签优先展示中文名称；内部节点 ID 可通过悬停查看，用于审计追溯，不代表学习顺序。
        </p>
        <el-empty v-else description="暂无生成步骤摘要" />
      </el-card>

      <el-card shadow="never" class="section-gap">
        <template #header>
          <div class="section-header">
            <span>节点纳入原因</span>
            <el-tag size="small" type="warning">目标 / 前置 / 补强</el-tag>
          </div>
        </template>
        <el-row :gutter="12">
          <el-col
            v-for="group in displayNodeGroups"
            :key="group.group_id"
            :xs="24"
            :md="8"
          >
            <div class="node-group-card">
              <div class="node-group-title">
                <strong>{{ group.title }}</strong>
                <el-tag size="small" effect="plain">{{ group.nodes.length }} 个</el-tag>
              </div>
              <p class="summary-text">{{ group.summary }}</p>
              <div class="node-list" v-if="group.nodes.length">
                <div v-for="node in group.nodes" :key="node.node_id" class="node-item">
                  <span class="node-name">{{ node.node_name }}</span>
                  <span v-if="node.reason" class="node-reason">{{ node.reason }}</span>
                </div>
              </div>
              <el-empty v-else description="暂无节点" :image-size="48" />
            </div>
          </el-col>
        </el-row>
      </el-card>

      <el-row :gutter="12" class="section-gap">
        <el-col :xs="24" :lg="8">
          <el-card shadow="never" class="summary-card">
            <template #header>排序依据</template>
            <p class="summary-text">{{ orderingSummaryText }}</p>
            <div class="evidence-list" v-if="orderingFactors.length">
              <el-tag v-for="factor in orderingFactors" :key="factor" size="small" effect="plain">
                {{ factor }}
              </el-tag>
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :lg="8">
          <el-card shadow="never" class="summary-card">
            <template #header>阶段划分</template>
            <p class="summary-text">{{ stageSummaryText }}</p>
            <div class="stage-mini-list" v-if="stageCards.length">
              <div v-for="stage in stageCards" :key="stage.key" class="stage-mini-item">
                <strong>{{ stage.title }}</strong>
                <span>{{ stage.summary }}</span>
              </div>
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :lg="8">
          <el-card shadow="never" class="summary-card">
            <template #header>时间预算</template>
            <p class="summary-text">{{ budgetSummaryText }}</p>
            <div class="budget-meta" v-if="budgetSummary">
              <el-tag :type="budgetTagTypeByStatus(budgetSummary.status)" effect="plain">
                {{ formatBudgetStatus(budgetSummary.status) }}
              </el-tag>
              <span>{{ formatHours(budgetSummary.total_hours) }}</span>
              <span v-if="budgetSummary.estimated_weeks != null">约 {{ budgetSummary.estimated_weeks }} 周</span>
            </div>
            <el-alert
              v-if="budgetSummary?.compressed_dependency_note"
              type="info"
              :closable="false"
              show-icon
              class="compact-alert"
            >
              {{ budgetSummary.compressed_dependency_note }}
            </el-alert>
          </el-card>
        </el-col>
      </el-row>

      <el-card shadow="never" class="section-gap">
        <template #header>
          <div class="section-header">
            <span>AI 辅助解释</span>
            <el-tag size="small" type="info">预设问题</el-tag>
          </div>
        </template>
        <el-alert
          title="AI 只辅助解释当前路径，不会修改路径、排序或学习计划。"
          type="info"
          :closable="false"
          show-icon
          class="section-gap-small"
        />
        <div class="question-grid">
          <el-button
            v-for="question in genericQuestions"
            :key="question.question_id"
            :loading="askLoading"
            @click="askQuestion({ question_id: question.question_id })"
          >
            {{ question.label }}
          </el-button>
        </div>
        <div v-if="nodeQuestionTargets.length" class="node-question-list">
          <div v-for="node in nodeQuestionTargets" :key="node.node_id" class="node-question-item">
            <span>{{ node.node_name }}</span>
            <div>
              <el-button size="small" :loading="askLoading" @click="askQuestion({ question_id: 'why_include_node', node_id: node.node_id })">
                为什么纳入
              </el-button>
              <el-button size="small" :loading="askLoading" @click="askQuestion({ question_id: 'why_stage_assignment', node_id: node.node_id })">
                为什么在此阶段
              </el-button>
            </div>
          </div>
        </div>
        <el-alert v-if="askError" type="error" :title="askError" :closable="false" show-icon class="section-gap-small" />
        <div v-if="askResponse" class="ask-answer">
          <div class="ask-answer-header">
            <strong>{{ formatQuestionId(askResponse.question_id) }}</strong>
            <el-tag size="small" :type="askResponse.ai_used ? 'success' : 'info'">
              {{ askResponse.ai_used ? 'AI 已参与' : '规则回答' }}
            </el-tag>
          </div>
          <p>{{ askResponse.answer }}</p>
          <div class="evidence-list" v-if="askResponse.evidence_refs.length">
            <el-tag
              v-for="ref in askResponse.evidence_refs"
              :key="`${ref.source}-${ref.key}-${ref.node_id}`"
              size="small"
              effect="plain"
              :title="evidenceTraceTitle(ref)"
            >
              {{ evidenceRefLabel(ref) }}
            </el-tag>
          </div>
          <ul v-if="askResponse.limitations.length" class="note-list">
            <li v-for="item in askResponse.limitations" :key="item">{{ item }}</li>
          </ul>
        </div>
      </el-card>

      <el-card v-if="showTechnicalDetails" shadow="never" class="section-gap">
        <template #header>
          <div class="section-header">
            <span>原始规则文本对照</span>
            <el-tag size="small" type="warning">raw_*</el-tag>
          </div>
        </template>
        <el-collapse v-if="rawExplanationEntries.length" v-model="activeRawPanels">
          <el-collapse-item
            v-for="item in rawExplanationEntries"
            :key="item.key"
            :title="item.title"
            :name="item.key"
          >
            <p class="summary-text">当前展示：{{ item.currentText }}</p>
            <pre class="audit-value raw-value">{{ item.rawText }}</pre>
          </el-collapse-item>
        </el-collapse>
        <el-empty v-else description="暂无 raw_reason / raw_rationale 对照" />
      </el-card>

      <el-card v-if="showTechnicalDetails" shadow="never" class="section-gap">
        <template #header>
          <div class="section-header">
            <span>高级审计依据</span>
            <el-tag size="small" type="info">默认折叠</el-tag>
          </div>
        </template>
        <el-collapse v-if="auditHighlights.length" v-model="activeAuditPanels">
          <el-collapse-item
            v-for="item in auditHighlights"
            :key="item.key"
            :title="item.title"
            :name="item.key"
          >
            <p class="summary-text">{{ item.summary }}</p>
            <p v-if="item.source" class="muted-text" :title="`原始来源：${item.source}`">
              来源：{{ auditSourceLabel(item.source).label }}
            </p>
            <pre v-if="formatAuditValue(item.value)" class="audit-value">{{ formatAuditValue(item.value) }}</pre>
          </el-collapse-item>
        </el-collapse>
        <el-empty v-else description="暂无审计高亮" />
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { auditSourceLabel } from '@/utils/displayLabels'
import type { DisplayMode } from '@/composables/useDisplayMode'
import type {
  AuditHighlight,
  EvidenceRef,
  ExplanationAskRequest,
  ExplanationAskResponse,
  ExplanationQuestionId,
  ExplanationResponse,
  ReadableBudgetSummary,
} from '@/api/modules/plan'
import type { ExplanationAiAvailability } from './useExplanationState'

interface DisplayNode {
  node_id: string
  node_name: string
  reason: string
}

interface DisplayNodeGroup {
  group_id: string
  title: string
  summary: string
  nodes: DisplayNode[]
}

interface StageCard {
  key: string
  title: string
  summary: string
}

interface DisplayNodeRef {
  node_id: string
  label: string
  traceTitle: string
  unresolved: boolean
}

interface RawExplanationEntry {
  key: string
  title: string
  currentText: string
  rawText: string
}

const props = defineProps<{
  explanation: ExplanationResponse | null
  loading: boolean
  error: string
  polishRequested: boolean
  displayMode: DisplayMode
  aiAvailability: ExplanationAiAvailability
  askResponse: ExplanationAskResponse | null
  askLoading: boolean
  askError: string
}>()
const emit = defineEmits<{
  (e: 'polish-change', polish: boolean): void
  (e: 'retry'): void
  (e: 'ask-question', payload: ExplanationAskRequest): void
}>()

const activeAuditPanels = ref<string[]>([])
const activeRawPanels = ref<string[]>([])

const genericQuestions: Array<{ question_id: ExplanationQuestionId; label: string }> = [
  { question_id: 'why_path_order', label: '为什么按这个顺序学习？' },
  { question_id: 'budget_feasibility', label: '当前时间预算是否可行？' },
  { question_id: 'what_if_time_limited', label: '如果时间不够怎么办？' },
]

function onPolishChange(value: boolean) {
  emit('polish-change', value)
}

function askQuestion(payload: ExplanationAskRequest) {
  emit('ask-question', payload)
}

const explanation = computed(() => props.explanation)
const loading = computed(() => props.loading)
const error = computed(() => props.error)
const polishRequested = computed(() => props.polishRequested)
const showAuditDetails = computed(() => props.displayMode !== 'simple')
const showTechnicalDetails = computed(() => props.displayMode === 'debug')
const askResponse = computed(() => props.askResponse)
const askLoading = computed(() => props.askLoading)
const askError = computed(() => props.askError)
const isPolishLoading = computed(() => loading.value && polishRequested.value && props.aiAvailability.polishAvailable)
const showInitialPolishSkeleton = computed(() => isPolishLoading.value && !explanation.value)
const polishLoadingMessage = computed(() => (
  explanation.value
    ? 'AI 正在基于当前规则解释做自然语言润色，您可以先继续阅读下方规则文本。'
    : 'AI 润色最长可能需要约 1 分钟，请稍等；完成后会自动展示更自然的解释文本。'
))
const readability = computed(() => explanation.value?.readability ?? null)
const polishMeta = computed(() => explanation.value?.meta?.polish ?? null)
const polishApplied = computed(() => polishMeta.value?.applied === true)
const showPolishUnavailable = computed(
  () => polishRequested.value && !props.aiAvailability.polishAvailable,
)
const polishUnavailableMessage = computed(() => {
  const actions: string[] = []
  if (!props.aiAvailability.llmApiKeySet) {
    actions.push('配置 LLM_API_KEY')
  }
  if (!props.aiAvailability.polishEnabled) {
    actions.push('启用解释润色')
  }
  return `请在设置页${actions.join('并')}后重试。`
})
const polishStatusLabel = computed(() => {
  if (!polishRequested.value) {
    return ''
  }
  return polishApplied.value ? '本次已应用 AI 润色' : '本次未应用 AI 润色'
})
const polishStatusType = computed(() => (
  polishApplied.value ? 'success' : 'warning'
))
const polishHint = computed(() => {
  if (!polishRequested.value) {
    return ''
  }
  if (polishApplied.value) {
    return '解释文本已经过 LLM 润色；原始规则文本保留在 `raw_*` 字段中可对照查看。'
  }
  const fallbackReason = resolvePolishFallbackReason(polishMeta.value?.fallback_reason)
  return fallbackReason
    ? `本次请求未应用 AI 润色，已回退规则文本：${fallbackReason}。`
    : '本次请求未应用 AI 润色，当前展示规则生成的解释文本。'
})

const nodeEntries = computed(() => explanation.value?.node_explanations ?? [])
const reinforcementEntries = computed(() => explanation.value?.reinforcement_explanations ?? [])
const orderingEntries = computed(() => explanation.value?.ordering_explanations ?? [])
const stageEntries = computed(() => explanation.value?.stage_explanations ?? [])
const budgetExplanation = computed(() => explanation.value?.budget_explanation ?? null)

const overview = computed(() => {
  const summary = readability.value?.overview_summary
  const fallbackGoals = nodeEntries.value
    .filter((item) => item.decision_type === 'target')
    .map((item) => item.node_name)
  return {
    headline: summary?.headline || '系统基于最终目标、硬前置依赖、画像补强和时间预算生成当前学习路径。',
    goalNames: summary?.goal_names?.length ? summary.goal_names : fallbackGoals,
    nodeCount: summary?.node_count ?? nodeEntries.value.length,
    totalHours: summary?.total_hours ?? budgetExplanation.value?.total_hours ?? null,
    budgetStatus: summary?.budget_status ?? budgetExplanation.value?.status ?? null,
    pathMode: summary?.path_mode ?? readability.value?.budget_summary?.path_mode ?? null,
    notes: summary?.notes ?? [],
  }
})

const generationSteps = computed(() => readability.value?.generation_steps ?? [])
const nodeNameById = computed(() => {
  const names = new Map<string, string>()
  for (const item of nodeEntries.value) {
    addNodeName(names, item.node_id, item.node_name)
  }
  for (const item of reinforcementEntries.value) {
    addNodeName(names, item.node_id, item.node_name)
  }
  for (const item of orderingEntries.value) {
    addNodeName(names, item.node_id, item.node_name)
  }
  for (const item of stageEntries.value) {
    addNodeName(names, item.node_id, item.node_name)
  }
  for (const chain of explanation.value?.dependency_chain_explanations ?? []) {
    addNodeName(names, chain.target_node_id, chain.target_node_name)
    chain.chain_node_ids.forEach((nodeId, index) => addNodeName(names, nodeId, chain.chain_node_names[index]))
  }
  readability.value?.goal_resolution_summary.target_node_ids.forEach((nodeId, index) => {
    addNodeName(names, nodeId, readability.value?.goal_resolution_summary.target_node_names[index])
  })
  for (const group of readability.value?.node_groups ?? []) {
    for (const node of normalizeGroupNodes(group.nodes, group.node_ids)) {
      addNodeName(names, node.node_id, node.node_name)
    }
  }
  return names
})
const displayGenerationSteps = computed(() => generationSteps.value.map((step) => ({
  ...step,
  nodeRefs: step.node_ids.map(resolveDisplayNodeRef),
})))
const hasGenerationStepNodeRefs = computed(() => displayGenerationSteps.value.some((step) => step.nodeRefs.length > 0))

const displayNodeGroups = computed<DisplayNodeGroup[]>(() => {
  const groups = readability.value?.node_groups
  if (groups?.length) {
    return groups.map((group) => ({
      group_id: group.group_id,
      title: group.title,
      summary: group.summary,
      nodes: normalizeGroupNodes(group.nodes, group.node_ids),
    }))
  }
  return buildFallbackNodeGroups()
})

const orderingSummaryText = computed(() => (
  readability.value?.ordering_summary?.summary
  || `系统在满足前置依赖的基础上，结合 ${orderingEntries.value.length} 个节点的目标相关度和优先级生成学习顺序。`
))
const orderingFactors = computed(() => {
  const factors = readability.value?.ordering_summary?.key_factors ?? []
  if (factors.length) return factors
  return Array.from(new Set(orderingEntries.value.flatMap((item) => item.factors))).slice(0, 8)
})
const stageSummaryText = computed(() => (
  readability.value?.stage_summary?.summary
  || `系统已为 ${stageEntries.value.length} 个节点生成阶段划分说明。`
))
const stageCards = computed<StageCard[]>(() => {
  const stages = readability.value?.stage_summary?.stages ?? []
  if (stages.length) {
    return stages.map((stage, index) => ({
      key: normalizeText(stage.key) || normalizeText(stage.stage_name) || `stage-${index}`,
      title: normalizeText(stage.stage_name) || normalizeText(stage.title) || `阶段 ${index + 1}`,
      summary: normalizeText(stage.summary) || normalizeText(stage.reason) || normalizeText(stage.rule) || '按阶段规则分配。',
    }))
  }
  return stageEntries.value.slice(0, 3).map((item) => ({
    key: item.node_id,
    title: item.assigned_stage,
    summary: `${item.node_name}：${item.rationale || item.reasons.join('、') || '暂无说明'}`,
  }))
})
const budgetSummary = computed<ReadableBudgetSummary | null>(() => {
  if (readability.value?.budget_summary) {
    return readability.value.budget_summary
  }
  const fallback = budgetExplanation.value
  if (!fallback) return null
  return {
    summary: fallback.suggestion,
    total_hours: fallback.total_hours,
    weekly_hours: fallback.weekly_hours,
    estimated_weeks: fallback.estimated_weeks,
    status: fallback.status,
    path_mode: null,
    compressed_dependency_note: null,
  }
})
const budgetSummaryText = computed(() => budgetSummary.value?.summary || '暂无时间预算说明。')
const defenseGuideCards = computed(() => {
  const prerequisiteCount = nodeGroupCount(['prerequisite', 'prerequisites', 'dependency'])
  const reinforcedCount = nodeGroupCount(['reinforced', 'reinforcement'])
  const targetNames = overview.value.goalNames.length ? overview.value.goalNames.join('、') : '目标节点待识别'
  return [
    {
      title: '目标锁定',
      value: targetNames,
      detail: readability.value?.goal_resolution_summary.final_goal_text || '来自目标解析结果',
    },
    {
      title: '依赖闭包',
      value: `${prerequisiteCount} 个前置`,
      detail: '先补齐硬前置，避免跳学关键概念',
    },
    {
      title: '画像补强',
      value: `${reinforcedCount} 个补强`,
      detail: '按画像短板补充必要基础',
    },
    {
      title: '阶段与预算',
      value: `${stageCards.value.length} 阶段 / ${formatHours(budgetSummary.value?.total_hours ?? overview.value.totalHours)}`,
      detail: formatBudgetStatus(budgetSummary.value?.status ?? overview.value.budgetStatus),
    },
  ]
})
const defenseTalkingPoints = computed(() => [
  '先说明学习目标如何映射到目标知识点。',
  '再说明硬前置闭包如何保证学习顺序正确。',
  '接着说明画像补强和排序因子如何体现个性化。',
  '最后用阶段划分与时间预算说明路径可执行。',
])
const auditHighlights = computed<AuditHighlight[]>(() => readability.value?.audit_highlights ?? [])
const rawExplanationEntries = computed<RawExplanationEntry[]>(() => {
  const entries: RawExplanationEntry[] = []
  nodeEntries.value.forEach((item, index) => {
    const rawText = normalizeText(item.raw_reason)
    if (!rawText) return
    entries.push({
      key: `node-${item.node_id || index}`,
      title: `节点纳入原因：${item.node_name || item.node_id}`,
      currentText: normalizeText(item.reason) || '当前展示文本为空',
      rawText,
    })
  })
  stageEntries.value.forEach((item, index) => {
    const rawText = normalizeText(item.raw_rationale)
    if (!rawText) return
    entries.push({
      key: `stage-${item.node_id || index}`,
      title: `阶段划分说明：${item.node_name || item.node_id}`,
      currentText: normalizeText(item.rationale) || item.reasons.join('、') || '当前展示文本为空',
      rawText,
    })
  })
  return entries
})
const traceSourceLabel = computed(() => {
  const provenance = explanation.value?.meta?.provenance
  if (!provenance) return '规则解释'
  return provenance.fallback_used ? '快照 + fallback' : '计划快照'
})
const nodeQuestionTargets = computed(() => {
  const seen = new Set<string>()
  return displayNodeGroups.value
    .flatMap((group) => group.nodes)
    .filter((node) => {
      if (!node.node_id || seen.has(node.node_id)) return false
      seen.add(node.node_id)
      return true
    })
    .slice(0, 5)
})

function addNodeName(names: Map<string, string>, nodeId?: string | null, nodeName?: string | null) {
  const normalizedId = normalizeText(nodeId)
  const normalizedName = normalizeText(nodeName)
  if (normalizedId && normalizedName && normalizedName !== normalizedId) {
    names.set(normalizedId, normalizedName)
  }
}

function resolveDisplayNodeRef(nodeId: string): DisplayNodeRef {
  const label = nodeNameById.value.get(nodeId)
  if (label) {
    return {
      node_id: nodeId,
      label,
      traceTitle: `节点 ID：${nodeId}`,
      unresolved: false,
    }
  }
  return {
    node_id: nodeId,
    label: `未识别知识点（${nodeId}）`,
    traceTitle: `暂未找到该节点的中文名称，节点 ID：${nodeId}`,
    unresolved: true,
  }
}

function normalizeGroupNodes(nodes: Array<Record<string, unknown>>, fallbackIds: string[]) {
  if (nodes.length) {
    return nodes.map((node, index) => {
      const nodeId = normalizeText(node.node_id) || normalizeText(node.id) || fallbackIds[index] || `node-${index}`
      return {
        node_id: nodeId,
        node_name: normalizeText(node.node_name) || normalizeText(node.name) || nodeId,
        reason: normalizeText(node.reason) || normalizeText(node.summary) || normalizeText(node.decision_type),
      }
    })
  }
  return fallbackIds.map((nodeId) => ({
    node_id: nodeId,
    node_name: nodeId,
    reason: '',
  }))
}

function nodeGroupCount(groupIds: string[]) {
  const targetIds = new Set(groupIds)
  return displayNodeGroups.value
    .filter((group) => targetIds.has(group.group_id))
    .reduce((sum, group) => sum + group.nodes.length, 0)
}

function buildFallbackNodeGroups() {
  const reinforcedIds = new Set(reinforcementEntries.value.map((item) => item.node_id))
  const target: DisplayNode[] = []
  const reinforced: DisplayNode[] = []
  const prerequisite: DisplayNode[] = []

  for (const item of nodeEntries.value) {
    const node = {
      node_id: item.node_id,
      node_name: item.node_name,
      reason: item.reason,
    }
    if (item.decision_type === 'target') {
      target.push(node)
    } else if (reinforcedIds.has(item.node_id)) {
      reinforced.push(node)
    } else {
      prerequisite.push(node)
    }
  }

  for (const item of reinforcementEntries.value) {
    if (!reinforced.some((node) => node.node_id === item.node_id)) {
      reinforced.push({
        node_id: item.node_id,
        node_name: item.node_name,
        reason: item.reasons.join('、'),
      })
    }
  }

  return [
    { group_id: 'target', title: '目标节点', summary: '直接对应本次学习目标的知识点。', nodes: target },
    { group_id: 'prerequisite', title: '硬前置节点', summary: '为了满足知识依赖而必须先学习的节点。', nodes: prerequisite },
    { group_id: 'reinforced', title: '画像补强节点', summary: '根据学习者画像短板额外补充的基础节点。', nodes: reinforced },
  ]
}

function normalizeText(value: unknown) {
  if (typeof value === 'string' && value.trim()) return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

function formatHours(value?: number | null) {
  return value == null ? '未知' : `${value} 小时`
}

function formatBudgetStatus(status?: string | null) {
  if (status === 'feasible') return '时间充裕'
  if (status === 'tight') return '时间紧张'
  if (status === 'insufficient') return '时间不足'
  return status || '预算未知'
}

function budgetTagTypeByStatus(status?: string | null) {
  if (status === 'feasible') return 'success'
  if (status === 'tight') return 'warning'
  if (status === 'insufficient') return 'danger'
  return 'info'
}

function formatPathMode(mode?: string | null) {
  if (mode === 'compressed') return '压缩模式'
  if (mode === 'standard') return '标准模式'
  return mode || '路径模式未知'
}

function formatQuestionId(questionId: ExplanationQuestionId) {
  const question = genericQuestions.find((item) => item.question_id === questionId)
  if (question) return question.label
  if (questionId === 'why_include_node') return '为什么纳入这个知识点？'
  if (questionId === 'why_stage_assignment') return '为什么安排在这个阶段？'
  return questionId
}

function evidenceRefLabel(ref: EvidenceRef) {
  return normalizeText(ref.summary) || auditSourceLabel(ref.source).label
}

function evidenceTraceTitle(ref: EvidenceRef) {
  return [
    `来源：${ref.source}`,
    ref.key ? `键：${ref.key}` : '',
    ref.node_id ? `节点 ID：${ref.node_id}` : '',
  ].filter(Boolean).join('；')
}

function formatAuditValue(value: unknown) {
  if (value == null || value === '') return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function resolvePolishFallbackReason(reason?: string | null) {
  if (!reason) return ''
  if (reason === 'disabled') return '设置页未启用解释润色'
  if (reason === 'missing_api_key') return '未配置 LLM_API_KEY'
  if (reason === 'empty_scope') return '当前解释没有可润色内容'
  if (reason === 'invalid_response') return 'AI 返回结果无效'
  if (reason === 'blocked') return 'AI 服务商拦截了本次润色请求，已回退为规则文本'
  if (reason === 'timeout') return 'AI 服务响应超时'
  if (reason === 'length_exceeded') return '文本超过处理上限'
  return reason
}
</script>

<style scoped>
.explanation-section {
  margin-top: 16px;
}
.section-gap {
  margin-bottom: 16px;
}
.section-gap-small {
  margin-bottom: 12px;
}
.section-header,
.polish-toolbar,
.overview-tags,
.evidence-list,
.budget-meta,
.ask-answer-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.section-header {
  justify-content: space-between;
}
.polish-loading-card {
  position: relative;
  display: flex;
  gap: 14px;
  padding: 16px;
  overflow: hidden;
  border: 1px solid #d9ecff;
  border-radius: 14px;
  background: linear-gradient(135deg, #ecf5ff 0%, #ffffff 65%);
}
.polish-loading-card::after {
  position: absolute;
  inset: 0;
  pointer-events: none;
  content: '';
  background: linear-gradient(90deg, transparent, rgba(64, 158, 255, 0.12), transparent);
  animation: polish-shimmer 1.8s ease-in-out infinite;
}
.polish-loading-card__halo {
  z-index: 1;
  display: grid;
  flex: 0 0 44px;
  width: 44px;
  height: 44px;
  place-items: center;
  border-radius: 50%;
  color: #fff;
  font-weight: 700;
  background: linear-gradient(135deg, #409eff, #67c23a);
  box-shadow: 0 8px 18px rgba(64, 158, 255, 0.25);
}
.polish-loading-card__body {
  z-index: 1;
  flex: 1;
  min-width: 0;
}
.polish-loading-card__title {
  margin-bottom: 4px;
  color: #303133;
  font-weight: 700;
}
.polish-loading-card__body p {
  margin: 0 0 10px;
  color: #606266;
  line-height: 1.7;
}
.polish-loading-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.polish-loading-steps span {
  padding: 3px 8px;
  border-radius: 999px;
  color: #337ecc;
  font-size: 12px;
  background: rgba(64, 158, 255, 0.12);
}
.polish-loading-bar {
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: #d9ecff;
}
.polish-loading-bar span {
  display: block;
  width: 38%;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #409eff, #67c23a);
  animation: polish-progress 1.4s ease-in-out infinite;
}
.polish-skeleton {
  padding: 16px;
  border: 1px solid #ebeef5;
  border-radius: 14px;
  background: #fff;
}
.skeleton-line {
  height: 12px;
  margin-top: 12px;
  border-radius: 999px;
  background: linear-gradient(90deg, #f0f2f5 25%, #e4e7ed 50%, #f0f2f5 75%);
  background-size: 200% 100%;
  animation: skeleton-loading 1.5s ease-in-out infinite;
}
.skeleton-line-title {
  width: 42%;
  height: 18px;
  margin-top: 0;
}
.skeleton-line-short {
  width: 68%;
}
.polish-hint,
.summary-text,
.muted-text,
.node-reason,
.step-summary,
.node-id-note {
  color: #606266;
  line-height: 1.7;
}
.polish-hint,
.muted-text,
.node-reason,
.node-id-note {
  font-size: 12px;
}
.node-name-tag {
  cursor: help;
}
.node-id-note {
  margin: 8px 0 0;
}
.defense-guide {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 14px;
  padding: 18px;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 16px;
  background: linear-gradient(135deg, var(--el-color-primary-light-9), #ffffff 68%);
}
.defense-guide-main h3 {
  margin: 0;
  font-size: 22px;
  line-height: 1.4;
}
.defense-guide-main p:not(.defense-eyebrow) {
  margin: 8px 0 0;
  color: #606266;
  line-height: 1.7;
}
.defense-eyebrow {
  margin: 0 0 6px;
  color: var(--el-color-primary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.defense-card-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.defense-card {
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: rgb(255 255 255 / 78%);
}
.defense-card span,
.defense-card small {
  display: block;
  color: #909399;
  font-size: 12px;
}
.defense-card strong {
  display: block;
  margin: 6px 0;
  color: #303133;
  font-size: 16px;
  line-height: 1.4;
}
.defense-talking-points {
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(64, 158, 255, 0.08);
}
.defense-talking-points strong {
  color: #303133;
}
.defense-talking-points ol {
  margin: 8px 0 0;
  padding-left: 18px;
  color: #606266;
  line-height: 1.8;
}
.overview-card {
  background: linear-gradient(135deg, #f5f9ff 0%, #ffffff 60%);
}
.headline {
  margin: 0 0 12px;
  font-size: 18px;
  line-height: 1.6;
}
.metric-grid {
  margin-top: 16px;
}
.metric-card,
.node-group-card,
.summary-card,
.ask-answer {
  border: 1px solid #ebeef5;
  border-radius: 10px;
  padding: 12px;
  background: #fff;
}
.metric-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 70px;
}
.metric-label {
  color: #909399;
  font-size: 12px;
}
.note-list {
  margin: 12px 0 0;
  padding-left: 18px;
  color: #606266;
  line-height: 1.7;
}
.node-group-card,
.summary-card {
  min-height: 100%;
  margin-bottom: 12px;
}
.node-group-title,
.node-question-item,
.stage-mini-item {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.node-list,
.stage-mini-list,
.node-question-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}
.node-item,
.stage-mini-item,
.node-question-item {
  padding: 8px;
  border-radius: 8px;
  background: #f8fafc;
}
.node-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.node-name {
  font-weight: 600;
  color: #303133;
}
.question-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}
.compact-alert {
  margin-top: 10px;
}
.audit-value {
  margin: 8px 0 0;
  padding: 10px;
  background: #f5f7fa;
  border-radius: 8px;
  overflow-x: auto;
  white-space: pre-wrap;
}
.raw-value {
  border-left: 3px solid var(--el-color-warning);
  background: #fff8ec;
}

@keyframes polish-shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

@keyframes polish-progress {
  0% { transform: translateX(-120%); }
  50% { transform: translateX(80%); }
  100% { transform: translateX(260%); }
}

@keyframes skeleton-loading {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

@media (max-width: 768px) {
  .section-header,
  .node-question-item,
  .stage-mini-item {
    align-items: flex-start;
    flex-direction: column;
  }

  .defense-card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
