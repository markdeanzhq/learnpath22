<template>
  <div class="page-container">
    <el-card shadow="never" v-if="planStore.currentPlan" style="margin-bottom: 20px">
      <template #header>
        <div class="card-header">
          <span>学习路径</span>
          <div class="header-actions">
            <DisplayModeSwitch v-model="displayMode" />
            <el-tag>v{{ planStore.currentPlan.version }}</el-tag>
            <el-tag :type="budgetTagType">
              {{ budgetLabel }}
            </el-tag>
            <el-tag type="info">
              {{ planStore.currentPlan.stages.reduce((sum, s) => sum + s.tasks.length, 0) }} 个知识点
            </el-tag>
            <el-tag v-if="planStore.currentPlan.total_hours" type="info">
              共 {{ planStore.currentPlan.total_hours }} 小时
            </el-tag>
            <el-dropdown trigger="click" @command="handleReplan" style="margin-left: 8px">
              <el-button size="small" :loading="planStore.loading">重规划</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="progress_aware">进度感知（保留已完成）</el-dropdown-item>
                  <el-dropdown-item command="profile_update">画像更新（全量重生成）</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" type="primary" plain :loading="variantLoading" @click="previewVariants">
              预览路径变体
            </el-button>
            <el-button size="small" type="success" plain :loading="graphOptionLoading" @click="previewGraphOptions">
              对比基础/增强图谱
            </el-button>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <el-tab-pane label="路径总览" name="timeline">
          <StageTimeline :stages="planStore.currentPlan.stages" />
        </el-tab-pane>
        <el-tab-pane label="调整路径" name="previews">
          <section class="preview-section">
            <el-alert
              title="预览不会覆盖当前最新路径；只有点击确认应用后才会保存新的正式路径版本。"
              type="info"
              :closable="false"
              show-icon
            />
            <el-alert
              v-if="previewUnsafeMessage"
              class="preview-alert"
              :title="previewUnsafeMessage"
              type="warning"
              :closable="false"
              show-icon
            />

            <div class="adjustment-entry-grid">
              <button
                type="button"
                class="adjustment-entry-card"
                :class="{ active: activeAdjustmentTool === 'variants' }"
                @click="openAdjustmentTool('variants')"
              >
                <strong>调整学习方式</strong>
                <span>标准、压缩、理论优先或实践优先</span>
              </button>
              <button
                type="button"
                class="adjustment-entry-card"
                :class="{ active: activeAdjustmentTool === 'graph_options' }"
                @click="openAdjustmentTool('graph_options')"
              >
                <strong>使用扩展知识点</strong>
                <span>比较基础图谱与已审核扩展图谱</span>
              </button>
              <button
                type="button"
                class="adjustment-entry-card"
                :class="{ active: activeAdjustmentTool === 'feedback' }"
                @click="openAdjustmentTool('feedback')"
              >
                <strong>用一句话调整</strong>
                <span>压缩时间、增加实践或标记已掌握</span>
              </button>
            </div>

            <section v-if="activeAdjustmentTool === 'variants'" class="preview-card">
              <div class="section-header">
                <div>
                  <h3>路径变体预览</h3>
                  <p>比较标准路径、压缩路径、理论优先和实践优先的学习投入与节点取舍。</p>
                </div>
                <el-button type="primary" :loading="variantLoading" @click="previewVariants">生成变体预览</el-button>
              </div>

              <template v-if="variantPreview">
                <div class="preview-meta">
                  <el-tag type="info">状态：{{ variantPreview.status }}</el-tag>
                  <el-tag type="warning">有效期：{{ formatExpiresAt(variantPreview.expires_at) }}</el-tag>
                  <el-tag v-if="showTechnicalDetails" effect="plain">graph：{{ shortHash(variantPreview.project_graph_hash) }}</el-tag>
                </div>
                <div class="variant-grid">
                  <el-card
                    v-for="variant in variantPreview.variants"
                    :key="variant.variant_id"
                    shadow="never"
                    class="variant-card"
                    :class="{ selected: selectedVariantId === variant.variant_id }"
                    @click="selectedVariantId = variant.variant_id"
                  >
                    <div class="variant-title-row">
                      <el-radio-group v-model="selectedVariantId">
                        <el-radio :value="variant.variant_id">{{ pathModeLabel(variant.path_mode) }}</el-radio>
                      </el-radio-group>
                      <el-tag type="success">{{ budgetStatusLabel(variant.budget_summary.status) }}</el-tag>
                    </div>
                    <div class="preview-meta compact">
                      <el-tag type="info">包含 {{ variant.included_node_ids.length }} 个节点</el-tag>
                      <el-tag type="warning">排除 {{ variant.excluded_node_ids.length }} 个节点</el-tag>
                    </div>
                    <dl class="summary-list">
                      <template v-for="item in budgetSummaryEntries(variant.budget_summary)" :key="item.key">
                        <dt>{{ item.key }}</dt>
                        <dd>{{ item.value }}</dd>
                      </template>
                    </dl>
                    <dl v-if="showAuditDetails" class="summary-list audit-summary">
                      <template v-for="item in auditSummaryEntries(variant.audit_summary)" :key="item.key">
                        <dt>{{ item.key }}</dt>
                        <dd>{{ item.value }}</dd>
                      </template>
                    </dl>
                  </el-card>
                </div>
                <el-button
                  type="success"
                  :loading="variantConfirming"
                  :disabled="!canConfirmVariant"
                  @click="confirmSelectedVariant"
                >
                  应用所选变体为正式路径
                </el-button>
              </template>
            </section>

            <section v-if="activeAdjustmentTool === 'graph_options'" class="preview-card graph-option-card">
              <div class="section-header">
                <div>
                  <h3>基础 / 增强图谱路径对比</h3>
                  <p>比较“只按现有基线图谱规划”和“纳入已审核且开启规划的项目扩展图谱规划”，未审核草稿不会进入正式路径。</p>
                </div>
                <el-button type="success" :loading="graphOptionLoading" @click="previewGraphOptions">生成图谱方案对比</el-button>
              </div>
              <el-alert
                title="增强方案只消费已校验、已人工确认并开启规划的 overlay；LLM 草稿不能绕过审核直接进入正式路径。"
                type="warning"
                :closable="false"
                show-icon
              />

              <template v-if="graphOptionPreview">
                <div class="preview-meta">
                  <el-tag type="info">状态：{{ graphOptionPreview.status }}</el-tag>
                  <el-tag type="warning">有效期：{{ formatExpiresAt(graphOptionPreview.expires_at) }}</el-tag>
                  <el-tag v-if="showTechnicalDetails" effect="plain">当前 graph：{{ shortHash(graphOptionPreview.project_graph_hash) }}</el-tag>
                </div>
                <div class="variant-grid">
                  <el-card
                    v-for="variant in graphOptionPreview.variants"
                    :key="variant.variant_id"
                    shadow="never"
                    class="variant-card"
                    :class="{ selected: selectedGraphOptionVariantId === variant.variant_id, unavailable: variant.status === 'unavailable' }"
                    @click="selectGraphOptionVariant(variant)"
                  >
                    <div class="variant-title-row">
                      <el-radio-group v-model="selectedGraphOptionVariantId">
                        <el-radio :value="variant.variant_id" :disabled="variant.status === 'unavailable'">
                          {{ variant.option_label || graphOptionLabel(variant.graph_option) }}
                        </el-radio>
                      </el-radio-group>
                      <el-tag :type="variant.status === 'unavailable' ? 'warning' : 'success'">
                        {{ graphOptionStatusLabel(variant.status) }}
                      </el-tag>
                    </div>
                    <p class="option-description">{{ variant.option_description }}</p>
                    <p class="option-impact">{{ graphOptionImpactText(variant) }}</p>
                    <el-alert
                      v-if="variant.blocked_reason"
                      class="preview-alert"
                      :title="formatPreviewReason(variant.blocked_reason)"
                      type="warning"
                      :closable="false"
                      show-icon
                    />
                    <div class="preview-meta compact">
                      <el-tag type="info">包含 {{ variant.included_node_ids.length }} 个节点</el-tag>
                      <el-tag type="success">增强新增 {{ (variant.added_node_ids || []).length }} 个节点</el-tag>
                      <el-tag type="warning">移除 {{ (variant.removed_node_ids || []).length }} 个节点</el-tag>
                      <el-tag v-if="showAuditDetails" effect="plain">overlay {{ (variant.overlay_node_ids || []).length }} 节点 / {{ (variant.overlay_edge_ids || []).length }} 边</el-tag>
                    </div>
                    <div v-if="showAuditDetails && variant.added_node_ids?.length" class="node-id-list">
                      <span>增强新增：</span>
                      <el-tag v-for="nodeId in variant.added_node_ids" :key="nodeId" type="success" effect="plain">{{ nodeId }}</el-tag>
                    </div>
                    <dl class="summary-list">
                      <template v-for="item in budgetSummaryEntries(variant.budget_summary)" :key="item.key">
                        <dt>{{ item.key }}</dt>
                        <dd>{{ item.value }}</dd>
                      </template>
                    </dl>
                    <dl v-if="showAuditDetails" class="summary-list audit-summary">
                      <template v-for="item in auditSummaryEntries(variant.audit_summary)" :key="item.key">
                        <dt>{{ item.key }}</dt>
                        <dd>{{ item.value }}</dd>
                      </template>
                    </dl>
                  </el-card>
                </div>
                <el-button
                  type="success"
                  :loading="graphOptionConfirming"
                  :disabled="!canConfirmGraphOption"
                  @click="confirmGraphOption"
                >
                  应用所选图谱方案为正式路径
                </el-button>
              </template>
            </section>

            <section v-if="activeAdjustmentTool === 'feedback'" class="preview-card">
              <div class="section-header">
                <div>
                  <h3>自然语言反馈预览</h3>
                  <p>支持压缩时间、增加实践、增加理论、调整期限和标记已掌握节点。</p>
                </div>
              </div>
              <div class="feedback-input-row">
                <el-input
                  v-model="feedbackText"
                  type="textarea"
                  :rows="3"
                  placeholder="例如：我想增加实践内容，或者把时间压缩到 6 周"
                />
                <el-button type="primary" :loading="feedbackLoading" @click="previewFeedback">预览反馈重规划</el-button>
              </div>

              <template v-if="feedbackPreview">
                <div class="preview-meta">
                  <el-tag type="info">意图：{{ feedbackIntentLabel(feedbackPreview.intent_type) }}</el-tag>
                  <el-tag type="success">置信度：{{ formatPercent(feedbackPreview.confidence) }}</el-tag>
                  <el-tag type="warning">有效期：{{ formatExpiresAt(feedbackPreview.expires_at) }}</el-tag>
                  <el-tag v-if="showTechnicalDetails" effect="plain">graph：{{ shortHash(feedbackPreview.project_graph_hash) }}</el-tag>
                </div>
                <dl class="summary-list">
                  <template v-for="item in feedbackParameterEntries(feedbackPreview.controlled_parameters)" :key="item.key">
                    <dt>{{ item.key }}</dt>
                    <dd>{{ item.value }}</dd>
                  </template>
                </dl>
                <div class="diff-grid">
                  <section v-for="item in feedbackDiffEntries" :key="item.key" class="diff-card">
                    <h4>{{ item.key }}</h4>
                    <el-tag v-for="value in item.values" :key="value" type="info" effect="plain">{{ value }}</el-tag>
                  </section>
                </div>
                <dl class="summary-list">
                  <template v-for="item in feedbackBudgetDeltaEntries(feedbackPreview.budget_delta)" :key="item.key">
                    <dt>{{ item.key }}</dt>
                    <dd>{{ item.value }}</dd>
                  </template>
                </dl>
                <div v-if="feedbackPreview.blocked_actions.length" class="blocked-actions">
                  <el-tag v-for="action in feedbackPreview.blocked_actions" :key="action" type="warning">{{ formatPreviewReason(action) }}</el-tag>
                </div>
                <section v-if="feedbackPreview.known_node_draft" class="known-node-draft">
                  <h4>已掌握节点确认</h4>
                  <div class="preview-meta compact">
                    <span v-if="!showAuditDetails" class="option-impact">系统识别出 {{ feedbackPreview.known_node_draft.node_ids.length }} 个已掌握知识点，请确认后再应用重规划。</span>
                    <el-tag v-for="nodeId in showAuditDetails ? feedbackPreview.known_node_draft.node_ids : []" :key="nodeId" type="success">{{ nodeId }}</el-tag>
                    <el-tag type="info">状态：{{ feedbackPreview.known_node_draft.status }}</el-tag>
                  </div>
                  <el-button
                    type="primary"
                    plain
                    :loading="knownNodeConfirming"
                    :disabled="feedbackPreview.known_node_draft.status === 'confirmed'"
                    @click="confirmKnownNodeDraft"
                  >
                    确认这些节点已掌握
                  </el-button>
                </section>
                <el-button
                  type="success"
                  :loading="feedbackConfirming"
                  :disabled="!canConfirmFeedback"
                  @click="confirmFeedbackPreview"
                >
                  应用反馈预览为正式路径
                </el-button>
              </template>
            </section>
          </section>
        </el-tab-pane>
        <el-tab-pane label="规划解释" name="explanation">
          <Explanation
            :explanation="explanation"
            :loading="explanationLoading"
            :error="explanationError"
            :polish-requested="polishRequested"
            :display-mode="displayMode"
            :ai-availability="aiAvailability"
            :ask-response="askResponse"
            :ask-loading="askLoading"
            :ask-error="askError"
            @polish-change="reloadExplanation"
            @retry="retryExplanation"
            @ask-question="askExplanationQuestion"
          />
        </el-tab-pane>
        <el-tab-pane label="推荐资源" name="resources">
          <div class="resources-section">
            <div class="resources-actions">
              <el-alert
                title="资源优先绑定到知识点；阶段资源仅作为总览保底，Tavily 结果属于在线增强。"
                type="info"
                :closable="false"
                show-icon
              />
              <el-button type="primary" @click="recommendResources" :loading="recommendLoading">
                自动补充知识点资源
              </el-button>
            </div>
            <div v-loading="resourcesLoading" element-loading-text="正在加载推荐资源...">
              <template v-if="planResources?.stages?.length">
                <el-collapse>
                  <el-collapse-item
                    v-for="stage in planResources.stages"
                    :key="stage.stage_name"
                    :title="`${stage.stage_name}（${countStageResources(stage)} 条）`"
                    :name="stage.stage_name"
                  >
                    <el-empty v-if="!countStageResources(stage)" description="当前阶段暂无资源，可点击上方按钮自动补充" />
                    <section v-if="stage.stage_resources.length" class="stage-resource-block">
                      <div class="resource-group-title">阶段总览资源</div>
                      <el-card v-for="item in stage.stage_resources" :key="item.id" shadow="never" class="resource-card">
                        <div class="resource-card__header">
                          <a v-if="item.url" :href="item.url" target="_blank" rel="noopener" class="search-link">{{ item.title }}</a>
                          <span v-else class="resource-title">{{ item.title }}</span>
                          <el-tag size="small" :type="resourceTagType(item.source_type)">
                            {{ resourceSourceLabel(item.source_type) }}
                          </el-tag>
                        </div>
                        <div class="resource-snippet">{{ item.snippet || '暂无摘要' }}</div>
                        <div class="resource-meta" v-if="item.score != null">相关度：{{ (item.score * 100).toFixed(0) }}%</div>
                      </el-card>
                    </section>
                    <section v-for="node in stage.nodes" :key="node.node_id" class="node-resource-block">
                      <div class="resource-group-title">{{ node.node_name }}</div>
                      <el-empty v-if="!node.resources.length" description="该知识点暂无资源" />
                      <el-card v-for="item in node.resources" :key="item.id" shadow="never" class="resource-card">
                        <div class="resource-card__header">
                          <a v-if="item.url" :href="item.url" target="_blank" rel="noopener" class="search-link">{{ item.title }}</a>
                          <span v-else class="resource-title">{{ item.title }}</span>
                          <el-tag size="small" :type="resourceTagType(item.source_type)">
                            {{ resourceSourceLabel(item.source_type) }}
                          </el-tag>
                        </div>
                        <div class="resource-snippet">{{ item.snippet || '暂无摘要' }}</div>
                        <div class="resource-meta" v-if="item.score != null">相关度：{{ (item.score * 100).toFixed(0) }}%</div>
                      </el-card>
                    </section>
                  </el-collapse-item>
                </el-collapse>
              </template>
              <el-empty v-else description="暂无推荐资源，可点击上方按钮自动补充" />
            </div>
          </div>
        </el-tab-pane>
        <el-tab-pane label="变更对比" name="diff" v-if="planStore.lastReplanResult?.diff">
          <div class="diff-section">
            <el-tag type="info" style="margin-bottom: 12px">
              模式: {{ planStore.lastReplanResult.mode === 'progress_aware' ? '进度感知' : '画像更新' }}
            </el-tag>
            <template v-if="replanDiffDetails.added?.length">
              <h4>新增节点</h4>
              <el-tag v-for="item in replanDiffDetails.added" :key="item.node_id" type="success" style="margin: 0 4px 4px 0">{{ item.node_name }}</el-tag>
            </template>
            <template v-if="replanDiffDetails.removed?.length">
              <h4>移除节点</h4>
              <el-tag v-for="item in replanDiffDetails.removed" :key="item.node_id" type="danger" style="margin: 0 4px 4px 0">{{ item.node_name }}</el-tag>
            </template>
            <template v-if="replanDiffDetails.unchanged?.length">
              <h4>保持不变</h4>
              <el-tag v-for="item in replanDiffDetails.unchanged" :key="item.node_id" type="info" style="margin: 0 4px 4px 0">{{ item.node_name }}</el-tag>
            </template>
            <template v-if="replanDiffDetails.completed?.length">
              <h4>已完成（锁定）</h4>
              <el-tag v-for="item in replanDiffDetails.completed" :key="item.node_id" type="success" style="margin: 0 4px 4px 0">{{ item.node_name }}</el-tag>
            </template>
            <template v-if="replanDiffDetails.pending?.length">
              <h4>待重规划</h4>
              <el-tag v-for="item in replanDiffDetails.pending" :key="item.node_id" type="warning" style="margin: 0 4px 4px 0">{{ item.node_name }}</el-tag>
            </template>
            <template v-if="replanDiffDetails.skipped?.length">
              <h4>已跳过</h4>
              <el-tag v-for="item in replanDiffDetails.skipped" :key="item.node_id" type="warning" effect="plain" style="margin: 0 4px 4px 0">{{ item.node_name }}</el-tag>
            </template>
          </div>
        </el-tab-pane>
        <el-tab-pane label="搜索资料" name="search">
          <div class="search-section">
            <div class="search-toolbar">
              <el-input
                v-model="searchQuery"
                placeholder="输入关键词搜索学习资料..."
                @keyup.enter="doSearch"
              >
                <template #append>
                  <el-button @click="doSearch" :loading="searching">搜索</el-button>
                </template>
              </el-input>
              <el-select v-model="selectedStageName" placeholder="选择阶段" style="width: 220px">
                <el-option
                  v-for="stage in stageOptions"
                  :key="stage.stage_name"
                  :label="stage.stage_name"
                  :value="stage.stage_name"
                />
              </el-select>
              <el-select v-model="selectedNodeId" placeholder="选择知识点" style="width: 240px">
                <el-option
                  v-for="task in selectedStageTasks"
                  :key="task.node_id"
                  :label="task.name"
                  :value="task.node_id"
                />
              </el-select>
            </div>
            <el-table :data="searchResults" v-if="searchResults.length" size="small" stripe>
              <el-table-column label="标题" min-width="200">
                <template #default="{ row }">
                  <a :href="row.url" target="_blank" rel="noopener" class="search-link">{{ row.title }}</a>
                </template>
              </el-table-column>
              <el-table-column prop="snippet" label="摘要" min-width="300" show-overflow-tooltip />
              <el-table-column label="相关度" width="80">
                <template #default="{ row }">{{ (row.score * 100).toFixed(0) }}%</template>
              </el-table-column>
              <el-table-column label="操作" width="130">
                <template #default="{ row }">
                  <el-button link type="primary" :loading="bindLoading" @click="bindSearchResultToNode(row)">
                    绑定到知识点
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else-if="searchDone" description="未找到相关资料" />
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-card v-else-if="planStore.loading" shadow="never">
      <div v-loading="true" style="height: 200px" element-loading-text="正在加载学习路径..." />
    </el-card>

    <el-card v-else-if="projectId && !loadError" shadow="never">
      <el-empty description="暂无学习路径，请先生成">
        <template #image>
          <el-icon :size="60" color="#67C23A"><Guide /></el-icon>
        </template>
        <el-button type="primary" @click="router.push('/project')">前往项目页</el-button>
      </el-empty>
    </el-card>

    <el-card v-else-if="loadError" shadow="never">
      <el-result icon="warning" title="加载失败" :sub-title="loadError">
        <template #extra>
          <el-button type="primary" @click="loadPath">重试</el-button>
        </template>
      </el-result>
    </el-card>

    <el-card v-else shadow="never">
      <el-empty description="请先在项目页面选择一个项目">
        <template #image>
          <el-icon :size="60" color="#409EFF"><Guide /></el-icon>
        </template>
        <el-button type="primary" @click="router.push('/project')">前往项目页</el-button>
      </el-empty>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Guide } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import { usePlanStore } from '@/stores/plan'
