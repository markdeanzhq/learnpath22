<template>
  <div class="explanation-section" v-if="explanation">
    <el-alert
      v-if="showPolishUnavailable"
      type="warning"
      title="请在设置页配置 LLM_API_KEY 并启用解释润色"
      :closable="false"
      show-icon
      style="margin-bottom: 8px;"
    />
    <div class="polish-toolbar">
      <el-switch
        v-model="polishEnabled"
        active-text="AI 润色"
        inline-prompt
        @change="onPolishChange"
      />
      <span class="polish-hint" v-if="polishEnabled">
        解释文本已经过 LLM 润色；原始规则文本保留在 `raw_*` 字段中可对照查看。
      </span>
    </div>
    <el-tabs v-model="activeTab" type="border-card">
      <el-tab-pane label="节点选择" name="nodes">
        <el-table :data="nodeEntries" size="small" stripe>
          <el-table-column prop="node_name" label="知识点" min-width="160" />
          <el-table-column prop="decision_type" label="类型" width="120" />
          <el-table-column prop="reason" label="选中原因" min-width="280">
            <template #default="{ row }">
              <div>{{ row.reason }}</div>
              <div class="raw-text" v-if="row.raw_reason">
                <span class="raw-label">原始：</span>{{ row.raw_reason }}
              </div>
            </template>
          </el-table-column>
        </el-table>

        <el-divider v-if="reinforcementEntries.length > 0" />

        <template v-if="reinforcementEntries.length > 0">
          <p class="hint-text">系统根据学习者画像自动补充了以下基础节点：</p>
          <el-table :data="reinforcementEntries" size="small" stripe>
            <el-table-column prop="node_name" label="知识点" min-width="160" />
            <el-table-column label="差距(数学)" width="100">
              <template #default="{ row }">{{ row.gap.gap_math?.toFixed(3) ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="差距(编程)" width="100">
              <template #default="{ row }">{{ row.gap.gap_code?.toFixed(3) ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="差距(ML)" width="100">
              <template #default="{ row }">{{ row.gap.gap_ml?.toFixed(3) ?? '-' }}</template>
            </el-table-column>
            <el-table-column label="总差距" width="100">
              <template #default="{ row }">{{ row.gap.gap_total?.toFixed(3) ?? '-' }}</template>
            </el-table-column>
          </el-table>
        </template>
      </el-tab-pane>

      <el-tab-pane label="学习顺序" name="ordering">
        <el-table :data="orderingEntries" size="small" stripe>
          <el-table-column prop="node_name" label="知识点" min-width="160" />
          <el-table-column label="优先级" width="90">
            <template #default="{ row }">{{ row.priority_score.toFixed(3) }}</template>
          </el-table-column>
          <el-table-column label="目标相关度" width="110">
            <template #default="{ row }">{{ row.goal_relevance.toFixed(3) }}</template>
          </el-table-column>
          <el-table-column label="排序因子" min-width="240">
            <template #default="{ row }">{{ row.factors.join(', ') }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="阶段划分" name="staging">
        <el-table :data="stageEntries" size="small" stripe>
          <el-table-column prop="node_name" label="知识点" min-width="160" />
          <el-table-column prop="assigned_stage" label="分配阶段" width="120">
            <template #default="{ row }">
              <el-tag size="small">{{ row.assigned_stage }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="原因" min-width="240">
            <template #default="{ row }">
              <div>{{ row.rationale || '暂无说明' }}</div>
              <div class="raw-text" v-if="row.raw_rationale">
                <span class="raw-label">原始：</span>{{ row.raw_rationale }}
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="依赖链" name="dependency">
        <el-collapse v-if="dependencyChains.length > 0">
          <el-collapse-item
            v-for="item in dependencyChains"
            :key="item.target_node_id"
            :title="item.target_node_name"
            :name="item.target_node_id"
          >
            <p class="hint-text">{{ item.reason }}</p>
            <div class="chain-tags">
              <el-tag v-for="name in item.chain_node_names" :key="name" size="small" style="margin: 0 6px 6px 0">
                {{ name }}
              </el-tag>
            </div>
          </el-collapse-item>
        </el-collapse>
        <el-empty v-else description="暂无依赖链解释" />
      </el-tab-pane>

      <el-tab-pane label="预算说明" name="budget">
        <el-descriptions :column="2" border size="small" v-if="explanation.budget_explanation">
          <el-descriptions-item label="预算状态">
            <el-tag :type="budgetTagType">{{ explanation.budget_explanation.status }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="总学时">{{ explanation.budget_explanation.total_hours }} 小时</el-descriptions-item>
          <el-descriptions-item label="每周学时">{{ explanation.budget_explanation.weekly_hours }} 小时</el-descriptions-item>
          <el-descriptions-item label="预计周数">{{ explanation.budget_explanation.estimated_weeks }} 周</el-descriptions-item>
          <el-descriptions-item label="建议" :span="2">
            <div style="white-space: pre-line">{{ explanation.budget_explanation.suggestion }}</div>
          </el-descriptions-item>
        </el-descriptions>
        <el-empty v-else description="暂无预算说明" />
      </el-tab-pane>
    </el-tabs>
  </div>
  <el-empty v-else description="暂无路径解释数据" />
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import type { ExplanationResponse } from '@/api/modules/plan'
import { useSettingsStore } from '@/stores/settings'

const props = defineProps<{ explanation: ExplanationResponse | null }>()
const emit = defineEmits<{ (e: 'polish-change', polish: boolean): void }>()

const settingsStore = useSettingsStore()
const { llmApiKeySet } = storeToRefs(settingsStore)

const activeTab = ref('nodes')
const polishEnabled = ref(false)

onMounted(async () => {
  await settingsStore.refreshServerStatus()
  polishEnabled.value = settingsStore.llmExplanationPolish
})

function onPolishChange(value: boolean) {
  emit('polish-change', value)
}

const explanation = computed(() => props.explanation)
const showPolishUnavailable = computed(
  () => polishEnabled.value === true && llmApiKeySet.value === false,
)
const nodeEntries = computed(() => explanation.value?.node_explanations ?? [])
const reinforcementEntries = computed(() => explanation.value?.reinforcement_explanations ?? [])
const orderingEntries = computed(() => explanation.value?.ordering_explanations ?? [])
const stageEntries = computed(() => explanation.value?.stage_explanations ?? [])
const dependencyChains = computed(() => explanation.value?.dependency_chain_explanations ?? [])

const budgetTagType = computed(() => {
  const status = explanation.value?.budget_explanation?.status
  if (status === 'feasible') return 'success'
  if (status === 'tight') return 'warning'
  return 'danger'
})
</script>

<style scoped>
.explanation-section { margin-top: 16px; }
.polish-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.polish-hint {
  color: #606266;
  font-size: 12px;
}
.raw-text {
  color: #909399;
  font-size: 12px;
  margin-top: 4px;
  padding-top: 4px;
  border-top: 1px dashed #ebeef5;
}
.raw-label { font-weight: 600; }
.hint-text {
  color: #606266;
  font-size: 13px;
  margin-bottom: 12px;
}
.chain-tags {
  display: flex;
  flex-wrap: wrap;
}
</style>
