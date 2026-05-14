<template>
  <div class="page-container">
    <el-card shadow="never" v-if="planStore.currentPlan" class="path-dashboard-card">
      <section class="path-hero">
        <div class="path-hero-main">
          <p class="hero-eyebrow">学习路径驾驶舱</p>
          <h1>{{ currentProjectTitle }}</h1>
          <p class="hero-goal">目标：{{ currentProjectGoal }}</p>
          <div class="hero-tags">
            <el-tag>v{{ planStore.currentPlan.version }}</el-tag>
            <el-tag :type="budgetTagType">{{ budgetLabel }}</el-tag>
            <el-tag type="info">{{ pathModeLabel(planStore.currentPlan.path_mode || 'standard') }}</el-tag>
            <el-tag v-if="pathModeSourceLabel" type="success" effect="plain">来源：{{ pathModeSourceLabel }}</el-tag>
          </div>
        </div>
        <div class="path-hero-actions">
          <el-button type="primary" @click="activeTab = 'timeline'">继续学习</el-button>
          <el-button plain @click="openAdjustmentTool('variants')">调整路径</el-button>
          <el-button plain @click="activeTab = 'explanation'">查看解释</el-button>
        </div>
      </section>

      <PageSummaryBar :items="pathSummaryItems" class="path-summary-bar">
        <NextActionCard :title="nextLearningTitle" :description="nextLearningDescription">
          <el-button size="small" type="primary" @click="activeTab = 'timeline'">查看当前阶段</el-button>
          <el-button size="small" plain @click="activeTab = 'explanation'">查看原因</el-button>
        </NextActionCard>
      </PageSummaryBar>

      <div class="path-display-row">
        <DisplayModeSwitch v-model="displayMode" />
        <span>显示模式只影响解释和审计信息展示，不会修改正式路径。</span>
      </div>

      <el-alert
        v-if="displayMode !== 'simple'"
        class="display-mode-hint"
        :title="displayModeHint.title"
        :description="displayModeHint.description"
        :type="displayModeHint.type"
        :closable="false"
        show-icon
      />

      <el-tabs v-model="activeTab">
        <el-tab-pane label="路径总览" name="timeline">
          <StageTimeline
            :stages="planStore.currentPlan.stages"
            :practice-intensity="practiceIntensity"
          />
        </el-tab-pane>
        <el-tab-pane label="调整路径" name="previews">
          <section class="preview-section">
            <section class="adjustment-workbench">
              <div class="adjustment-workbench-main">
                <p class="hero-eyebrow">路径调整中心</p>
                <h2>先预览影响，再决定是否生成新版本</h2>
                <p>这里集中处理时间预算、学习偏好、图谱范围和自然语言反馈；除“快速重规划”外，其它方案都只生成预览，不会立刻覆盖当前路径。</p>
              </div>
              <div class="adjustment-safety-steps" aria-label="路径调整安全流程">
                <span>1 选择调整方式</span>
                <span>2 查看差异和预算</span>
                <span>3 确认后保存新版</span>
              </div>
            </section>

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

            <section class="quick-replan-card">
              <div class="section-header compact-header">
                <div>
                  <span class="adjustment-card-kicker">场景化重规划</span>
                  <h3>按你现在遇到的情况选择</h3>
                  <p>前两个场景会生成新的正式路径版本；点击后会先确认。想先看影响就走预览，不写入正式路径。</p>
                </div>
              </div>
              <div class="replan-scenario-grid">
                <button
                  v-for="scenario in quickReplanScenarios"
                  :key="scenario.id"
                  type="button"
                  class="replan-scenario-card"
                  :disabled="scenario.action === 'replan' && planStore.loading"
                  @click="handleReplanScenario(scenario)"
                >
                  <strong>{{ scenario.title }}</strong>
                  <span>{{ scenario.description }}</span>
                  <small>{{ scenario.buttonLabel }}</small>
                </button>
              </div>
            </section>

            <section class="adjustment-preview-panel">
              <div class="section-header compact-header">
                <div>
                  <h3>先比较，再应用</h3>
                  <p>适合不确定要不要改变当前路径时使用，确认前只会展示差异。</p>
                </div>
              </div>
              <div class="adjustment-entry-grid">
                <button
                  type="button"
                  class="adjustment-entry-card"
                  :class="{ active: activeAdjustmentTool === 'variants' }"
                  @click="openAdjustmentTool('variants')"
                >
                  <em>学习节奏</em>
                  <strong>调整学习方式</strong>
                  <span>标准或压缩路径控制完整度；理论/实践侧重由画像和反馈调整</span>
                  <small>适合：想改变学习投入或路径长度</small>
                </button>
                <button
                  type="button"
                  class="adjustment-entry-card"
                  :class="{ active: activeAdjustmentTool === 'graph_options' }"
                  @click="openAdjustmentTool('graph_options')"
                >
                  <em>图谱范围</em>
                  <strong>使用扩展知识点</strong>
                  <span>比较基础图谱与已审核扩展图谱</span>
                  <small>适合：目标涉及项目级扩展知识</small>
                </button>
                <button
                  type="button"
                  class="adjustment-entry-card"
                  :class="{ active: activeAdjustmentTool === 'feedback' }"
                  @click="openAdjustmentTool('feedback')"
                >
                  <em>自然语言</em>
                  <strong>用一句话调整</strong>
                  <span>压缩时间、增加实践或标记已掌握</span>
                  <small>适合：不知道该选哪个参数</small>
                </button>
              </div>
            </section>

            <section v-if="activeAdjustmentTool === 'variants'" class="preview-card">
              <div class="section-header">
                <div>
                  <h3>路径变体预览</h3>
                  <p>比较标准、压缩等路径模式的学习投入与节点取舍；理论/实践侧重来自画像权重和反馈预览。</p>
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
              <div v-else class="preview-empty-hint">
                <strong>还没有生成变体预览</strong>
                <span>点击上方按钮后，系统会比较标准、压缩等路径模式；理论/实践侧重会通过画像权重和反馈入口体现。</span>
              </div>
            </section>

            <section v-if="activeAdjustmentTool === 'graph_options'" class="preview-card graph-option-card">
              <div class="section-header">
                <div>
                  <h3>基础 / 增强图谱路径对比</h3>
                  <p>比较“只按现有基线图谱规划”和“纳入已审核且开启规划的项目扩展图谱规划”，未审核草稿不会进入正式路径。</p>
                </div>
                <el-button type="success" :loading="graphOptionLoading" :disabled="overlayPreflight?.status === 'blocked'" @click="previewGraphOptions">生成图谱方案对比</el-button>
              </div>
              <el-alert
                title="增强方案只消费已校验、已人工确认并开启规划的 overlay；LLM 草稿不能绕过审核直接进入正式路径。"
                type="warning"
                :closable="false"
                show-icon
              />
              <el-alert
                v-if="graphOptionEntryGuideVisible"
                class="preview-alert"
                title="已从 Knowledge 增强图谱预检进入"
                description="下一步点击“生成图谱方案对比”；系统只生成可撤销预览，确认应用前不会保存正式路径版本。"
                type="info"
                :closable="false"
                show-icon
              />
              <section v-if="overlayPreflight" class="overlay-preflight-panel">
                <div class="overlay-preflight-header">
                  <strong>增强图谱使用状态</strong>
                  <el-tag :type="overlayPreflightTagType">{{ overlayPreflightStatusLabel }}</el-tag>
                </div>
                <p>{{ overlayPreflight.summary }}</p>
                <div class="preview-meta compact">
                  <el-tag type="info" effect="plain">候选 {{ overlayPreflight.counts.active_nodes }} 节点 / {{ overlayPreflight.counts.active_edges }} 关系</el-tag>
                  <el-tag type="success" effect="plain">可进入 {{ overlayPreflight.counts.visible_overlay_nodes }} 节点 / {{ overlayPreflight.counts.visible_overlay_edges }} 关系</el-tag>
                  <el-tag type="warning" effect="plain">当前路径命中 {{ overlayPreflight.counts.path_overlay_nodes }} 节点 / {{ overlayPreflight.counts.path_overlay_edges }} 关系</el-tag>
                  <el-tag v-if="overlayPreflight.counts.shadowed_edges" type="warning" effect="plain">基线覆盖关系 {{ overlayPreflight.counts.shadowed_edges }}</el-tag>
                  <el-tag v-if="overlayPreflight.counts.cycle_edges" type="danger" effect="plain">环依赖关系 {{ overlayPreflight.counts.cycle_edges }}</el-tag>
                </div>
                <div v-if="overlayPreflightIssues.length" class="overlay-preflight-issues">
                  <span v-for="(item, index) in overlayPreflightIssues" :key="`${item.kind}-${index}`">{{ item.message }}</span>
                </div>
              </section>

              <template v-if="graphOptionPreview">
                <div class="preview-meta">
                  <el-tag type="info">状态：{{ graphOptionPreview.status }}</el-tag>
                  <el-tag type="warning">有效期：{{ formatExpiresAt(graphOptionPreview.expires_at) }}</el-tag>
                  <el-tag v-if="showTechnicalDetails" effect="plain">当前 graph：{{ shortHash(graphOptionPreview.project_graph_hash) }}</el-tag>
                </div>
                <el-alert
                  v-if="graphOptionComparisonMessage"
                  class="preview-alert"
                  :title="graphOptionComparisonMessage"
                  :type="graphOptionComparisonType"
                  :closable="false"
                  show-icon
                />
                <section v-if="graphOptionSummaryRows.length" class="graph-option-summary" aria-label="图谱方案影响摘要">
                  <div class="section-header compact-header">
                    <div>
                      <h3>增强影响摘要</h3>
                      <p>先看增强图谱是否真正影响最终路径，再决定是否应用为正式版本。</p>
                    </div>
                  </div>
                  <div class="graph-option-summary-grid">
                    <article v-for="row in graphOptionSummaryRows" :key="row.label">
                      <span>{{ row.label }}</span>
                      <strong>{{ row.value }}</strong>
                      <small>{{ row.detail }}</small>
                    </article>
                  </div>
                  <div class="graph-option-change-tags">
                    <el-tag v-for="badge in graphOptionChangeBadges" :key="badge.label" :type="badge.type" effect="plain">
                      {{ badge.label }}
                    </el-tag>
                  </div>
                  <p class="option-impact">{{ graphOptionDefenseSummary }}</p>
                </section>
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
                      <el-tag v-if="showAuditDetails" effect="plain">可见 overlay {{ (variant.visible_overlay_node_ids || variant.overlay_node_ids || []).length }} 节点 / {{ (variant.visible_overlay_edge_ids || variant.overlay_edge_ids || []).length }} 边</el-tag>
                      <el-tag v-if="showAuditDetails" effect="plain">路径命中 {{ (variant.path_overlay_node_ids || []).length }} 节点 / {{ (variant.path_overlay_edge_ids || []).length }} 边</el-tag>
                      <el-tag v-if="showAuditDetails && variant.order_changed" type="success" effect="plain">顺序变化</el-tag>
                      <el-tag v-if="showAuditDetails && variant.stage_changed" type="success" effect="plain">阶段变化</el-tag>
                      <el-tag v-if="showAuditDetails && variant.budget_changed" type="success" effect="plain">预算变化</el-tag>
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
              <div v-else class="preview-empty-hint">
                <strong>还没有生成图谱方案对比</strong>
                <span>点击上方按钮后，可比较基础图谱和已审核扩展图谱的路径差异。</span>
              </div>
            </section>

            <section v-if="activeAdjustmentTool === 'feedback'" class="preview-card">
              <div class="section-header">
                <div>
                  <h3>自然语言反馈预览</h3>
                  <p>支持压缩时间、增加实践、增加理论、调整期限和标记已掌握节点。</p>
                </div>
              </div>
              <div class="feedback-example-row" aria-label="反馈快捷示例">
                <span>快捷示例</span>
                <el-button
                  v-for="example in feedbackExamples"
                  :key="example.label"
                  size="small"
                  plain
                  @click="applyFeedbackExample(example.text)"
                >
                  {{ example.label }}
                </el-button>
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
                <section class="feedback-readable-summary" aria-label="反馈预览摘要">
                  <article v-for="item in feedbackReadableCards" :key="item.label">
                    <span>{{ item.label }}</span>
                    <strong>{{ item.value }}</strong>
                    <small>{{ item.detail }}</small>
                  </article>
                </section>
                <dl v-if="showAuditDetails && feedbackParameterEntries(feedbackPreview.controlled_parameters).length" class="summary-list audit-summary">
                  <dt>参数变化</dt>
                  <dd>以下是后端识别出的受控参数，供答辩或调试时核对。</dd>
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
                <dl v-if="showAuditDetails && feedbackBudgetDeltaEntries(feedbackPreview.budget_delta).length" class="summary-list audit-summary">
                  <dt>预算原始字段</dt>
                  <dd>保留后端返回字段，方便核验预算计算。</dd>
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
                  <div v-if="feedbackKnownNodeEvidenceRows.length" class="known-node-evidence-list">
                    <span v-for="item in feedbackKnownNodeEvidenceRows" :key="item.key">
                      {{ item.nodeName }}
                      <small v-if="item.matchedText">命中：{{ item.matchedText }}</small>
                    </span>
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
              <div v-else class="preview-empty-hint">
                <strong>还没有反馈预览</strong>
                <span>输入一句话后先生成差异预览，确认前不会保存为正式路径。</span>
              </div>
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
              <el-button type="primary" @click="recommendSelectedNodeResources" :loading="selectedNodeRecommendLoading" :disabled="!selectedNodeId">
                补充当前知识点资源
              </el-button>
              <el-button plain @click="recommendResources" :loading="recommendLoading">
                批量补充缺资源知识点
              </el-button>
            </div>
            <div v-loading="resourcesLoading" :element-loading-text="resourceLoadingText">
              <template v-if="planResources?.stages?.length">
                <section class="resource-workbench">
                  <div class="resource-workbench-main">
                    <p class="hero-eyebrow">知识点资源工作台</p>
                    <h3>{{ selectedResourceNode?.node_name || '选择知识点查看资源' }}</h3>
                    <p>资源默认跟随知识点展示，阶段资源只作为总览保底；搜索并绑定入口只服务当前选中的阶段与知识点。</p>
                  </div>
                  <div class="resource-stat-grid" aria-label="资源覆盖概览">
                    <article>
                      <span>总资源</span>
                      <strong>{{ totalResourceCount }} 条</strong>
                    </article>
                    <article>
                      <span>当前阶段</span>
                      <strong>{{ selectedStageResourceCount }} 条</strong>
                    </article>
                    <article>
                      <span>当前知识点</span>
                      <strong>{{ selectedNodeResourceCount }} 条</strong>
                    </article>
                    <article>
                      <span>待补充知识点</span>
                      <strong>{{ missingResourceNodeCount }} 个</strong>
                    </article>
                  </div>
                </section>

                <section class="resource-focus-layout">
                  <aside class="resource-node-list" aria-label="按知识点选择资源">
                    <el-collapse v-model="activeResourceNodeStages" class="resource-node-stage-collapse">
                      <el-collapse-item
                        v-for="stage in planResources.stages"
                        :key="stage.stage_name"
                        :title="resourceStageCollapseTitle(stage)"
                        :name="stage.stage_name"
                      >
                        <button
                          v-for="node in stage.nodes"
                          :key="node.node_id"
                          type="button"
                          class="resource-node-button"
                          :class="{ active: selectedNodeId === node.node_id }"
                          @click="selectResourceNode(stage.stage_name, node.node_id)"
                        >
                          <strong>{{ node.node_name }}</strong>
                          <span>{{ node.resources.length ? `${node.resources.length} 条资源` : '待补充资源' }}</span>
                        </button>
                      </el-collapse-item>
                    </el-collapse>
                  </aside>

                  <section class="resource-node-panel">
                    <div class="section-header compact-header">
                      <div>
                        <h3>{{ selectedResourceNode?.node_name || '请选择知识点' }}</h3>
                        <p>{{ selectedStageName || '未选择阶段' }} · 当前知识点 {{ selectedNodeResourceCount }} 条资源</p>
                      </div>
                      <el-button plain @click="activeTab = 'search'">搜索并绑定资料</el-button>
                    </div>
                    <el-empty v-if="!selectedResourceNode?.resources.length" description="该知识点暂无资源，可自动补充或搜索绑定" />
                    <el-card v-for="item in selectedResourceNode?.resources ?? []" :key="item.id" shadow="never" class="resource-card featured-resource-card">
                      <div class="resource-card__header">
                        <a v-if="safeExternalUrl(item.url)" :href="safeExternalUrl(item.url)" target="_blank" rel="noopener" class="search-link">{{ item.title }}</a>
                        <span v-else class="resource-title">{{ item.title }}</span>
                        <el-tag size="small" :type="resourceTagType(item.source_type)">
                          {{ resourceSourceLabel(item.source_type) }}
                        </el-tag>
                        <el-tag v-if="resourcePreferenceLabel(item.preference_match)" size="small" effect="plain" :type="resourcePreferenceTagType(item.preference_match)">
                          {{ resourcePreferenceLabel(item.preference_match) }}
                        </el-tag>
                      </div>
                      <div class="resource-snippet">{{ item.snippet || '暂无摘要' }}</div>
                      <div v-if="item.preference_reason" class="resource-preference-reason">{{ item.preference_reason }}</div>
                      <div class="resource-meta" v-if="item.score != null">相关度：{{ (item.score * 100).toFixed(0) }}%</div>
                    </el-card>
                  </section>
                </section>

                <el-collapse v-model="activeResourceOverviewStages" class="resource-overview-collapse">
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
                          <a v-if="safeExternalUrl(item.url)" :href="safeExternalUrl(item.url)" target="_blank" rel="noopener" class="search-link">{{ item.title }}</a>
                          <span v-else class="resource-title">{{ item.title }}</span>
                          <el-tag size="small" :type="resourceTagType(item.source_type)">
                            {{ resourceSourceLabel(item.source_type) }}
                          </el-tag>
                          <el-tag v-if="resourcePreferenceLabel(item.preference_match)" size="small" effect="plain" :type="resourcePreferenceTagType(item.preference_match)">
                            {{ resourcePreferenceLabel(item.preference_match) }}
                          </el-tag>
                        </div>
                        <div class="resource-snippet">{{ item.snippet || '暂无摘要' }}</div>
                        <div v-if="item.preference_reason" class="resource-preference-reason">{{ item.preference_reason }}</div>
                        <div class="resource-meta" v-if="item.score != null">相关度：{{ (item.score * 100).toFixed(0) }}%</div>
                      </el-card>
                    </section>
                    <section v-for="node in stage.nodes" :key="node.node_id" class="node-resource-block">
                      <div class="resource-group-title">{{ node.node_name }}</div>
                      <el-empty v-if="!node.resources.length" description="该知识点暂无资源" />
                      <el-card v-for="item in node.resources" :key="item.id" shadow="never" class="resource-card">
                        <div class="resource-card__header">
                          <a v-if="safeExternalUrl(item.url)" :href="safeExternalUrl(item.url)" target="_blank" rel="noopener" class="search-link">{{ item.title }}</a>
                          <span v-else class="resource-title">{{ item.title }}</span>
                          <el-tag size="small" :type="resourceTagType(item.source_type)">
                            {{ resourceSourceLabel(item.source_type) }}
                          </el-tag>
                          <el-tag v-if="resourcePreferenceLabel(item.preference_match)" size="small" effect="plain" :type="resourcePreferenceTagType(item.preference_match)">
                            {{ resourcePreferenceLabel(item.preference_match) }}
                          </el-tag>
                        </div>
                        <div class="resource-snippet">{{ item.snippet || '暂无摘要' }}</div>
                        <div v-if="item.preference_reason" class="resource-preference-reason">{{ item.preference_reason }}</div>
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
            <section class="diff-summary-panel">
              <div class="section-header compact-header">
                <div>
                  <h3>重规划结果摘要</h3>
                  <p>{{ replanDiffHumanSummary }}</p>
                </div>
                <el-tag type="info">模式：{{ replanModeLabel }}</el-tag>
              </div>
              <div class="diff-summary-grid">
                <article v-for="item in replanDiffSummaryCards" :key="item.key">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                  <small>{{ item.detail }}</small>
                </article>
              </div>
              <el-alert
                title="已完成不等于删除"
                description="已完成节点会进入学习历史和锁定集合，重规划只是避免把它们重复塞回待学路径；它们仍然是路径证据的一部分。"
                type="info"
                :closable="false"
                show-icon
              />
            </section>
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
            <template v-if="replanDiffDetails.order_changed?.length">
              <h4>顺序变化</h4>
              <el-tag v-for="item in replanDiffDetails.order_changed" :key="item.node_id" type="warning" style="margin: 0 4px 4px 0">{{ item.node_name }}</el-tag>
            </template>
            <template v-if="replanDiffDetails.stage_changed?.length">
              <h4>阶段变化</h4>
              <el-tag v-for="item in replanDiffDetails.stage_changed" :key="item.node_id" type="warning" effect="plain" style="margin: 0 4px 4px 0">{{ item.node_name }}</el-tag>
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
            <template v-if="replanDiffDetails.blocked?.length">
              <h4>依赖阻断</h4>
              <el-tag v-for="item in replanDiffDetails.blocked" :key="item.node_id" type="danger" effect="plain" style="margin: 0 4px 4px 0">{{ item.node_name }}</el-tag>
            </template>
          </div>
        </el-tab-pane>
        <el-tab-pane label="搜索并绑定" name="search">
          <div class="search-section">
            <div class="search-toolbar">
              <el-input
                v-model="searchQuery"
                placeholder="搜索要绑定到当前知识点的资料..."
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
                  <a v-if="safeExternalUrl(row.url)" :href="safeExternalUrl(row.url)" target="_blank" rel="noopener" class="search-link">{{ row.title }}</a>
                  <span v-else>{{ row.title }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="snippet" label="摘要" min-width="300" show-overflow-tooltip />
              <el-table-column label="相关度" width="80">
                <template #default="{ row }">{{ (row.score * 100).toFixed(0) }}%</template>
              </el-table-column>
              <el-table-column label="操作" width="130">
                <template #default="{ row }">
                  <el-button link type="primary" :loading="bindLoading" @click="bindSearchResultToNode(row)">
                    绑定到当前知识点
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-else-if="searchDone" description="未找到相关资料" />
            <section v-else class="search-empty-guide">
              <h3>搜索资料并绑定到选中知识点</h3>
              <p>先选择阶段和知识点，再输入关键词搜索；这里不维护项目资料库，也不生成图谱候选，绑定后的资料会回到“推荐资源”页签中按知识点展示。</p>
            </section>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-card v-else-if="planStore.loading" shadow="never" class="path-empty-card loading-state">
      <div v-loading="true" class="path-loading-panel" element-loading-text="正在加载学习路径...">
        <h3>正在准备学习路径</h3>
        <p>蕾姆正在读取最新路径、解释和推荐资源，加载完成后会自动展示驾驶舱。</p>
      </div>
    </el-card>

    <el-card v-else-if="projectId && !loadError" shadow="never" class="path-empty-card">
      <el-empty description="还没有生成学习路径">
        <template #image>
          <el-icon :size="60" color="#67C23A"><Guide /></el-icon>
        </template>
        <div class="empty-action-panel">
          <h3>先回到项目页完成画像并生成路径</h3>
          <p>当前项目已选中，但还没有可展示的正式学习路径。完成画像后即可生成阶段化学习计划。</p>
          <el-button type="primary" @click="router.push('/project')">前往项目页生成路径</el-button>
        </div>
      </el-empty>
    </el-card>

    <el-card v-else-if="loadError" shadow="never" class="path-empty-card">
      <el-result icon="warning" title="路径加载失败" :sub-title="loadError">
        <template #extra>
          <div class="empty-action-panel compact">
            <p>可以先重试读取最新路径；如果仍失败，请回项目页检查目标、画像或重新生成路径。</p>
            <div class="empty-action-row">
              <el-button type="primary" @click="loadPath">重试加载</el-button>
              <el-button plain @click="router.push('/project')">返回项目页</el-button>
            </div>
          </div>
        </template>
      </el-result>
    </el-card>

    <el-card v-else shadow="never" class="path-empty-card">
      <el-empty description="请先选择学习项目">
        <template #image>
          <el-icon :size="60" color="#409EFF"><Guide /></el-icon>
        </template>
        <div class="empty-action-panel">
          <h3>学习路径需要依附于项目</h3>
          <p>请先在项目页选择已有项目，或创建新项目并完成画像采集后再生成路径。</p>
          <el-button type="primary" @click="router.push('/project')">前往项目页</el-button>
        </div>
      </el-empty>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { Guide } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import { usePlanStore } from '@/stores/plan'
import { useSettingsStore } from '@/stores/settings'
import {
  planApi,
  type ExplanationAskRequest,
  type FeedbackPreviewSessionResponse,
  type ReplanDiff,
  type ReplanDiffDetails,
  type ReplanResult,
  type VariantConfirmResponse,
  type VariantPreviewSessionResponse,
  type VariantSummary,
} from '@/api/modules/plan'
import { graphApi, type OverlayPreflightResponse } from '@/api/modules/graph'
import { searchApi, type SearchResultItem } from '@/api/modules/search'
import { resourceApi, type PlanResourcesResponse, type StageResourceGroup } from '@/api/modules/resource'
import DisplayModeSwitch from '@/components/DisplayModeSwitch.vue'
import PageSummaryBar from '@/components/PageSummaryBar.vue'
import NextActionCard from '@/components/NextActionCard.vue'
import { useDisplayMode } from '@/composables/useDisplayMode'
import {
  auditSummaryEntries,
  budgetSummaryEntries,
  feedbackBudgetDeltaEntries,
  feedbackParameterEntries,
  stringifyPreviewValue,
} from '@/utils/pathPreviewDisplay'
import { formatErrorCode } from '@/utils/displayLabels'
import { safeExternalUrl } from '@/utils/url'
import StageTimeline from './components/StageTimeline.vue'
import Explanation from './Explanation.vue'
import { useExplanationState } from './useExplanationState'

type AdjustmentTool = 'variants' | 'graph_options' | 'feedback'
type QuickReplanMode = 'progress_aware' | 'profile_update'
type ReplanDiffKey = keyof ReplanDiff

const STALE_PREVIEW_ERRORS = new Set([
  'STALE_VARIANT_PREVIEW',
  'STALE_FEEDBACK_PREVIEW',
  'PROJECT_GRAPH_DRIFT',
  'PACK_HASH_DRIFT',
  'PROFILE_DRIFT',
  'PARAMETER_DRIFT',
])
const DEFAULT_RESOURCE_STAGE_NAME = '基础准备'
const REPLAN_DIFF_KEYS: ReplanDiffKey[] = ['added', 'removed', 'unchanged', 'order_changed', 'stage_changed', 'completed', 'pending', 'skipped', 'blocked']
const quickReplanScenarios = [
  {
    id: 'finished_some',
    title: '我学完了一部分',
    description: '保留已完成和已跳过记录，只重新安排还没学完的部分。',
    action: 'replan',
    mode: 'progress_aware',
    buttonLabel: '按进度生成新版',
  },
  {
    id: 'profile_changed',
    title: '我的基础或时间变了',
    description: '按最新画像、每周投入和期限重新生成完整路径。',
    action: 'replan',
    mode: 'profile_update',
    buttonLabel: '按画像生成新版',
  },
  {
    id: 'preview_first',
    title: '我想先看看影响',
    description: '先进入预览区比较节点、预算和图谱变化，不会写入正式版本。',
    action: 'preview',
    buttonLabel: '打开影响预览',
  },
] as const
const feedbackExamples = [
  { label: '时间更紧', text: '我想把路径压缩到 6 周' },
  { label: '多些实战', text: '请多安排项目练习和动手实践' },
  { label: '我已掌握', text: '机器学习导论我已经会了，不用学' },
] as const

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const planStore = usePlanStore()
const settingsStore = useSettingsStore()
const { llmApiKeySet, llmExplanationPolish } = storeToRefs(settingsStore)
const { displayMode, showAuditDetails, showTechnicalDetails } = useDisplayMode()

const activeTab = ref('timeline')
const loadError = ref('')
const projectId = computed(() => projectStore.currentProject?.id)
const currentProjectTitle = computed(() => projectStore.currentProject?.title || '当前学习路径')
const currentProjectGoal = computed(() => projectStore.currentProject?.goal_text || '当前学习目标')
const pathStageCount = computed(() => planStore.currentPlan?.stages.length || 0)
const pathNodeCount = computed(() => (
  planStore.currentPlan?.node_count ?? planStore.currentPlan?.stages.reduce((sum, stage) => sum + stage.tasks.length, 0) ?? 0
))
const pathTotalHoursLabel = computed(() => (
  planStore.currentPlan?.total_hours ? `${planStore.currentPlan.total_hours} 小时` : '待估算'
))
const practiceIntensity = computed(() => {
  const value = planStore.currentPlan?.audit?.profile_snapshot?.practice_intensity
  return typeof value === 'number' ? value : null
})
const pathModeSourceLabel = computed(() => pathModeSourceLabelFrom(
  planStore.currentPlan?.path_mode_source || planStore.currentPlan?.audit?.path_mode_source,
))
const pathSummaryItems = computed<Array<{ label: string; value: string; detail: string; tone: 'primary' | 'success' | 'warning' | 'danger' | 'info' }>>(() => [
  {
    label: '阶段数',
    value: `${pathStageCount.value} 个`,
    detail: '按学习顺序分阶段推进',
    tone: 'primary',
  },
  {
    label: '知识点',
    value: `${pathNodeCount.value} 个`,
    detail: '目标、前置和画像补强节点',
    tone: 'info',
  },
  {
    label: '预计投入',
    value: pathTotalHoursLabel.value,
    detail: '来自当前路径预算评估',
    tone: 'success',
  },
  {
    label: '时间预算',
    value: budgetLabel.value,
    detail: '不裁剪硬依赖，仅提示风险',
    tone: budgetTagType.value === 'danger' ? 'danger' : budgetTagType.value === 'warning' ? 'warning' : 'success',
  },
])
const firstPathTask = computed(() => planStore.currentPlan?.stages.flatMap((stage) => stage.tasks)[0] ?? null)
const nextLearningTitle = computed(() => firstPathTask.value ? `从「${firstPathTask.value.name}」开始` : '查看阶段化学习路径')
const nextLearningDescription = computed(() => firstPathTask.value
  ? '默认先从当前路径的第一个知识点开始；学习过程中可在进度页记录状态。'
  : '路径加载完成后，这里会显示建议开始的知识点。')
const searchQuery = ref('')
const searchResults = ref<SearchResultItem[]>([])
const searching = ref(false)
const searchDone = ref(false)
const planResources = ref<PlanResourcesResponse | null>(null)
const resourcesLoading = ref(false)
const resourcesLoadedPathId = ref('')
const recommendLoading = ref(false)
const selectedNodeRecommendLoading = ref(false)
const bindLoading = ref(false)
const selectedStageName = ref('')
const selectedNodeId = ref('')
const activeResourceNodeStages = ref<string[]>([])
const activeResourceOverviewStages = ref<string[]>([])
const activeAdjustmentTool = ref<AdjustmentTool>('variants')
const variantPreview = ref<VariantPreviewSessionResponse | null>(null)
const selectedVariantId = ref('')
const variantLoading = ref(false)
const variantConfirming = ref(false)
const graphOptionPreview = ref<VariantPreviewSessionResponse | null>(null)
const selectedGraphOptionVariantId = ref('')
const graphOptionLoading = ref(false)
const graphOptionConfirming = ref(false)
const overlayPreflight = ref<OverlayPreflightResponse | null>(null)
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
const displayModeHint = computed(() => {
  if (displayMode.value === 'debug') {
    return {
      title: '调试模式：显示 hash、审计字段与内部追溯信息',
      description: '适合排查 graph drift、preview 过期和解释 DTO 问题；不会改变路径生成结果。',
      type: 'warning' as const,
    }
  }
  if (displayMode.value === 'defense') {
    return {
      title: '答辩模式：显示算法依据与可解释链路',
      description: '会展示生成流程、audit 摘要、overlay 计数和节点追溯信息，适合向评委说明路径为何成立。',
      type: 'success' as const,
    }
  }
  return {
    title: '普通模式：隐藏审计细节，只保留用户决策信息',
    description: '适合学习者查看路径、资源、预算和重规划操作；切换模式只影响展示，不会修改正式路径。',
    type: 'info' as const,
  }
})

const previewContextMatches = computed(() => (
  Boolean(projectId.value && currentPlanId.value) &&
  previewProjectId.value === projectId.value &&
  previewPlanId.value === currentPlanId.value
))
const selectedVariant = computed(() => variantPreview.value?.variants.find((item) => item.variant_id === selectedVariantId.value) ?? null)
const selectedGraphOptionVariant = computed(() => graphOptionPreview.value?.variants.find((item) => item.variant_id === selectedGraphOptionVariantId.value) ?? null)
const graphOptionBaselineVariant = computed(() => graphOptionPreview.value?.variants.find((item) => item.graph_option === 'baseline') ?? null)
const graphOptionEnhancedVariant = computed(() => graphOptionPreview.value?.variants.find((item) => item.graph_option === 'enhanced') ?? null)
const graphOptionAddedCount = computed(() => graphOptionEnhancedVariant.value?.added_node_ids?.length || 0)
const graphOptionRemovedCount = computed(() => graphOptionEnhancedVariant.value?.removed_node_ids?.length || 0)
const graphOptionVisibleOverlayNodeCount = computed(() => (
  graphOptionEnhancedVariant.value?.visible_overlay_node_ids?.length
  ?? graphOptionEnhancedVariant.value?.overlay_node_ids?.length
  ?? 0
))
const graphOptionVisibleOverlayEdgeCount = computed(() => (
  graphOptionEnhancedVariant.value?.visible_overlay_edge_ids?.length
  ?? graphOptionEnhancedVariant.value?.overlay_edge_ids?.length
  ?? 0
))
const graphOptionPathOverlayNodeCount = computed(() => graphOptionEnhancedVariant.value?.path_overlay_node_ids?.length || 0)
const graphOptionPathOverlayEdgeCount = computed(() => graphOptionEnhancedVariant.value?.path_overlay_edge_ids?.length || 0)
const graphOptionHasPathLevelChange = computed(() => Boolean(
  graphOptionPathOverlayNodeCount.value
  || graphOptionPathOverlayEdgeCount.value
  || graphOptionEnhancedVariant.value?.order_changed
  || graphOptionEnhancedVariant.value?.stage_changed
  || graphOptionEnhancedVariant.value?.budget_changed,
))
const graphOptionGraphChanged = computed(() => Boolean(
  graphOptionBaselineVariant.value?.project_graph_hash
  && graphOptionEnhancedVariant.value?.project_graph_hash
  && graphOptionBaselineVariant.value.project_graph_hash !== graphOptionEnhancedVariant.value.project_graph_hash,
))
const graphOptionComparisonType = computed(() => {
  if (graphOptionAddedCount.value || graphOptionRemovedCount.value || graphOptionHasPathLevelChange.value) return 'success'
  if (!graphOptionVisibleOverlayNodeCount.value && !graphOptionVisibleOverlayEdgeCount.value && !graphOptionGraphChanged.value) return 'warning'
  return 'info'
})
const graphOptionComparisonMessage = computed(() => {
  const enhanced = graphOptionEnhancedVariant.value
  if (!graphOptionPreview.value || !enhanced) return ''
  if (enhanced.status === 'unavailable') {
    return `增强方案暂不可用：${formatPreviewReason(enhanced.blocked_reason) || '当前图谱状态无法生成路径'}`
  }
  if (graphOptionAddedCount.value || graphOptionRemovedCount.value) {
    return `增强方案已影响最终路径：新增 ${graphOptionAddedCount.value} 个知识点，移除 ${graphOptionRemovedCount.value} 个节点。${graphOptionChangeSuffix(enhanced)}`
  }
  if (graphOptionHasPathLevelChange.value) {
    return `增强方案已命中当前路径：${graphOptionChangeLabels(enhanced).join('、')}。即使节点集合一致，依赖、顺序、阶段或预算也可能已经变化。`
  }
  if (graphOptionVisibleOverlayNodeCount.value || graphOptionVisibleOverlayEdgeCount.value) {
    return `增强图谱已纳入 ${graphOptionVisibleOverlayNodeCount.value} 个已审核扩展知识点和 ${graphOptionVisibleOverlayEdgeCount.value} 条关系，但当前目标路径没有命中这些扩展，所以最终路径节点与基础方案一致。`
  }
  if (!graphOptionGraphChanged.value) {
    return '当前没有已审核、校验通过且开启规划的扩展图谱，基础方案与增强方案会完全一致。'
  }
  return '增强图谱边界已变化，但当前目标下最终路径节点没有变化。'
})
const graphOptionSummaryRows = computed(() => {
  const enhanced = graphOptionEnhancedVariant.value
  if (!graphOptionPreview.value || !enhanced) return []
  return [
    {
      label: '路径节点差异',
      value: `新增 ${graphOptionAddedCount.value} / 移除 ${graphOptionRemovedCount.value}`,
      detail: graphOptionAddedCount.value || graphOptionRemovedCount.value ? '增强方案已改变最终节点集合' : '最终节点集合与基础方案一致',
    },
    {
      label: '增强图谱可见',
      value: `${graphOptionVisibleOverlayNodeCount.value} 节点 / ${graphOptionVisibleOverlayEdgeCount.value} 关系`,
      detail: '只统计已校验、已确认且开启规划的 overlay',
    },
    {
      label: '当前路径命中',
      value: `${graphOptionPathOverlayNodeCount.value} 节点 / ${graphOptionPathOverlayEdgeCount.value} 关系`,
      detail: graphOptionPathOverlayNodeCount.value || graphOptionPathOverlayEdgeCount.value ? '当前目标已消费增强内容' : '当前目标暂未消费增强内容',
    },
    {
      label: '增强方案状态',
      value: graphOptionStatusLabel(enhanced.status),
      detail: enhanced.status === 'unavailable' ? formatPreviewReason(enhanced.blocked_reason) || '需要先处理阻塞项' : '可继续选择并确认应用',
    },
  ]
})
const graphOptionChangeBadges = computed(() => {
  const enhanced = graphOptionEnhancedVariant.value
  if (!graphOptionPreview.value || !enhanced) return []
  const badges: Array<{ label: string; type: 'success' | 'warning' | 'info' | 'danger' }> = []
  if (enhanced.status === 'unavailable') badges.push({ label: '增强方案暂不可用', type: 'danger' })
  if (graphOptionAddedCount.value) badges.push({ label: `新增 ${graphOptionAddedCount.value} 个知识点`, type: 'success' })
  if (graphOptionRemovedCount.value) badges.push({ label: `移除 ${graphOptionRemovedCount.value} 个节点`, type: 'warning' })
  if (graphOptionPathOverlayNodeCount.value || graphOptionPathOverlayEdgeCount.value) badges.push({ label: `路径命中 ${graphOptionPathOverlayNodeCount.value} 节点 / ${graphOptionPathOverlayEdgeCount.value} 关系`, type: 'success' })
  if (enhanced.order_changed) badges.push({ label: '学习顺序变化', type: 'success' })
  if (enhanced.stage_changed) badges.push({ label: '阶段划分变化', type: 'success' })
  if (enhanced.budget_changed) badges.push({ label: '预算估算变化', type: 'success' })
  if (!badges.length && (graphOptionVisibleOverlayNodeCount.value || graphOptionVisibleOverlayEdgeCount.value)) badges.push({ label: '增强图谱已纳入但未命中当前路径', type: 'info' })
  if (!badges.length) badges.push({ label: '基础与增强方案一致', type: 'info' })
  return badges
})
const graphOptionDefenseSummary = computed(() => {
  const enhanced = graphOptionEnhancedVariant.value
  if (!graphOptionPreview.value || !enhanced) return ''
  if (enhanced.status === 'unavailable') {
    return `答辩口径：增强方案当前不可用，原因是 ${formatPreviewReason(enhanced.blocked_reason) || '图谱状态无法规划'}，系统不会允许确认该方案。`
  }
  if (graphOptionAddedCount.value || graphOptionRemovedCount.value) {
    return '答辩口径：增强图谱已经改变最终路径节点集合，说明已审核 overlay 可以影响规划，但仍需要用户确认后才保存正式版本。'
  }
  if (graphOptionHasPathLevelChange.value) {
    return '答辩口径：节点集合不变时，overlay 关系仍可能改变依赖顺序、阶段划分或预算评估，因此需要单独展示路径级影响。'
  }
  if (graphOptionVisibleOverlayNodeCount.value || graphOptionVisibleOverlayEdgeCount.value) {
    return '答辩口径：overlay 已进入增强图谱但当前目标没有命中，说明扩展内容不会无条件污染所有学习路径。'
  }
  return '答辩口径：当前没有可规划的已审核 overlay，基础方案与增强方案保持一致。'
})
const overlayPreflightTagType = computed(() => {
  if (overlayPreflight.value?.status === 'ok') return 'success'
  if (overlayPreflight.value?.status === 'blocked') return 'danger'
  return 'warning'
})
const overlayPreflightStatusLabel = computed(() => {
  if (overlayPreflight.value?.status === 'ok') return '可生成对比'
  if (overlayPreflight.value?.status === 'blocked') return '阻塞'
  return '需关注'
})
const overlayPreflightIssues = computed(() => [
  ...(overlayPreflight.value?.blocking_items || []),
  ...(overlayPreflight.value?.warning_items || []),
])
const graphOptionEntryGuideVisible = computed(() => (
  activeAdjustmentTool.value === 'graph_options'
  && normalizeRouteQueryValue(route.query.from) === 'knowledge_overlay'
  && !graphOptionPreview.value
))
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
const feedbackDiffDetails = computed(() => normalizeDiffDetails(
  feedbackPreview.value?.diff as ReplanDiff | undefined,
  feedbackPreview.value?.diff_details,
))
const feedbackDiffEntries = computed(() => REPLAN_DIFF_KEYS
  .map((key) => ({
    key: feedbackDiffLabel(key),
    values: (feedbackDiffDetails.value[key] || []).map((item) => item.node_name),
  }))
  .filter((item) => item.values.length > 0))
const feedbackReadableCards = computed(() => {
  const preview = feedbackPreview.value
  if (!preview) return []
  return [
    {
      label: '识别到的意图',
      value: feedbackIntentLabel(preview.intent_type),
      detail: `${feedbackIntentPlainText(preview.intent_type)}，置信度 ${formatPercent(preview.confidence)}`,
    },
    {
      label: '影响说明',
      value: feedbackImpactTitle.value,
      detail: feedbackImpactDetail.value,
    },
    {
      label: '预算变化',
      value: feedbackBudgetChangeTitle.value,
      detail: feedbackBudgetChangeDetail.value,
    },
    {
      label: '已掌握节点证据',
      value: feedbackKnownNodeEvidenceTitle.value,
      detail: feedbackKnownNodeEvidenceDetail.value,
    },
  ]
})
const feedbackTargetPathModeLabel = computed(() => {
  const mode = feedbackPreview.value?.controlled_parameters?.path_mode
  return typeof mode === 'string' && mode ? pathModeLabel(mode) : ''
})
const feedbackImpactTitle = computed(() => {
  if (!feedbackPreview.value) return '暂无预览'
  const added = feedbackDiffCount('added')
  const removed = feedbackDiffCount('removed')
  const orderChanged = feedbackDiffCount('order_changed')
  const stageChanged = feedbackDiffCount('stage_changed')
  const completed = feedbackDiffCount('completed') || feedbackPreview.value.known_node_draft?.node_ids.length || 0
  if (feedbackPreview.value.intent_type === 'mark_known_nodes') return `锁定 ${completed} 个已掌握节点`
  const parts: string[] = []
  if (added || removed) parts.push(`新增 ${added} 个，减少 ${removed} 个`)
  if (orderChanged) parts.push(`顺序调整 ${orderChanged} 个`)
  if (stageChanged) parts.push(`阶段调整 ${stageChanged} 个`)
  if (parts.length) return parts.join('，')
  if (feedbackTargetPathModeLabel.value) return `切换为${feedbackTargetPathModeLabel.value}`
  if (Object.keys(feedbackPreview.value.controlled_parameters || {}).length) return '调整学习参数'
  return '路径结构基本不变'
})
const feedbackImpactDetail = computed(() => {
  if (!feedbackPreview.value) return ''
  if (feedbackPreview.value.intent_type === 'mark_known_nodes') {
    return '确认后系统会记录学习完成事件，并避免这些知识点在待学路径里重复出现。'
  }
  const added = feedbackDiffCount('added')
  const removed = feedbackDiffCount('removed')
  const unchanged = feedbackDiffCount('unchanged')
  const orderChanged = feedbackDiffCount('order_changed')
  const stageChanged = feedbackDiffCount('stage_changed')
  const modePrefix = feedbackTargetPathModeLabel.value ? `目标路径模式：${feedbackTargetPathModeLabel.value}。` : ''
  if (added || removed || orderChanged || stageChanged) {
    return `${modePrefix}预览里有 ${added} 个新增知识点、${removed} 个移出待学路径、${orderChanged} 个顺序变化、${stageChanged} 个阶段变化，另有 ${unchanged} 个保持不变。`
  }
  return `${modePrefix}这次反馈主要改变路径模式、时间或理论/实践权重，节点集合可能暂时不变。`
})
const feedbackBudgetChangeTitle = computed(() => formatFeedbackBudgetTitle(feedbackPreview.value?.budget_delta))
const feedbackBudgetChangeDetail = computed(() => formatFeedbackBudgetDetail(feedbackPreview.value?.budget_delta))
const feedbackKnownNodeEvidenceRows = computed(() => (
  feedbackPreview.value?.known_node_draft?.evidence ?? []
).map((item, index) => ({
  key: String(item.node_id ?? item.node_name ?? index),
  nodeName: stringifyPreviewValue(item.node_name ?? item.node_id ?? '知识点'),
  matchedText: item.matched_text == null ? '' : stringifyPreviewValue(item.matched_text),
})))
const feedbackKnownNodeEvidenceTitle = computed(() => {
  const draft = feedbackPreview.value?.known_node_draft
  if (!draft) return '未涉及已掌握节点'
  return `${draft.node_ids.length} 个节点待确认`
})
const feedbackKnownNodeEvidenceDetail = computed(() => {
  const rows = feedbackKnownNodeEvidenceRows.value
  if (!feedbackPreview.value?.known_node_draft) return '这次反馈不会把知识点标记为已掌握。'
  if (!rows.length) return '后端识别到已掌握节点，但没有返回额外命中文本。'
  return rows.map((item) => item.matchedText ? `${item.nodeName}（${item.matchedText}）` : item.nodeName).join('、')
})
const selectedResourceStage = computed(() => (
  planResources.value?.stages.find((stage) => stage.stage_name === selectedStageName.value) ?? planResources.value?.stages[0] ?? null
))
const selectedResourceNode = computed(() => (
  selectedResourceStage.value?.nodes.find((node) => node.node_id === selectedNodeId.value) ?? selectedResourceStage.value?.nodes[0] ?? null
))
const totalResourceCount = computed(() => (
  planResources.value?.stages.reduce((sum, stage) => sum + countStageResources(stage), 0) ?? 0
))
const selectedStageResourceCount = computed(() => (
  selectedResourceStage.value ? countStageResources(selectedResourceStage.value) : 0
))
const selectedNodeResourceCount = computed(() => selectedResourceNode.value?.resources.length ?? 0)
const missingResourceNodeCount = computed(() => (
  planResources.value?.stages.reduce((sum, stage) => sum + stage.nodes.filter((node) => !node.resources.length).length, 0) ?? 0
))
const resourceLoadingText = computed(() => '正在读取已绑定资源...')

function defaultResourceStageName(stages: StageResourceGroup[]) {
  return stages.find((stage) => stage.stage_name === DEFAULT_RESOURCE_STAGE_NAME)?.stage_name
    || stages[0]?.stage_name
    || ''
}

function syncResourceStageCollapse(stages: StageResourceGroup[]) {
  const availableStageNames = new Set(stages.map((stage) => stage.stage_name))
  const fallbackStageName = defaultResourceStageName(stages)
  activeResourceNodeStages.value = activeResourceNodeStages.value.filter(
    (stageName) => availableStageNames.has(stageName),
  )
  activeResourceOverviewStages.value = activeResourceOverviewStages.value.filter(
    (stageName) => availableStageNames.has(stageName),
  )
  if (!activeResourceNodeStages.value.length && fallbackStageName) {
    activeResourceNodeStages.value = [fallbackStageName]
  }
}

function ensureResourceStageExpanded(stageName: string) {
  if (!stageName || activeResourceNodeStages.value.includes(stageName)) return
  activeResourceNodeStages.value = [...activeResourceNodeStages.value, stageName]
}

async function loadOverlayPreflight() {
  if (!projectId.value) {
    overlayPreflight.value = null
    return
  }
  try {
    overlayPreflight.value = await graphApi.getOverlayPreflight(projectId.value)
  } catch {
    overlayPreflight.value = null
  }
}

function resetPlanResourceCache() {
  planResources.value = null
  resourcesLoadedPathId.value = ''
  activeResourceNodeStages.value = []
  activeResourceOverviewStages.value = []
}

async function ensurePlanResourcesLoaded(force = false) {
  if (!planStore.currentPlan?.id) return
  if (!force && resourcesLoadedPathId.value === planStore.currentPlan.id && planResources.value) return
  await loadPlanResources()
}

async function loadPlanResources() {
  if (!projectId.value || !planStore.currentPlan?.id) {
    resetPlanResourceCache()
    return
  }
  resourcesLoading.value = true
  try {
    planResources.value = await resourceApi.getPlanResources(projectId.value, planStore.currentPlan.id)
    resourcesLoadedPathId.value = planStore.currentPlan.id
    syncResourceStageCollapse(planResources.value.stages)
    if (!selectedStageName.value) {
      selectedStageName.value = planStore.currentPlan.stages[0]?.stage_name || ''
    }
    if (!selectedNodeId.value) {
      selectedNodeId.value = selectedStageTasks.value[0]?.node_id || ''
    }
  } catch (e: any) {
    if (!planResources.value) {
      resetPlanResourceCache()
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

function applyFeedbackExample(text: string) {
  feedbackText.value = text
  openAdjustmentTool('feedback')
}

function syncAdjustmentToolFromRoute() {
  const requestedTool = normalizeAdjustmentTool(route.query.tool)
  if (requestedTool) {
    openAdjustmentTool(requestedTool)
  }
}

function normalizeAdjustmentTool(value: unknown): AdjustmentTool | null {
  const nextValue = normalizeRouteQueryValue(value)
  if (nextValue === 'variants' || nextValue === 'graph_options' || nextValue === 'feedback') {
    return nextValue
  }
  return null
}

function normalizeRouteQueryValue(value: unknown): string | null {
  const nextValue = Array.isArray(value) ? value[0] : value
  return typeof nextValue === 'string' && nextValue.trim() ? nextValue.trim() : null
}

function graphOptionChangeLabels(variant: VariantSummary) {
  const labels: string[] = []
  const pathOverlayNodes = variant.path_overlay_node_ids?.length || 0
  const pathOverlayEdges = variant.path_overlay_edge_ids?.length || 0
  if (pathOverlayNodes || pathOverlayEdges) {
    labels.push(`路径命中 ${pathOverlayNodes} 个扩展知识点 / ${pathOverlayEdges} 条扩展关系`)
  }
  if (variant.order_changed) labels.push('学习顺序变化')
  if (variant.stage_changed) labels.push('阶段划分变化')
  if (variant.budget_changed) labels.push('预算估算变化')
  return labels
}

function graphOptionChangeSuffix(variant: VariantSummary) {
  const labels = graphOptionChangeLabels(variant)
  return labels.length ? `同时出现：${labels.join('、')}。` : ''
}

function graphOptionImpactText(variant: VariantSummary) {
  if (variant.status === 'unavailable') {
    return `该方案暂不可用：${formatPreviewReason(variant.blocked_reason) || '当前图谱状态无法生成路径'}`
  }
  const added = variant.added_node_ids?.length || 0
  const removed = variant.removed_node_ids?.length || 0
  const visibleOverlayNodes = variant.visible_overlay_node_ids?.length ?? variant.overlay_node_ids?.length ?? 0
  const visibleOverlayEdges = variant.visible_overlay_edge_ids?.length ?? variant.overlay_edge_ids?.length ?? 0
  const changeLabels = graphOptionChangeLabels(variant)
  if (variant.graph_option === 'baseline') {
    return added ? `基础方案不会纳入增强方案中的 ${added} 个扩展知识点。` : '基础方案只使用领域基线图谱，适合保守生成路径。'
  }
  if (added || removed) {
    return `增强方案会新增 ${added} 个已审核知识点，移除 ${removed} 个不适用节点。${graphOptionChangeSuffix(variant)}`
  }
  if (changeLabels.length) {
    return `增强方案不会新增知识点，但${changeLabels.join('、')}，因此仍会影响当前路径。`
  }
  if (visibleOverlayNodes || visibleOverlayEdges) {
    return `增强图谱已纳入 ${visibleOverlayNodes} 个已审核扩展知识点和 ${visibleOverlayEdges} 条关系，但当前目标路径暂未命中这些扩展。`
  }
  return '当前没有可用于规划的已审核扩展图谱，因此增强方案会与基础方案一致。'
}

function formatPreviewReason(value?: string | null) {
  return formatErrorCode(value) || value || ''
}

function feedbackDiffLabel(key: string) {
  const map: Record<string, string> = {
    added: '新增知识点',
    removed: '移除知识点',
    unchanged: '保持不变',
    order_changed: '顺序变化',
    stage_changed: '阶段变化',
    completed: '已完成锁定',
    skipped: '已跳过',
    pending: '待重规划',
    blocked: '依赖阻断',
  }
  return map[key] || key
}

function normalizeDiffDetails(diff?: ReplanDiff | null, diffDetails?: ReplanDiffDetails | null) {
  return REPLAN_DIFF_KEYS.reduce((result, key) => {
    const detailedItems = diffDetails?.[key]
    if (detailedItems?.length) {
      result[key] = detailedItems
      return result
    }
    const nodeIds = diff?.[key]
    if (nodeIds?.length) {
      result[key] = nodeIds.map((nodeId) => ({ node_id: nodeId, node_name: nodeId }))
    }
    return result
  }, {} as ReplanDiffDetails)
}

function feedbackDiffCount(key: ReplanDiffKey) {
  return feedbackDiffDetails.value[key]?.length || 0
}

function replanDiffCount(key: ReplanDiffKey) {
  return replanDiffDetails.value[key]?.length || 0
}

function replanModeLabelFrom(mode?: string | null) {
  const map: Record<string, string> = {
    progress_aware: '进度感知',
    profile_update: '画像更新',
    feedback_confirm: '反馈确认',
    variant_confirm: '变体确认',
  }
  return mode ? map[mode] || mode : '未知'
}

function feedbackIntentPlainText(intent: string) {
  const map: Record<string, string> = {
    compress_time: '想缩短学习路径或减少时间压力',
    increase_practice: '想增加项目、练习和动手内容',
    increase_theory: '想加强原理、推导和理论理解',
    adjust_deadline: '想按新的截止时间调整节奏',
    mark_known_nodes: '想把已经掌握的知识点从待学安排里锁定',
  }
  return map[intent] || '系统识别到一类可控调整'
}

function getNumberField(record: Record<string, unknown> | undefined, keys: string[]) {
  for (const key of keys) {
    const value = record?.[key]
    if (typeof value === 'number' && Number.isFinite(value)) return value
  }
  return null
}

function formatHourDelta(value: number) {
  const rounded = Math.abs(Math.round(value * 10) / 10)
  return Number.isInteger(rounded) ? `${rounded}` : `${rounded.toFixed(1)}`
}

function formatFeedbackBudgetTitle(record?: Record<string, unknown>) {
  const deltaHours = getNumberField(record, ['delta_hours', 'total_hours_delta'])
  if (deltaHours != null && deltaHours > 0) return `预计增加 ${formatHourDelta(deltaHours)} 小时`
  if (deltaHours != null && deltaHours < 0) return `预计减少 ${formatHourDelta(deltaHours)} 小时`
  const previous = getNumberField(record, ['previous_total_hours'])
  const preview = getNumberField(record, ['preview_total_hours'])
  if (previous != null && preview != null) return `总投入 ${previous} -> ${preview} 小时`
  return '预算基本不变'
}

function formatFeedbackBudgetDetail(record?: Record<string, unknown>) {
  const previous = getNumberField(record, ['previous_total_hours'])
  const preview = getNumberField(record, ['preview_total_hours'])
  const previousStatus = budgetStatusLabel(record?.['previous_budget_status'])
  const previewStatus = budgetStatusLabel(record?.['preview_budget_status'])
  if (previous != null && preview != null) {
    return `从 ${previous} 小时调整到 ${preview} 小时，预算状态 ${previousStatus} -> ${previewStatus}。`
  }
  return '后端没有返回可量化的学时变化，先按节点差异和路径模式判断影响。'
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

function rememberPlanWriteResult(result: ReplanResult | VariantConfirmResponse | null, fallbackMode: string) {
  if (!result?.diff) return
  planStore.setLastReplanResult({
    ...result,
    mode: result.mode || fallbackMode,
    diff: result.diff,
  } as ReplanResult)
}

async function refreshAfterPlanWrite() {
  if (!projectId.value) return
  await planStore.loadLatest(projectId.value)
  resetPlanResourceCache()
  await Promise.all([
    explanationState.load(),
    activeTab.value === 'resources' ? ensurePlanResourcesLoaded(true) : Promise.resolve(),
    loadOverlayPreflight(),
  ])
}

async function loadPath() {
  loadError.value = ''
  const previousProjectId = projectId.value
  const previousPlanId = planStore.currentPlan?.id
  selectedStageName.value = ''
  selectedNodeId.value = ''
  clearPreviews()
  planStore.clearLastReplanResult()
  if (!projectId.value) {
    planResources.value = null
    overlayPreflight.value = null
    planStore.currentPlan = null
    explanationState.clear()
    return
  }
  try {
    await settingsStore.refreshServerStatus().catch(() => undefined)
    await planStore.loadLatest(projectId.value)
    if (projectId.value !== previousProjectId || planStore.currentPlan?.id !== previousPlanId) {
      resetPlanResourceCache()
      explanationState.clear()
    }
    await Promise.all([
      explanationState.load(llmExplanationPolish.value),
      activeTab.value === 'resources' ? ensurePlanResourcesLoaded(true) : Promise.resolve(),
      loadOverlayPreflight(),
    ])
  } catch (e: any) {
    resetPlanResourceCache()
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

onMounted(() => {
  syncAdjustmentToolFromRoute()
  void loadPath()
})

watch(() => route.query.tool, () => syncAdjustmentToolFromRoute())
watch(activeTab, (tab) => {
  if (tab === 'resources') {
    void ensurePlanResourcesLoaded()
  }
})
watch(projectId, () => loadPath())
watch(currentPlanId, (nextPlanId, previousPlanId) => {
  if (previousPlanId && nextPlanId !== previousPlanId) {
    clearPreviews()
    resetPlanResourceCache()
  }
})

function handleReplanScenario(scenario: (typeof quickReplanScenarios)[number]) {
  if (scenario.action === 'preview') {
    openAdjustmentTool('variants')
    return
  }
  void handleReplan(scenario.mode)
}

async function confirmDirectReplan(mode: QuickReplanMode) {
  const scenario = quickReplanScenarios.find((item) => 'mode' in item && item.mode === mode)
  const title = mode === 'progress_aware' ? '确认按学习进度重规划？' : '确认按最新画像重规划？'
  const message = mode === 'progress_aware'
    ? '系统会保留已完成、已跳过记录，并把未完成部分生成新的正式路径版本。'
    : '系统会按最新画像和时间预算重建正式路径，当前路径会保留为历史版本。'
  try {
    await ElMessageBox.confirm(
      `${scenario?.title || replanModeLabelFrom(mode)}：${message}`,
      title,
      {
        confirmButtonText: '确认生成新版',
        cancelButtonText: '先不改',
        type: 'warning',
        distinguishCancelAndClose: true,
      },
    )
    return true
  } catch {
    return false
  }
}

function normalizeQuickReplanMode(mode: string): QuickReplanMode | null {
  if (mode === 'progress_aware' || mode === 'profile_update') return mode
  return null
}

async function handleReplan(mode: string) {
  if (!projectId.value) return
  const replanMode = normalizeQuickReplanMode(mode)
  if (!replanMode) return
  const confirmed = await confirmDirectReplan(replanMode)
  if (!confirmed) return
  try {
    const result = await planStore.replan(projectId.value, replanMode, { pathMode: planStore.currentPlan?.path_mode })
    clearPreviews()
    resetPlanResourceCache()
    await explanationState.load()
    activeTab.value = 'diff'
    if (result.refresh_error) {
      ElMessage.warning(result.refresh_error)
    } else {
      ElMessage.success('重规划完成')
    }
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
    const result = await planApi.confirmVariant(projectId.value, variantPreview.value.variant_preview_id, selectedVariant.value.variant_id)
    rememberPlanWriteResult(result, 'variant_confirm')
    clearPreviews()
    await refreshAfterPlanWrite()
    activeTab.value = result.diff ? 'diff' : 'timeline'
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
    await loadOverlayPreflight()
    if (overlayPreflight.value?.status === 'blocked') {
      graphOptionPreview.value = null
      previewUnsafeMessage.value = overlayPreflight.value.summary || '增强图谱存在阻塞问题，请先处理后再生成路径对比。'
      return
    }
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
    const result = await planApi.confirmVariant(
      projectId.value,
      graphOptionPreview.value.variant_preview_id,
      selectedGraphOptionVariant.value.variant_id,
    )
    rememberPlanWriteResult(result, 'variant_confirm')
    clearPreviews()
    await refreshAfterPlanWrite()
    activeTab.value = result.diff ? 'diff' : 'timeline'
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
    const result = await planApi.confirmFeedback(projectId.value, feedbackPreview.value.feedback_preview_id)
    rememberPlanWriteResult(result, 'feedback_confirm')
    clearPreviews()
    await refreshAfterPlanWrite()
    activeTab.value = 'diff'
    ElMessage.success('反馈预览已保存为新的正式路径版本')
  } catch (error: any) {
    handlePreviewError(error, '应用反馈预览失败')
  } finally {
    feedbackConfirming.value = false
  }
}

function applyPlanResources(data: PlanResourcesResponse) {
  planResources.value = data
  resourcesLoadedPathId.value = data.path_id
  syncResourceStageCollapse(data.stages)
  if (!selectedStageName.value) {
    selectedStageName.value = planStore.currentPlan?.stages[0]?.stage_name || data.stages[0]?.stage_name || ''
  }
  if (!selectedNodeId.value) {
    selectedNodeId.value = selectedStageTasks.value[0]?.node_id || data.stages[0]?.nodes[0]?.node_id || ''
  }
}

async function recommendSelectedNodeResources() {
  if (!projectId.value || !planStore.currentPlan?.id || !selectedNodeId.value) {
    ElMessage.warning('请先选择目标知识点')
    return
  }
  selectedNodeRecommendLoading.value = true
  try {
    const data = await resourceApi.recommendPlanResources(projectId.value, planStore.currentPlan.id, {
      stage_name: selectedStageName.value,
      node_id: selectedNodeId.value,
    })
    applyPlanResources(data)
    activeTab.value = 'resources'
    ElMessage.success('已为当前知识点补充资源')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '补充当前知识点资源失败')
  } finally {
    selectedNodeRecommendLoading.value = false
  }
}

async function recommendResources() {
  if (!projectId.value || !planStore.currentPlan?.id) return
  recommendLoading.value = true
  try {
    const data = await resourceApi.recommendPlanResources(projectId.value, planStore.currentPlan.id)
    applyPlanResources(data)
    activeTab.value = 'resources'
    ElMessage.success('已批量补充缺资源知识点')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '批量补充资源失败')
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

const replanDiffDetails = computed(() => normalizeDiffDetails(
  planStore.lastReplanResult?.diff ?? undefined,
  planStore.lastReplanResult?.diff_details,
))
const replanModeLabel = computed(() => replanModeLabelFrom(planStore.lastReplanResult?.mode))
const replanDiffSummaryCards = computed(() => {
  const mode = planStore.lastReplanResult?.mode
  if (mode === 'progress_aware' || mode === 'feedback_confirm') {
    return [
      {
        key: 'completed',
        label: '已完成锁定',
        value: `${replanDiffCount('completed')} 个`,
        detail: '进入学习历史，不会重复安排',
      },
      {
        key: 'pending',
        label: '继续学习',
        value: `${replanDiffCount('pending')} 个`,
        detail: '仍需要继续学习或重新排序',
      },
      {
        key: 'skipped',
        label: '已跳过',
        value: `${replanDiffCount('skipped')} 个`,
        detail: '按学习记录从待学路径中避开',
      },
      {
        key: 'blocked',
        label: '依赖阻断',
        value: `${replanDiffCount('blocked')} 个`,
        detail: '因前置被跳过或移除暂不安排',
      },
    ]
  }
  return [
    {
      key: 'added',
      label: '新增',
      value: `${replanDiffCount('added')} 个`,
      detail: '新版路径新增的待学知识点',
    },
    {
      key: 'removed',
      label: '移出待学',
      value: `${replanDiffCount('removed')} 个`,
      detail: '不再出现在新版待学路径中',
    },
    {
      key: 'unchanged',
      label: '保持',
      value: `${replanDiffCount('unchanged')} 个`,
      detail: '继续沿用原路径安排',
    },
    {
      key: 'order_changed',
      label: '顺序变化',
      value: `${replanDiffCount('order_changed')} 个`,
      detail: '节点仍保留，但学习先后位置变化',
    },
    {
      key: 'stage_changed',
      label: '阶段变化',
      value: `${replanDiffCount('stage_changed')} 个`,
      detail: '节点仍保留，但阶段划分变化',
    },
  ]
})
const replanDiffHumanSummary = computed(() => {
  if (!planStore.lastReplanResult?.diff) return '暂无可展示的重规划差异。'
  const added = replanDiffCount('added')
  const removed = replanDiffCount('removed')
  const completed = replanDiffCount('completed')
  const pending = replanDiffCount('pending')
  const blocked = replanDiffCount('blocked')
  const orderChanged = replanDiffCount('order_changed')
  const stageChanged = replanDiffCount('stage_changed')
  if (completed || pending || blocked) {
    return `这次重点是承认学习进度：${completed} 个已完成节点被锁定，${pending} 个节点继续参与后续安排，${blocked} 个节点因前置状态暂不安排。`
  }
  return `这次生成了新版路径：新增 ${added} 个知识点，移出 ${removed} 个待学节点，${orderChanged} 个节点顺序变化，${stageChanged} 个节点阶段变化。`
})

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
  ensureResourceStageExpanded(selectedStageName.value)
  if (!selectedStageTasks.value.some((task) => task.node_id === selectedNodeId.value)) {
    selectedNodeId.value = selectedStageTasks.value[0]?.node_id || ''
  }
})

function selectResourceNode(stageName: string, nodeId: string) {
  selectedStageName.value = stageName
  selectedNodeId.value = nodeId
  ensureResourceStageExpanded(stageName)
}

function resourceStageCollapseTitle(stage: StageResourceGroup) {
  const resourceCount = countStageResources(stage)
  return `${stage.stage_name} · ${stage.nodes.length} 个知识点 · ${resourceCount} 条资源`
}

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

function resourcePreferenceLabel(preferenceMatch?: string | null) {
  if (preferenceMatch === 'preferred') return '匹配偏好'
  if (preferenceMatch === 'available') return '相关保留'
  if (preferenceMatch === 'mixed') return '混合资料'
  return ''
}

function resourcePreferenceTagType(preferenceMatch?: string | null): '' | 'success' | 'warning' | 'danger' | 'info' {
  if (preferenceMatch === 'preferred') return 'success'
  if (preferenceMatch === 'available') return 'info'
  if (preferenceMatch === 'mixed') return 'warning'
  return ''
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

function pathModeSourceLabelFrom(source?: string | null) {
  const map: Record<string, string> = {
    explicit_request: '显式选择',
    project_path_mode: '项目设置',
    learner_profile_preference: '画像偏好',
    standard_fallback: '默认标准',
    variant_preview: '变体预览',
  }
  return source ? map[source] || source : ''
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
.path-dashboard-card {
  margin-bottom: 20px;
}
.path-hero {
  display: flex;
  justify-content: space-between;
  gap: var(--lp-space-4);
  align-items: flex-start;
  padding: var(--lp-space-4);
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: var(--lp-radius-lg);
  background: linear-gradient(135deg, var(--el-color-primary-light-9), var(--el-fill-color-blank));
}
.path-hero-main {
  min-width: 0;
}
.hero-eyebrow {
  margin: 0 0 8px;
  color: var(--el-color-primary);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.path-hero h1 {
  margin: 0;
  font-size: 22px;
  line-height: 1.3;
}
.hero-goal {
  display: -webkit-box;
  max-width: 680px;
  margin: var(--lp-space-1) 0 0;
  overflow: hidden;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.hero-tags,
.path-hero-actions,
.path-display-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.hero-tags {
  margin-top: var(--lp-space-2);
}

.path-summary-bar {
  margin: var(--lp-space-3) 0;
}
.path-hero-actions {
  justify-content: flex-end;
}
.path-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 16px 0;
}
.path-stat-card {
  padding: 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: var(--el-fill-color-light);
}
.path-stat-card span,
.path-stat-card small,
.path-display-row span {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.path-stat-card strong {
  display: block;
  margin: 6px 0;
  color: var(--el-text-color-primary);
  font-size: 22px;
}
.path-display-row {
  justify-content: space-between;
  margin-bottom: var(--lp-space-2);
}
.display-mode-hint {
  margin-bottom: 16px;
}
.adjustment-workbench {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-start;
  padding: 20px;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 16px;
  background: linear-gradient(135deg, var(--el-color-primary-light-9), var(--el-fill-color-blank));
}
.adjustment-workbench-main {
  min-width: 0;
}
.adjustment-workbench h2 {
  margin: 0;
  font-size: 22px;
  line-height: 1.4;
}
.adjustment-workbench p:not(.hero-eyebrow) {
  max-width: 720px;
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 14px;
  line-height: 1.7;
}
.adjustment-safety-steps {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.adjustment-safety-steps span {
  padding: 8px 10px;
  border-radius: 999px;
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-regular);
  font-size: 12px;
  box-shadow: 0 1px 2px rgb(0 0 0 / 5%);
}
.preview-section,
.preview-card,
.adjustment-preview-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.preview-alert {
  margin-top: 12px;
}
.preview-empty-hint,
.search-empty-guide {
  padding: 16px;
  border: 1px dashed var(--el-border-color);
  border-radius: 12px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
}
.preview-empty-hint {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.preview-empty-hint strong,
.search-empty-guide h3 {
  margin: 0;
  color: var(--el-text-color-primary);
}
.search-empty-guide p {
  margin: 8px 0 0;
  line-height: 1.7;
}
.adjustment-entry-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}
.adjustment-entry-card {
  min-height: 132px;
  padding: 16px;
  border: 1px solid var(--el-border-color);
  border-radius: 12px;
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-primary);
  cursor: pointer;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}
.adjustment-entry-card:hover {
  transform: translateY(-2px);
}
.adjustment-entry-card em,
.adjustment-card-kicker {
  color: var(--el-color-primary);
  font-size: 12px;
  font-style: normal;
  font-weight: 700;
}
.adjustment-entry-card span,
.adjustment-entry-card small {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.5;
}
.adjustment-entry-card small {
  margin-top: auto;
}
.adjustment-entry-card.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-5), 0 8px 24px rgb(64 158 255 / 10%);
}
.compact-header h3 {
  font-size: 18px;
}
.preview-card {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 16px;
}
.overlay-preflight-panel {
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: var(--el-fill-color-light);
}
.overlay-preflight-header,
.overlay-preflight-issues {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.overlay-preflight-header {
  justify-content: space-between;
}
.overlay-preflight-panel p {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}
.overlay-preflight-issues {
  color: var(--el-color-warning);
  font-size: 12px;
}
.quick-replan-card {
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  gap: 16px;
  align-items: stretch;
  padding: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: var(--el-fill-color-light);
}
.quick-replan-card h3 {
  margin: 0 0 4px;
}
.quick-replan-card p {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}
.replan-scenario-grid,
.feedback-readable-summary,
.diff-summary-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}
.replan-scenario-card {
  min-height: 128px;
  padding: 14px;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-primary);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 8px;
  text-align: left;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}
.replan-scenario-card:hover:not(:disabled) {
  border-color: var(--el-color-primary);
  box-shadow: 0 8px 20px rgb(64 158 255 / 10%);
  transform: translateY(-1px);
}
.replan-scenario-card:disabled {
  cursor: not-allowed;
  opacity: 0.62;
}
.replan-scenario-card strong {
  font-size: 16px;
  line-height: 1.4;
}
.replan-scenario-card span,
.replan-scenario-card small {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.5;
}
.replan-scenario-card small {
  margin-top: auto;
  color: var(--el-color-primary);
  font-weight: 700;
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
.graph-option-summary {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--el-color-success-light-7);
  border-radius: 14px;
  background: linear-gradient(135deg, var(--el-color-success-light-9), var(--el-fill-color-blank));
}
.graph-option-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
}
.graph-option-summary-grid article {
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: rgb(255 255 255 / 76%);
}
.graph-option-summary-grid span,
.graph-option-summary-grid small {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}
.graph-option-summary-grid strong {
  display: block;
  margin: 4px 0;
  color: var(--el-text-color-primary);
  font-size: 18px;
}
.graph-option-change-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.variant-title-row,
.feedback-input-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.feedback-example-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.feedback-example-row span {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.feedback-input-row > :first-child {
  flex: 1;
}
.feedback-readable-summary article,
.diff-summary-grid article {
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
}
.feedback-readable-summary span,
.feedback-readable-summary small,
.diff-summary-grid span,
.diff-summary-grid small {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}
.feedback-readable-summary strong,
.diff-summary-grid strong {
  display: block;
  margin: 4px 0;
  color: var(--el-text-color-primary);
  font-size: 17px;
  line-height: 1.35;
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
.known-node-evidence-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0 12px;
}
.known-node-evidence-list span {
  padding: 8px 10px;
  border: 1px solid var(--el-color-success-light-7);
  border-radius: 8px;
  background: var(--el-color-success-light-9);
  color: var(--el-text-color-primary);
  font-size: 13px;
}
.known-node-evidence-list small {
  display: block;
  margin-top: 2px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.diff-summary-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 16px;
  padding: 14px;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
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
.resource-workbench {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 16px;
  align-items: stretch;
  margin-bottom: 16px;
  padding: 18px;
  border: 1px solid var(--el-color-success-light-7);
  border-radius: 16px;
  background: linear-gradient(135deg, var(--el-color-success-light-9), var(--el-fill-color-blank));
}
.resource-workbench h3 {
  margin: 0;
  font-size: 20px;
  line-height: 1.4;
}
.resource-workbench p:not(.hero-eyebrow) {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 14px;
  line-height: 1.7;
}
.resource-stat-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.resource-stat-grid article {
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: rgb(255 255 255 / 72%);
}
.resource-stat-grid span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.resource-stat-grid strong {
  display: block;
  margin-top: 4px;
  color: var(--el-text-color-primary);
  font-size: 18px;
}
.resource-focus-layout {
  display: grid;
  grid-template-columns: minmax(220px, 0.36fr) minmax(0, 0.64fr);
  gap: 16px;
  margin-bottom: 16px;
}
.resource-node-list,
.resource-node-panel {
  padding: 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 14px;
  background: var(--el-fill-color-light);
}
.resource-node-stage-collapse,
.resource-overview-collapse {
  border-top: 0;
  border-bottom: 0;
}
.resource-node-stage-collapse :deep(.el-collapse-item__header) {
  min-height: 42px;
  height: auto;
  padding: 8px 0;
  background: transparent;
  font-weight: 700;
  line-height: 1.4;
}
.resource-node-stage-collapse :deep(.el-collapse-item__wrap) {
  background: transparent;
}
.resource-node-stage-collapse :deep(.el-collapse-item__content) {
  padding-bottom: 12px;
}
.resource-node-button {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-fill-color-blank);
  color: var(--el-text-color-primary);
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  gap: 8px;
  text-align: left;
}
.resource-node-button + .resource-node-button {
  margin-top: 8px;
}
.resource-node-button span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  white-space: nowrap;
}
.resource-node-button.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-5);
}
.featured-resource-card {
  margin-top: 12px;
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
.resource-preference-reason,
.resource-meta {
  color: #909399;
  font-size: 12px;
  margin-top: 8px;
}
.resource-preference-reason {
  color: #67c23a;
}
.path-empty-card {
  min-height: 360px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.path-empty-card :deep(.el-card__body) {
  width: 100%;
}
.path-loading-panel {
  min-height: 260px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}
.path-loading-panel h3,
.empty-action-panel h3 {
  margin: 0 0 8px;
  color: var(--el-text-color-primary);
}
.path-loading-panel p,
.empty-action-panel p {
  max-width: 520px;
  margin: 0 auto 14px;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}
.empty-action-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.empty-action-panel.compact p {
  margin-bottom: 10px;
}
.empty-action-row {
  display: flex;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .page-container {
    padding: 12px;
  }

  .path-hero,
  .adjustment-workbench,
  .quick-replan-card,
  .variant-title-row,
  .feedback-input-row,
  .section-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 10px;
  }

  .path-hero,
  .adjustment-workbench {
    padding: 18px;
  }

  .path-hero h1 {
    font-size: 22px;
  }

  .path-hero-actions,
  .path-display-row,
  .adjustment-safety-steps {
    justify-content: flex-start;
    width: 100%;
  }

  .path-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .resource-workbench,
  .resource-focus-layout {
    grid-template-columns: 1fr;
  }

  .resource-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .search-toolbar,
  .resources-actions,
  .resource-card__header,
  .resource-node-button,
  .empty-action-row {
    flex-direction: column;
    align-items: stretch;
  }

  .resource-node-button span {
    white-space: normal;
  }

  .path-empty-card {
    min-height: 300px;
  }

  .path-loading-panel {
    min-height: 220px;
    padding: 12px;
  }

  :deep(.el-tabs__nav) {
    flex-wrap: wrap;
  }
}
</style>