import { useSettingsStore } from '@/stores/settings'
import { planApi, type ExplanationAskRequest, type FeedbackPreviewSessionResponse, type VariantPreviewSessionResponse, type VariantSummary } from '@/api/modules/plan'
import { searchApi, type SearchResultItem } from '@/api/modules/search'
import { resourceApi, type PlanResourcesResponse, type StageResourceGroup } from '@/api/modules/resource'
import DisplayModeSwitch from '@/components/DisplayModeSwitch.vue'
import { useDisplayMode } from '@/composables/useDisplayMode'
import {
  auditSummaryEntries,
  budgetSummaryEntries,
  feedbackBudgetDeltaEntries,
  feedbackParameterEntries,
  stringifyPreviewValue,
} from '@/utils/pathPreviewDisplay'
import { formatErrorCode } from '@/utils/displayLabels'
import StageTimeline from './components/StageTimeline.vue'
import Explanation from './Explanation.vue'
import { useExplanationState } from './useExplanationState'

type AdjustmentTool = 'variants' | 'graph_options' | 'feedback'

const STALE_PREVIEW_ERRORS = new Set([
  'STALE_VARIANT_PREVIEW',
  'STALE_FEEDBACK_PREVIEW',
  'PROJECT_GRAPH_DRIFT',
  'PACK_HASH_DRIFT',
  'PROFILE_DRIFT',
  'PARAMETER_DRIFT',
])

const router = useRouter()
const projectStore = useProjectStore()
const planStore = usePlanStore()
const settingsStore = useSettingsStore()
const { llmApiKeySet, llmExplanationPolish } = storeToRefs(settingsStore)
const { displayMode, showAuditDetails, showTechnicalDetails } = useDisplayMode()

const activeTab = ref('timeline')
const loadError = ref('')
const projectId = computed(() => projectStore.currentProject?.id)
const searchQuery = ref('')
const searchResults = ref<SearchResultItem[]>([])
const searching = ref(false)
const searchDone = ref(false)
const planResources = ref<PlanResourcesResponse | null>(null)
const resourcesLoading = ref(false)
const recommendLoading = ref(false)
const bindLoading = ref(false)
const selectedStageName = ref('')
const selectedNodeId = ref('')
const activeAdjustmentTool = ref<AdjustmentTool>('variants')
const variantPreview = ref<VariantPreviewSessionResponse | null>(null)
const selectedVariantId = ref('')
const variantLoading = ref(false)
const variantConfirming = ref(false)
const graphOptionPreview = ref<VariantPreviewSessionResponse | null>(null)
const selectedGraphOptionVariantId = ref('')
const graphOptionLoading = ref(false)
const graphOptionConfirming = ref(false)
const feedbackText = ref('')
const feedbackPreview = ref<FeedbackPreviewSessionResponse | null>(null)
const feedbackLoading = ref(false)
const feedbackConfirming = ref(false)
const knownNodeConfirming = ref(false)
const previewUnsafeMessage = ref('')
const previewProjectId = ref('')
const previewPlanId = ref('')
const currentPlanId = computed(() => planStore.currentPlan?.id)
const explanationState = useExplanationState(projectId, currentPlanId)
const {
  explanation,
  polishRequested,
  loading: explanationLoading,
  error: explanationError,
  askResponse,
  askLoading,
  askError,
} = explanationState
const aiAvailability = computed(() => ({
  llmApiKeySet: llmApiKeySet.value,
  polishEnabled: llmExplanationPolish.value,
  polishAvailable: llmApiKeySet.value && llmExplanationPolish.value,
}))

const previewContextMatches = computed(() => (
  Boolean(projectId.value && currentPlanId.value) &&
  previewProjectId.value === projectId.value &&
  previewPlanId.value === currentPlanId.value
))
const selectedVariant = computed(() => variantPreview.value?.variants.find((item) => item.variant_id === selectedVariantId.value) ?? null)
const selectedGraphOptionVariant = computed(() => graphOptionPreview.value?.variants.find((item) => item.variant_id === selectedGraphOptionVariantId.value) ?? null)
const canConfirmVariant = computed(() => Boolean(
  variantPreview.value?.status === 'active' && selectedVariant.value && previewContextMatches.value && !previewUnsafeMessage.value,
))
const canConfirmGraphOption = computed(() => Boolean(
  graphOptionPreview.value?.status === 'active'
  && selectedGraphOptionVariant.value
  && selectedGraphOptionVariant.value.status !== 'unavailable'
  && previewContextMatches.value
  && !previewUnsafeMessage.value,
))
const canConfirmFeedback = computed(() => {
  if (feedbackPreview.value?.status !== 'active' || !previewContextMatches.value || previewUnsafeMessage.value) {
    return false
  }
  if (!feedbackPreview.value.requires_second_confirm) {
    return true
  }
  return feedbackPreview.value.known_node_draft?.status === 'confirmed'
})
const feedbackDiffEntries = computed(() => Object.entries(feedbackPreview.value?.diff ?? {})
  .filter((entry): entry is [string, string[]] => Array.isArray(entry[1]) && entry[1].length > 0)
  .map(([key, values]) => ({ key: feedbackDiffLabel(key), values })))

async function loadPlanResources() {
  if (!projectId.value || !planStore.currentPlan?.id) {
    planResources.value = null
    return
  }
  resourcesLoading.value = true
  try {
    planResources.value = await resourceApi.getPlanResources(projectId.value, planStore.currentPlan.id)
    if (!selectedStageName.value) {
      selectedStageName.value = planStore.currentPlan.stages[0]?.stage_name || ''
    }
    if (!selectedNodeId.value) {
      selectedNodeId.value = selectedStageTasks.value[0]?.node_id || ''
    }
  } catch (e: any) {
    if (!planResources.value) {
      planResources.value = null
    }
    ElMessage.error(e?.response?.data?.error || '加载推荐资源失败')
  } finally {
    resourcesLoading.value = false
  }
}

function clearPreviews(message = '') {
  variantPreview.value = null
  selectedVariantId.value = ''
  graphOptionPreview.value = null
  selectedGraphOptionVariantId.value = ''
  feedbackPreview.value = null
  previewUnsafeMessage.value = message
  previewProjectId.value = ''
  previewPlanId.value = ''
}

function markPreviewContext() {
  previewProjectId.value = projectId.value || ''
  previewPlanId.value = currentPlanId.value || ''
  previewUnsafeMessage.value = ''
}

function openAdjustmentTool(tool: AdjustmentTool) {
  activeAdjustmentTool.value = tool
  activeTab.value = 'previews'
}

function graphOptionImpactText(variant: VariantSummary) {
  if (variant.status === 'unavailable') {
    return `该方案暂不可用：${formatPreviewReason(variant.blocked_reason) || '当前图谱状态无法生成路径'}`
  }
  const added = variant.added_node_ids?.length || 0
  const removed = variant.removed_node_ids?.length || 0
  if (variant.graph_option === 'baseline') {
    return added ? `基础方案不会纳入增强方案中的 ${added} 个扩展知识点。` : '基础方案只使用领域基线图谱，适合保守生成路径。'
  }
  if (added || removed) {
    return `增强方案会新增 ${added} 个已审核知识点，移除 ${removed} 个不适用节点。`
  }
  return '增强方案当前与基础方案差异较小，但会持续遵守已审核扩展图谱边界。'
}

function formatPreviewReason(value?: string | null) {
  return formatErrorCode(value) || value || ''
}

function feedbackDiffLabel(key: string) {
  const map: Record<string, string> = {
    added: '新增知识点',
    removed: '移除知识点',
    unchanged: '保持不变',
    completed: '已完成锁定',
    skipped: '已跳过',
    pending: '待重规划',
  }
  return map[key] || key
}

function isStalePreviewError(error: any) {
  const data = error?.response?.data
  return STALE_PREVIEW_ERRORS.has(data?.error) || STALE_PREVIEW_ERRORS.has(data?.reason_code) || STALE_PREVIEW_ERRORS.has(data?.details?.reason_code)
}

function handlePreviewError(error: any, fallback: string) {
  if (isStalePreviewError(error)) {
    clearPreviews('预览已过期或路径依赖的画像/图谱/知识包已变化，请重新生成预览。')
    return
  }
  previewUnsafeMessage.value = ''
  ElMessage.error(error?.response?.data?.error || fallback)
}

async function refreshAfterPlanWrite() {
  if (!projectId.value) return
  await planStore.loadLatest(projectId.value)
  await Promise.all([
    explanationState.load(),
    loadPlanResources(),
  ])
}

async function loadPath() {
  loadError.value = ''
  const previousProjectId = projectId.value
  const previousPlanId = planStore.currentPlan?.id
  selectedStageName.value = ''
  selectedNodeId.value = ''
  clearPreviews()
  if (!projectId.value) {
    planResources.value = null
    planStore.currentPlan = null
    explanationState.clear()
    return
  }
  try {
    await settingsStore.refreshServerStatus().catch(() => undefined)
    await planStore.loadLatest(projectId.value)
    if (projectId.value !== previousProjectId || planStore.currentPlan?.id !== previousPlanId) {
      planResources.value = null
      explanationState.clear()
    }
    await explanationState.load(llmExplanationPolish.value)
    await loadPlanResources()
  } catch (e: any) {
    planResources.value = null
    planStore.currentPlan = null
    explanationState.clear()
    clearPreviews()
    if (e?.response?.status !== 404) {
      loadError.value = e?.response?.data?.error || '加载路径失败'
    }
  }
}

async function reloadExplanation(polish: boolean) {
  await explanationState.load(polish)
}

async function retryExplanation() {
  await explanationState.load()
}

async function askExplanationQuestion(payload: ExplanationAskRequest) {
  await explanationState.ask(payload)
}

onMounted(() => loadPath())

watch(projectId, () => loadPath())
watch(currentPlanId, (nextPlanId, previousPlanId) => {
  if (previousPlanId && nextPlanId !== previousPlanId) {
    clearPreviews()
  }
})

async function handleReplan(mode: string) {
  if (!projectId.value) return
  try {
    await planStore.replan(projectId.value, mode as 'progress_aware' | 'profile_update')
    clearPreviews()
    await Promise.all([
      explanationState.load(),
      loadPlanResources(),
    ])
    activeTab.value = 'diff'
    ElMessage.success('重规划完成')
  } catch (e: any) {
    if (e?.response?.status === 409 && e?.response?.data?.error === 'GOAL_TARGETS_REMOVED') {
      router.push({
        path: '/project',
        query: {
          mode: 'reconfirm',
          projectId: projectId.value,
          reason: 'goal-targets-removed',
        },
      })
      return
    }
    ElMessage.error(e?.response?.data?.error || '重规划失败')
  }
}

async function previewVariants() {
  if (variantLoading.value || !projectId.value || !currentPlanId.value) return
  variantLoading.value = true
  previewUnsafeMessage.value = ''
  try {
    variantPreview.value = await planApi.previewVariants(projectId.value)
    graphOptionPreview.value = null
    selectedGraphOptionVariantId.value = ''
    feedbackPreview.value = null
    selectedVariantId.value = variantPreview.value.variants[0]?.variant_id || ''
    markPreviewContext()
    activeAdjustmentTool.value = 'variants'
    activeTab.value = 'previews'
  } catch (error: any) {
    handlePreviewError(error, '生成路径变体预览失败')
  } finally {
    variantLoading.value = false
  }
}

async function confirmSelectedVariant() {
  if (variantConfirming.value || !projectId.value || !variantPreview.value || !selectedVariant.value || !canConfirmVariant.value) return
  variantConfirming.value = true
  try {
    await planApi.confirmVariant(projectId.value, variantPreview.value.variant_preview_id, selectedVariant.value.variant_id)
    clearPreviews()
    await refreshAfterPlanWrite()
    activeTab.value = 'timeline'
    ElMessage.success('变体已保存为新的正式路径版本')
  } catch (error: any) {
    handlePreviewError(error, '应用路径变体失败')
  } finally {
    variantConfirming.value = false
  }
}

function selectGraphOptionVariant(variant: VariantSummary) {
  if (variant.status === 'unavailable') return
  selectedGraphOptionVariantId.value = variant.variant_id
}

async function previewGraphOptions() {
  if (graphOptionLoading.value || !projectId.value || !currentPlanId.value) return
  graphOptionLoading.value = true
  previewUnsafeMessage.value = ''
  try {
    graphOptionPreview.value = await planApi.previewGraphOptions(projectId.value, planStore.currentPlan?.path_mode)
    variantPreview.value = null
    selectedVariantId.value = ''
    feedbackPreview.value = null
    selectedGraphOptionVariantId.value = (
      graphOptionPreview.value.variants.find((item) => item.status !== 'unavailable')?.variant_id || ''
    )
    markPreviewContext()
    activeAdjustmentTool.value = 'graph_options'
    activeTab.value = 'previews'
  } catch (error: any) {
    handlePreviewError(error, '生成图谱方案对比失败')
  } finally {
    graphOptionLoading.value = false
  }
}

async function confirmGraphOption() {
  if (
    graphOptionConfirming.value
    || !projectId.value
    || !graphOptionPreview.value
    || !selectedGraphOptionVariant.value
    || !canConfirmGraphOption.value
  ) return
  graphOptionConfirming.value = true
  try {
    await planApi.confirmVariant(
      projectId.value,
      graphOptionPreview.value.variant_preview_id,
      selectedGraphOptionVariant.value.variant_id,
    )
    clearPreviews()
    await refreshAfterPlanWrite()
    activeTab.value = 'timeline'
    ElMessage.success('图谱方案已保存为新的正式路径版本')
  } catch (error: any) {
    handlePreviewError(error, '应用图谱方案失败')
  } finally {
    graphOptionConfirming.value = false
  }
}

async function previewFeedback() {
  if (feedbackLoading.value || !projectId.value || !currentPlanId.value || !feedbackText.value.trim()) return
  feedbackLoading.value = true
  previewUnsafeMessage.value = ''
  try {
    feedbackPreview.value = await planApi.previewFeedback(projectId.value, feedbackText.value.trim())
    variantPreview.value = null
    selectedVariantId.value = ''
    graphOptionPreview.value = null
    selectedGraphOptionVariantId.value = ''
    markPreviewContext()
    activeAdjustmentTool.value = 'feedback'
    activeTab.value = 'previews'
  } catch (error: any) {
    handlePreviewError(error, '生成反馈预览失败')
  } finally {
    feedbackLoading.value = false
  }
}

async function confirmKnownNodeDraft() {
  if (knownNodeConfirming.value || !projectId.value || !feedbackPreview.value?.known_node_draft) return
  knownNodeConfirming.value = true
  try {
    feedbackPreview.value.known_node_draft = await planApi.confirmKnownNodeDraft(projectId.value, feedbackPreview.value.known_node_draft.draft_id)
  } catch (error: any) {
    handlePreviewError(error, '确认已掌握节点失败')
  } finally {
    knownNodeConfirming.value = false
  }
}

async function confirmFeedbackPreview() {
  if (feedbackConfirming.value || !projectId.value || !feedbackPreview.value || !canConfirmFeedback.value) return
  feedbackConfirming.value = true
  try {
    await planApi.confirmFeedback(projectId.value, feedbackPreview.value.feedback_preview_id)
    clearPreviews()
    await refreshAfterPlanWrite()
    activeTab.value = 'timeline'
    ElMessage.success('反馈预览已保存为新的正式路径版本')
  } catch (error: any) {
    handlePreviewError(error, '应用反馈预览失败')
  } finally {
    feedbackConfirming.value = false
  }
}

async function recommendResources() {
  if (!projectId.value || !planStore.currentPlan?.id) return
  recommendLoading.value = true
  try {
    planResources.value = await resourceApi.recommendPlanResources(projectId.value, planStore.currentPlan.id)
    activeTab.value = 'resources'
    ElMessage.success('已为当前路径补充知识点资源')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '自动补充资源失败')
  } finally {
    recommendLoading.value = false
  }
}

async function doSearch() {
  if (!projectId.value || !searchQuery.value.trim()) return
  searching.value = true
  searchDone.value = false
  try {
    const data = await searchApi.search(projectId.value, searchQuery.value)
    searchResults.value = data.results ?? []
    searchDone.value = true
  } catch (e: any) {
    ElMessage.error('搜索失败')
  } finally {
    searching.value = false
  }
}

async function bindSearchResultToNode(row: SearchResultItem) {
  if (!projectId.value || !planStore.currentPlan?.id || !selectedStageName.value || !selectedNodeId.value) {
    ElMessage.warning('请先选择目标知识点')
    return
  }
  bindLoading.value = true
  try {
    await resourceApi.bindManualResource(projectId.value, planStore.currentPlan.id, {
      stage_name: selectedStageName.value,
      node_id: selectedNodeId.value,
      title: row.title,
      url: row.url,
      snippet: row.snippet,
    })
    await loadPlanResources()
    activeTab.value = 'resources'
    ElMessage.success('已绑定到当前知识点')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '绑定资源失败')
  } finally {
    bindLoading.value = false
  }
}

const replanDiffDetails = computed(() => planStore.lastReplanResult?.diff_details ?? {})

const budgetTagType = computed(() => {
  const status = planStore.currentPlan?.budget_status
  if (status === 'feasible') return 'success'
  if (status === 'tight') return 'warning'
  return 'danger'
})

const budgetLabel = computed(() => {
  const status = planStore.currentPlan?.budget_status
  if (status === 'feasible') return '时间充裕'
  if (status === 'tight') return '时间紧张'
  if (status === 'insufficient') return '时间不足'
  return status ?? '未知'
})

const stageOptions = computed(() => planStore.currentPlan?.stages ?? [])
const selectedStageTasks = computed(() => (
  stageOptions.value.find((stage) => stage.stage_name === selectedStageName.value)?.tasks ?? []
))

watch(selectedStageName, () => {
  selectedNodeId.value = selectedStageTasks.value[0]?.node_id || ''
})

function countStageResources(stage: StageResourceGroup) {
  return stage.stage_resources.length + stage.nodes.reduce((sum, node) => sum + node.resources.length, 0)
}

function resourceTagType(sourceType: string) {
  if (sourceType === 'static') return 'info'
  if (sourceType === 'manual') return 'success'
  return 'warning'
}

function resourceSourceLabel(sourceType: string) {
  if (sourceType === 'static') return '静态保底'
  if (sourceType === 'manual') return '手动绑定'
  return '在线增强'
}

function pathModeLabel(pathMode: string) {
  const map: Record<string, string> = {
    standard: '标准路径',
    compressed: '压缩路径',
    theory_first: '理论优先',
    practice_first: '实践优先',
  }
  return map[pathMode] || pathMode
}

function graphOptionLabel(option?: string | null) {
  if (option === 'baseline') return '基础图谱路径'
  if (option === 'enhanced') return '增强图谱路径'
  return option || '图谱方案'
}

function graphOptionStatusLabel(status?: string) {
  if (status === 'unavailable') return '暂不可用'
  return '可应用'
}

function feedbackIntentLabel(intent: string) {
  const map: Record<string, string> = {
    compress_time: '压缩时间',
    increase_practice: '增加实践',
    increase_theory: '增加理论',
    adjust_deadline: '调整期限',
    mark_known_nodes: '标记已掌握',
  }
  return map[intent] || intent
}

function budgetStatusLabel(value: unknown) {
  if (value === 'feasible') return '时间充裕'
  if (value === 'tight') return '时间紧张'
  if (value === 'insufficient') return '时间不足'
  return stringifyPreviewValue(value || '未知')
}

function formatExpiresAt(expiresAt: string) {
  const date = new Date(expiresAt)
  if (Number.isNaN(date.getTime())) {
    return expiresAt
  }
  return date.toLocaleString('zh-CN', { hour12: false })
}

function formatPercent(value?: number | null) {
  if (value == null) return '未知'
  return `${Math.round(value * 100)}%`
}

function shortHash(value?: string | null) {
  if (!value) return '无'
  return value.length > 12 ? `${value.slice(0, 12)}…` : value
}

</script>

<style scoped>
.page-container { padding: 20px; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.preview-section,
.preview-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.preview-alert {
  margin-top: 12px;
}
.adjustment-entry-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}
.adjustment-entry-card {
  min-height: 88px;
  padding: 14px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-primary);
  cursor: pointer;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.adjustment-entry-card span {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.5;
}
.adjustment-entry-card.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-5);
}
.preview-card {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 16px;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.section-header h3 {
  margin: 0 0 4px;
}
.section-header p {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}
.preview-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.preview-meta.compact {
  margin: 8px 0;
}
.variant-grid,
.diff-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}
.variant-card {
  cursor: pointer;
  border: 1px solid var(--el-border-color);
}
.variant-card.selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-5);
}
.variant-card.unavailable {
  cursor: not-allowed;
  opacity: 0.72;
}
.option-description,
.option-impact {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}
.option-impact {
  color: var(--el-text-color-regular);
}
.node-id-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.variant-title-row,
.feedback-input-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.feedback-input-row > :first-child {
  flex: 1;
}
.summary-list {
  display: grid;
  grid-template-columns: minmax(100px, max-content) 1fr;
  gap: 6px 12px;
  margin: 12px 0 0;
  font-size: 13px;
}
.summary-list dt {
  color: var(--el-text-color-secondary);
}
.summary-list dd {
  margin: 0;
  color: var(--el-text-color-regular);
  word-break: break-word;
}
.audit-summary {
  border-top: 1px dashed var(--el-border-color);
  padding-top: 8px;
}
.diff-card,
.known-node-draft {
  border: 1px dashed var(--el-border-color);
  border-radius: 6px;
  padding: 12px;
}
.diff-card h4,
.known-node-draft h4,
.diff-section h4 {
  margin: 12px 0 8px 0;
  font-size: 14px;
  color: #303133;
}
.blocked-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.search-toolbar,
.resources-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.stage-resource-block,
.node-resource-block {
  margin-bottom: 16px;
}
.resource-group-title {
  color: #303133;
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 8px;
}
.resource-card {
  margin-bottom: 12px;
}
.resource-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
.resource-title,
.search-link {
  color: #409EFF;
  text-decoration: none;
  font-weight: 500;
}
.search-link:hover {
  text-decoration: underline;
}
.resource-snippet {
  color: #606266;
  line-height: 1.6;
}
.resource-meta {
  color: #909399;
  font-size: 12px;
  margin-top: 8px;
}

@media (max-width: 768px) {
  .page-container {
    padding: 12px;
  }

  .card-header,
  .variant-title-row,
  .feedback-input-row,
  .section-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }

  .header-actions {
    width: 100%;
  }

  .search-toolbar,
  .resources-actions,
  .resource-card__header {
    flex-direction: column;
    align-items: stretch;
  }

  :deep(.el-tabs__nav) {
    flex-wrap: wrap;
  }
}
</style>
