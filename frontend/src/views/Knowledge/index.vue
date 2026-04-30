<template>
  <div class="page-container" ref="pageRef">
    <el-card
      shadow="never"
      class="graph-card"
      :body-style="{ padding: 0, display: 'flex', flexDirection: 'column', height: 'calc(100vh - 160px)' }"
    >
      <template v-if="!projectId">
        <div class="empty-project-wrap">
          <el-empty description="请先在项目页选择一个项目后再查看知识图谱" />
        </div>
      </template>

      <GraphToolbar
        v-if="projectId"
        :scope="scope"
        :current-layout="layout"
        :review-mode="reviewMode"
        :loading="loading"
        :syncing="syncing"
        :entity-loading="entityLoading"
        @scope-change="onScopeChange"
        @refresh="onRefresh"
        @sync="onSync"
        @layout-change="onLayoutChange"
        @zoom-in="graphRef?.zoomIn()"
        @zoom-out="graphRef?.zoomOut()"
        @fit-view="graphRef?.fitView()"
        @search="onSearch"
        @show-entities="onShowEntities"
        @create-overlay="openOverlayDrawer"
        @toggle-fullscreen="toggleFullscreen"
        @toggle-review="reviewMode = $event"
      />

      <div
        v-if="projectId"
        class="graph-wrapper"
        v-loading="loading || syncing"
        :element-loading-text="syncing ? '正在同步知识图谱...' : '正在加载知识图谱...'"
      >
        <div class="graph-legend-wrap">
          <div class="legend-section">
            <span class="legend-title">节点颜色</span>
            <div class="legend-items">
              <span v-for="item in categoryLegend" :key="item.key" class="legend-chip">
                <span class="legend-dot" :style="{ backgroundColor: item.color }"></span>
                <span>{{ item.label }}</span>
              </span>
            </div>
          </div>

          <div class="legend-section">
            <span class="legend-title">关系说明</span>
            <div class="legend-items">
              <span v-for="item in relationLegend" :key="item.type" class="legend-chip legend-chip-edge">
                <span class="legend-line" :class="[
                  item.lineStyle === 'dashed' ? 'legend-line-dashed' : 'legend-line-solid',
                  item.hasArrow ? 'legend-line-arrow' : '',
                ]"></span>
                <span>{{ item.label }}：{{ item.description }}</span>
              </span>
            </div>
          </div>
        </div>
        <section class="graph-status-panel">
          <div>
            <strong>{{ graphScopeLabel }}</strong>
            <p>{{ graphStatusHint }}</p>
          </div>
          <div class="graph-status-meta">
            <div class="graph-status-tags">
              <el-tag size="small" type="info" effect="plain">节点 {{ graphNodeCount }}</el-tag>
              <el-tag size="small" type="info" effect="plain">关系 {{ graphEdgeCount }}</el-tag>
              <el-tag size="small" type="success" effect="plain">本地读模型</el-tag>
              <el-tag v-if="overlayPreflight" size="small" :type="overlayPreflightTagType" effect="plain">
                增强候选 {{ overlayPreflight.counts.visible_overlay_nodes }} / {{ overlayPreflight.counts.visible_overlay_edges }}
              </el-tag>
            </div>
            <div v-if="showGraphCacheDiagnostics" class="graph-cache-diagnostics" data-testid="graph-cache-diagnostics">
              <span class="graph-cache-title">缓存诊断</span>
              <el-tag
                v-for="item in graphCacheDiagnosticItems"
                :key="item.key"
                size="small"
                type="info"
                effect="plain"
              >
                {{ item.label }} {{ item.hitRateLabel }} · {{ item.sizeLabel }}
              </el-tag>
              <el-tag v-if="graphCacheStatsLoading" size="small" type="warning" effect="plain">刷新中</el-tag>
              <el-tag v-if="graphCacheStatsError" size="small" type="danger" effect="plain">{{ graphCacheStatsError }}</el-tag>
            </div>
          </div>
        </section>
        <el-alert
          v-if="projectionStatus && projectionStatus.status !== 'empty'"
          class="graph-alert"
          :type="projectionAlertType"
          :closable="false"
          show-icon
          :title="projectionStatusTitle"
        />
        <section v-if="overlayPreflight" class="overlay-preflight-panel graph-alert">
          <div class="overlay-preflight-header">
            <strong>增强图谱使用状态</strong>
            <el-tag :type="overlayPreflightTagType">{{ overlayPreflightStatusLabel }}</el-tag>
          </div>
          <p>{{ overlayPreflight.summary }}</p>
          <p class="overlay-guidance">{{ overlayPreflightGuidance }}</p>
          <div class="overlay-preflight-tags">
            <el-tag type="info" effect="plain">候选 {{ overlayPreflight.counts.active_nodes }} 节点 / {{ overlayPreflight.counts.active_edges }} 关系</el-tag>
            <el-tag type="success" effect="plain">可进入增强图谱 {{ overlayPreflight.counts.visible_overlay_nodes }} 节点 / {{ overlayPreflight.counts.visible_overlay_edges }} 关系</el-tag>
            <el-tag type="warning" effect="plain">待审核 {{ overlayPreflight.counts.nodes.pending_review + overlayPreflight.counts.edges.pending_review }}</el-tag>
            <el-tag type="danger" effect="plain">校验失败 {{ overlayPreflight.counts.nodes.invalid + overlayPreflight.counts.edges.invalid }}</el-tag>
            <el-tag type="warning" effect="plain">当前路径命中 {{ overlayPreflight.counts.path_overlay_nodes }} 节点 / {{ overlayPreflight.counts.path_overlay_edges }} 关系</el-tag>
            <el-tag v-if="overlayPreflight.counts.ignored_overlay_edges" type="warning" effect="plain">忽略关系 {{ overlayPreflight.counts.ignored_overlay_edges }}</el-tag>
          </div>
          <div v-if="overlayPreflightIssues.length" class="overlay-preflight-issues">
            <span v-for="(item, index) in overlayPreflightIssues" :key="`${item.kind}-${index}`">{{ item.message }}</span>
          </div>
        </section>
        <el-alert
          v-if="graphState === 'ready' && lastRefreshError"
          class="graph-alert"
          type="warning"
          :closable="false"
          show-icon
          :title="lastRefreshError"
        />

        <GraphCanvas
          v-if="graphState === 'ready'"
          ref="graphRef"
          :elements="elements"
          :layout="layout"
          :highlight-nodes="selectedNodeId ? [selectedNodeId] : []"
          :review-mode="reviewMode"
          @node-click="onNodeClick"
          @review-node="onReviewNode"
          @review-edge="onReviewEdge"
        />

        <div v-else-if="graphState === 'loading'" class="graph-state-wrap graph-loading-state" data-testid="graph-loading-skeleton">
          <div class="graph-skeleton-panel">
            <div class="graph-skeleton-header"></div>
            <div class="graph-skeleton-body">
              <span v-for="index in 8" :key="index" class="graph-skeleton-node"></span>
            </div>
            <p>正在整理知识节点、审核状态与扩展候选，请稍候。</p>
          </div>
        </div>

        <el-empty
          v-else-if="graphState === 'empty'"
          class="graph-state-wrap"
          :description="emptyDescription"
        >
          <el-button type="primary" @click="onRefresh">刷新</el-button>
          <el-button :loading="syncing" @click="onSync">同步图谱</el-button>
        </el-empty>

        <div v-else class="graph-state-wrap">
          <el-result
            icon="error"
            title="知识图谱加载失败"
            :sub-title="errorMessage || '请稍后重试或重新同步图谱'"
          >
            <template #extra>
              <el-space wrap>
                <el-button type="primary" @click="onRefresh">重新加载</el-button>
                <el-button :loading="syncing" @click="onSync">同步图谱</el-button>
              </el-space>
            </template>
          </el-result>
        </div>
      </div>
    </el-card>

    <NodeDetail
      v-if="selectedNode"
      :node="selectedNode"
      @review-edge="onReviewEdge"
      @set-overlay-planning="onSetOverlayPlanning"
    />
    <EntityMetadataDrawer
      v-if="entityDrawerVisible || entityLoading || entityMetadata"
      v-model="entityDrawerVisible"
      :loading="entityLoading"
      :metadata="entityMetadata"
    />

    <el-drawer v-model="overlayDrawerVisible" title="创建扩展草稿" :size="520" direction="rtl">
      <div class="overlay-drawer" v-loading="overlaySubmitting || overlayExtractionPreviewLoading">
        <DisplayModeSwitch v-model="displayMode" />
        <el-alert
          class="overlay-alert"
          type="info"
          :closable="false"
          show-icon
          title="扩展草稿会先进入项目扩展区，确认审核与规划开关后才会参与路径规划。"
        />
        <el-alert
          v-if="activeGoalDraftResolutionSessionId"
          class="overlay-alert"
          type="warning"
          :closable="false"
          show-icon
          title="来自目标理解的领域内未覆盖概念。页面打开只展示草稿收件箱；点击创建后才会生成 overlay 草稿。"
        />
        <section v-else class="overlay-subsection goal-draft-entry manual-goal-draft-entry">
          <h4>智能草稿建议</h4>
          <p>手动触发当前项目目标的覆盖分析；只有识别为领域内未覆盖概念时，才会生成待审核 overlay 草稿收件箱。</p>
          <el-button size="small" type="primary" plain :loading="manualGoalDraftLoading" @click="prepareGoalDraftFromCurrentProject">
            分析当前目标并生成推荐草稿
          </el-button>
        </section>

        <section v-if="activeGoalDraftResolutionSessionId" class="overlay-subsection goal-draft-entry" v-loading="goalDraftProposalLoading">
          <h4>系统推荐草稿收件箱</h4>
          <p>系统已根据目标理解准备推荐草稿图谱；您也可以忽略推荐，继续使用粘贴文本、搜索 URL 或已保存搜索结果手动补充。</p>
          <el-radio-group v-model="overlayDraftMode" class="draft-mode-switch">
            <el-radio-button value="goal_draft">使用系统推荐草稿</el-radio-button>
            <el-radio-button value="manual">手动补充资料</el-radio-button>
          </el-radio-group>
          <div v-if="goalDraftInboxProposal && !goalDraftProposalDismissed" class="draft-inbox-card">
            <div class="review-focus-list">
              <el-tag v-for="concept in goalDraftInboxMissingConcepts" :key="concept" type="warning" effect="plain">{{ concept }}</el-tag>
            </div>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="推荐节点">{{ goalDraftInboxCounts.nodes }}</el-descriptions-item>
              <el-descriptions-item label="推荐关系">{{ goalDraftInboxCounts.edges }}</el-descriptions-item>
              <el-descriptions-item label="推荐资源">{{ goalDraftInboxCounts.resources }}</el-descriptions-item>
              <el-descriptions-item label="安全边界">不写正式图谱，不写正式路径，需人工审核</el-descriptions-item>
            </el-descriptions>
            <div v-if="goalDraftInboxNodes.length || goalDraftInboxEdges.length || goalDraftInboxResources.length" class="candidate-card-list compact">
              <article v-for="(node, index) in goalDraftInboxNodes.slice(0, 3)" :key="`draft-node-${index}`" class="preview-candidate-card">
                <strong>{{ candidateTitle(node, `节点候选 ${index + 1}`) }}</strong>
                <p>{{ node.summary || node.legality_rationale || '待审核节点候选' }}</p>
              </article>
              <article v-for="(edge, index) in goalDraftInboxEdges.slice(0, 3)" :key="`draft-edge-${index}`" class="preview-candidate-card">
                <strong>{{ edgeCandidateSummary(edge) }}</strong>
                <p>{{ edge.legality_rationale || '待审核关系候选' }}</p>
              </article>
              <article v-for="(resource, index) in goalDraftInboxResources.slice(0, 2)" :key="`draft-resource-${index}`" class="preview-candidate-card">
                <strong>{{ candidateTitle(resource, `资源候选 ${index + 1}`) }}</strong>
                <p>{{ resource.summary || '待审核资源候选' }}</p>
              </article>
            </div>
          </div>
          <el-alert
            v-else-if="goalDraftProposalDismissed"
            class="overlay-alert"
            type="info"
            :closable="false"
            show-icon
            title="已忽略系统推荐草稿，可在下方继续手动补充资料。"
          />
          <div class="draft-inbox-actions">
            <el-button size="small" plain :loading="goalDraftProposalLoading" @click="loadGoalDraftProposal">刷新推荐草稿</el-button>
            <el-button size="small" plain @click="dismissGoalDraftProposal">忽略推荐，手动补充</el-button>
          </div>
        </section>

        <el-form v-if="manualOverlayMode" label-position="top">
          <el-form-item label="来源类型">
            <el-radio-group v-model="overlayForm.sourceType">
              <el-radio-button value="pasted_text">粘贴文本</el-radio-button>
              <el-radio-button value="search_url">搜索 URL</el-radio-button>
              <el-radio-button value="saved_search">已保存搜索</el-radio-button>
            </el-radio-group>
          </el-form-item>

          <template v-if="overlayForm.sourceType === 'pasted_text'">
            <el-form-item label="资料文本">
              <el-input
                v-model="overlayForm.rawText"
                type="textarea"
                :rows="8"
                maxlength="12000"
                show-word-limit
                placeholder="粘贴希望抽取为项目图谱扩展的资料内容"
              />
            </el-form-item>
            <el-form-item label="摘要（可选）">
              <el-input v-model="overlayForm.summary" placeholder="用于回看来源的简短摘要" />
            </el-form-item>
          </template>

          <template v-else-if="overlayForm.sourceType === 'search_url'">
            <el-form-item label="URL">
              <el-input v-model="overlayForm.url" placeholder="https://example.com/article" />
            </el-form-item>
            <el-form-item label="标题">
              <el-input v-model="overlayForm.title" placeholder="搜索结果标题" />
            </el-form-item>
            <el-form-item label="摘要片段">
              <el-input v-model="overlayForm.snippet" type="textarea" :rows="4" />
            </el-form-item>
          </template>

          <template v-else>
            <el-form-item label="已保存搜索结果">
              <el-select
                v-model="overlayForm.selectedResultIds"
                multiple
                filterable
                placeholder="选择已保存搜索结果"
                style="width: 100%"
              >
                <el-option
                  v-for="item in persistedSearchResults"
                  :key="item.result_id"
                  :label="item.title"
                  :value="item.result_id"
                />
              </el-select>
            </el-form-item>
            <el-alert
              v-if="overlayBridgeMessage"
              class="overlay-alert"
              type="success"
              :closable="false"
              show-icon
              :title="overlayBridgeMessage"
            />
          </template>

          <el-form-item label="抽取模式">
            <el-radio-group v-model="overlayForm.mode">
              <el-radio-button value="default">默认抽取</el-radio-button>
              <el-radio-button value="custom_extension">自定义扩展</el-radio-button>
            </el-radio-group>
          </el-form-item>

          <el-form-item label="AI 抽取预览">
            <el-button plain :loading="overlayExtractionPreviewLoading" @click="previewOverlayExtractionPayload">
              生成候选预览
            </el-button>
            <span class="preview-hint">先预览 LLM payload，再勾选候选并复用现有校验创建草稿。</span>
          </el-form-item>
        </el-form>

        <section v-if="overlayExtractionPreview" class="overlay-preview">
          <h4>AI 抽取预览</h4>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="节点候选">{{ selectedPreviewCounts.nodes }} / {{ overlayExtractionPreview.counts.nodes }}</el-descriptions-item>
            <el-descriptions-item label="关系候选">{{ selectedPreviewCounts.edges }} / {{ overlayExtractionPreview.counts.edges }}</el-descriptions-item>
            <el-descriptions-item label="资源候选">{{ selectedPreviewCounts.resources }} / {{ overlayExtractionPreview.counts.resources }}</el-descriptions-item>
            <el-descriptions-item label="来源数">{{ overlayExtractionPreview.source_ids.length }}</el-descriptions-item>
          </el-descriptions>
          <div class="candidate-card-list">
            <article v-for="(node, index) in normalizedPreviewPayload.nodes" :key="`preview-node-${index}`" class="preview-candidate-card">
              <label class="candidate-checkbox-row">
                <input
                  type="checkbox"
                  :checked="isPreviewCandidateSelected('nodes', index)"
                  @change="togglePreviewCandidate('nodes', index, ($event.target as HTMLInputElement).checked)"
                />
                <strong>{{ candidateTitle(node, `节点候选 ${index + 1}`) }}</strong>
              </label>
              <p>{{ node.summary || node.legality_rationale || '暂无摘要' }}</p>
              <el-tag v-if="node.confidence !== undefined" size="small" type="info">置信度 {{ node.confidence }}</el-tag>
            </article>
            <article v-for="(edge, index) in normalizedPreviewPayload.edges" :key="`preview-edge-${index}`" class="preview-candidate-card">
              <label class="candidate-checkbox-row">
                <input
                  type="checkbox"
                  :checked="isPreviewCandidateSelected('edges', index)"
                  @change="togglePreviewCandidate('edges', index, ($event.target as HTMLInputElement).checked)"
                />
                <strong>{{ edgeCandidateSummary(edge) }}</strong>
              </label>
              <p>{{ edge.legality_rationale || '暂无合法性说明' }}</p>
              <el-tag size="small" type="info">{{ edge.relation_type || 'RELATED_TO' }}</el-tag>
            </article>
            <article v-for="(resource, index) in normalizedPreviewPayload.resources" :key="`preview-resource-${index}`" class="preview-candidate-card">
              <label class="candidate-checkbox-row">
                <input
                  type="checkbox"
                  :checked="isPreviewCandidateSelected('resources', index)"
                  @change="togglePreviewCandidate('resources', index, ($event.target as HTMLInputElement).checked)"
                />
                <strong>{{ candidateTitle(resource, `资源候选 ${index + 1}`) }}</strong>
              </label>
              <p>{{ resource.summary || resource.url || '暂无摘要' }}</p>
              <el-tag v-if="resource.resource_type" size="small" type="success">{{ resource.resource_type }}</el-tag>
            </article>
          </div>
          <el-alert
            v-if="overlayExtractionPreview.warnings.length"
            class="overlay-alert"
            type="warning"
            :closable="false"
            show-icon
            :title="overlayExtractionPreview.warnings.join('；')"
          />
          <el-alert
            v-if="overlayCandidateValidation"
            class="overlay-alert"
            :type="overlayCandidateValidation.summary.has_blocking_errors ? 'warning' : 'success'"
            :closable="false"
            show-icon
            :title="`预校验：通过 ${overlayCandidateValidation.counts.nodes.valid + overlayCandidateValidation.counts.edges.valid + overlayCandidateValidation.counts.resources.valid}，失败 ${overlayCandidateValidation.summary.invalid_count}，待复核 ${overlayCandidateValidation.summary.needs_review_count}`"
          />
        </section>

        <el-alert
          v-if="overlayError"
          class="overlay-alert"
          type="warning"
          :closable="false"
          show-icon
          :title="overlayError"
        />

        <section v-if="lastOverlaySession" class="overlay-result">
          <div class="section-header">
            <div>
              <h3>抽取结果</h3>
              <p v-if="showTechnicalDetails">追溯编号：{{ lastOverlaySession.session.session_id }}</p>
              <p v-else>{{ overlaySessionGuide }}</p>
            </div>
            <el-tag :type="sessionStatusMeta(lastOverlaySession.session.session_status).tagType" :title="lastOverlaySession.session.session_status">
              {{ sessionStatusMeta(lastOverlaySession.session.session_status).label }}
            </el-tag>
          </div>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="节点候选">{{ lastOverlaySession.nodes?.length || 0 }}</el-descriptions-item>
            <el-descriptions-item label="关系候选">{{ lastOverlaySession.edges?.length || 0 }}</el-descriptions-item>
            <el-descriptions-item label="资源候选">{{ lastOverlaySession.resources?.length || 0 }}</el-descriptions-item>
            <el-descriptions-item label="校验概览">
              通过 {{ overlaySessionStats.valid }}，失败 {{ overlaySessionStats.invalid }}，待复核 {{ overlaySessionStats.needsReview }}，待审核 {{ overlaySessionStats.pendingReview }}
            </el-descriptions-item>
            <el-descriptions-item label="来源数">{{ lastOverlaySession.sources?.length || 0 }}</el-descriptions-item>
          </el-descriptions>
          <el-alert
            class="overlay-alert"
            :type="overlaySessionStats.invalid ? 'warning' : 'info'"
            :closable="false"
            show-icon
            :title="overlaySessionGuide"
          />

          <section class="overlay-workflow" data-testid="overlay-workflow">
            <div class="overlay-workflow-header">
              <strong>草稿处理流程</strong>
              <span v-if="overlayWorkflowCurrentStep">当前阶段：{{ overlayWorkflowCurrentStep.title }}</span>
            </div>
            <ol class="overlay-workflow-steps">
              <li
                v-for="(step, index) in overlayWorkflowSteps"
                :key="step.key"
                class="overlay-workflow-step"
                :class="`is-${step.state}`"
              >
                <span class="overlay-workflow-index">{{ index + 1 }}</span>
                <div>
                  <div class="overlay-workflow-step-title">
                    <strong>{{ step.title }}</strong>
                    <el-tag size="small" :type="step.tagType" effect="plain">{{ step.statusLabel }}</el-tag>
                  </div>
                  <p>{{ step.description }}</p>
                </div>
              </li>
            </ol>
          </section>

          <div v-if="overlayCandidateFilterCounts.all" class="overlay-candidate-toolbar">
            <div class="overlay-candidate-toolbar-title">
              <strong>候选处理队列</strong>
              <p>建议顺序：先修复失败候选，再处理重复复核，最后确认可规划候选。</p>
            </div>
            <el-radio-group v-model="overlayCandidateFilter" size="small">
              <el-radio-button
                v-for="option in OVERLAY_CANDIDATE_FILTER_OPTIONS"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }} {{ overlayCandidateFilterCounts[option.value] }}
              </el-radio-button>
            </el-radio-group>
            <el-button size="small" type="primary" plain :disabled="!overlayCandidateRepairTarget" @click="openFirstRepairableCandidate">
              {{ overlayCandidateRepairTargetLabel }}
            </el-button>
          </div>

          <p v-if="overlayCandidateFilterCounts.all && !filteredOverlayCandidateCount" class="overlay-empty-filter">
            当前筛选下暂无候选，切换到“全部”可查看完整草稿。
          </p>

          <section v-if="filteredOverlayNodes.length || filteredOverlayEdges.length" class="overlay-subsection">
            <h4>候选校验明细</h4>
            <div class="candidate-card-list compact">
              <article v-for="node in filteredOverlayNodes" :key="node.node_id" class="preview-candidate-card">
                <div class="candidate-card-header">
                  <strong>{{ node.name || node.node_id }}</strong>
                  <el-button size="small" text type="primary" @click="openNodeCandidateEditor(node)">编辑修复</el-button>
                </div>
                <p>{{ node.summary || node.legality_rationale || '暂无摘要' }}</p>
                <el-tag size="small" :type="validationStatusMeta(node.validation_status).tagType">{{ validationStatusMeta(node.validation_status).label }}</el-tag>
                <ul v-if="node.validation_errors?.length" class="validation-errors">
                  <li v-for="error in node.validation_errors" :key="`${node.node_id}-${error}`">{{ validationErrorMessage(error) }}</li>
                </ul>
              </article>
              <article v-for="edge in filteredOverlayEdges" :key="edge.edge_id" class="preview-candidate-card">
                <div class="candidate-card-header">
                  <strong>{{ edge.source_node_id || edge.source_name_or_id }} → {{ edge.target_node_id || edge.target_name_or_id }}</strong>
                  <el-button size="small" text type="primary" @click="openEdgeCandidateEditor(edge)">编辑修复</el-button>
                </div>
                <p>{{ edge.legality_rationale || '暂无合法性说明' }}</p>
                <el-tag size="small" :type="validationStatusMeta(edge.validation_status).tagType">{{ validationStatusMeta(edge.validation_status).label }}</el-tag>
                <el-tag size="small" type="info">{{ edge.relation_type }}</el-tag>
                <ul v-if="edge.validation_errors?.length" class="validation-errors">
                  <li v-for="error in edge.validation_errors" :key="`${edge.edge_id}-${error}`">{{ validationErrorMessage(error) }}</li>
                </ul>
              </article>
            </div>
          </section>

          <section v-if="goalExtensionDraftDetails" class="overlay-subsection goal-draft-summary">
            <h4>目标缺口分析</h4>
            <el-alert
              class="overlay-alert"
              type="warning"
              :closable="false"
              show-icon
              title="扩展草稿只作为审核候选；未确认审核并开启规划前，不会进入正式路径。"
            />
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item v-if="goalExtensionDraftDetails.gap_analysis?.user_goal" label="用户目标">
                {{ goalExtensionDraftDetails.gap_analysis.user_goal }}
              </el-descriptions-item>
              <el-descriptions-item label="缺失概念">
                {{ goalDraftMissingConcepts.join('、') || '暂无' }}
              </el-descriptions-item>
              <el-descriptions-item v-if="goalExtensionDraftDetails.gap_analysis?.why_current_graph_is_insufficient" label="缺口原因">
                {{ goalExtensionDraftDetails.gap_analysis.why_current_graph_is_insufficient }}
              </el-descriptions-item>
              <el-descriptions-item v-if="showAuditDetails" label="草稿来源">
                {{ goalExtensionDraftDetails.draft_metadata?.draft_engine || 'rules' }} / {{ goalExtensionDraftDetails.draft_metadata?.prompt_version || 'unknown' }}
              </el-descriptions-item>
              <el-descriptions-item v-if="showAuditDetails" label="安全边界">
                需人工审核：{{ goalExtensionDraftDetails.draft_metadata?.requires_user_review ? '是' : '否' }}；可直接规划：{{ goalExtensionDraftDetails.draft_metadata?.can_directly_plan ? '是' : '否' }}
              </el-descriptions-item>
            </el-descriptions>
            <ul v-if="goalDraftReviewNotes.length" class="review-notes">
              <li v-for="note in goalDraftReviewNotes" :key="note">{{ note }}</li>
            </ul>
            <div v-if="showAuditDetails && goalDraftReviewFocus.length" class="review-focus-list">
              <el-tag v-for="item in goalDraftReviewFocus" :key="item" type="info" effect="plain">{{ item }}</el-tag>
            </div>
          </section>

          <section v-if="filteredOverlayResources.length" class="overlay-subsection">
            <h4>资源候选</h4>
            <article v-for="resource in filteredOverlayResources" :key="resource.resource_id" class="resource-candidate">
              <div class="candidate-card-header">
                <div class="resource-title">{{ resource.title }}</div>
                <el-button size="small" text type="primary" @click="openResourceCandidateEditor(resource)">编辑修复</el-button>
              </div>
              <p>{{ resource.summary || '暂无摘要' }}</p>
              <el-tag size="small" :type="resourceTypeMeta(resource.resource_type || 'resource').tagType" :title="resource.resource_type || 'resource'">
                {{ resourceTypeMeta(resource.resource_type || 'resource').label }}
              </el-tag>
              <el-tag size="small" :type="validationStatusMeta(resource.validation_status).tagType">{{ validationStatusMeta(resource.validation_status).label }}</el-tag>
              <el-tag size="small" type="success">绑定 {{ resource.binding_summary?.count || 0 }}</el-tag>
              <ul v-if="resource.validation_errors?.length" class="validation-errors">
                <li v-for="error in resource.validation_errors" :key="`${resource.resource_id}-${error}`">{{ validationErrorMessage(error) }}</li>
              </ul>
            </article>
          </section>

          <section v-if="showAuditDetails && lastOverlaySession.resources?.length" class="overlay-subsection">
            <h4>资源绑定</h4>
            <el-form label-position="top">
              <el-form-item label="资源">
                <el-select v-model="resourceBinding.resourceId" placeholder="选择资源候选" style="width: 100%">
                  <el-option
                    v-for="resource in lastOverlaySession.resources || []"
                    :key="resource.resource_id"
                    :label="resource.title"
                    :value="resource.resource_id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="绑定目标类型">
                <el-radio-group v-model="resourceBinding.targetType">
                  <el-radio-button value="project_node">项目节点</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="绑定目标">
                <el-select v-model="resourceBinding.targetId" filterable placeholder="选择知识点或阶段" style="width: 100%">
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
              <el-button size="small" type="primary" plain @click="bindOverlayResource">绑定资源</el-button>
            </el-form>
          </section>

          <section v-if="showTechnicalDetails" class="overlay-subsection">
            <h4>高级操作：推广到领域包</h4>
            <el-button size="small" :loading="promotionLoading" @click="previewPromotion">预览推广结果（不写入）</el-button>
            <el-descriptions v-if="promotionPreview" class="promotion-summary" :column="1" border size="small">
              <el-descriptions-item label="状态">
                <el-tag
                  size="small"
                  :type="promotionPreviewStatusMeta(promotionPreview.status).tagType"
                  :title="promotionPreviewStatusMeta(promotionPreview.status).detail || promotionPreview.status"
                >
                  {{ promotionPreviewStatusMeta(promotionPreview.status).label }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="候选数">{{ promotionPreview.candidate_count }}</el-descriptions-item>
              <el-descriptions-item label="原领域包指纹">{{ promotionPreview.baseline_pack_hash }}</el-descriptions-item>
              <el-descriptions-item label="推广后指纹">{{ promotionPreview.resulting_pack_hash }}</el-descriptions-item>
              <el-descriptions-item label="资源明细">{{ promotionPreview.resources?.length || 0 }}</el-descriptions-item>
              <el-descriptions-item label="写入说明">预览只校验，不写入领域包、Neo4j 或候选状态。</el-descriptions-item>
            </el-descriptions>
            <el-alert
              v-if="promotionPreview?.errors?.length"
              class="overlay-alert"
              type="warning"
              :closable="false"
              show-icon
              :title="promotionPreview.errors.join('; ')"
            />
            <el-input
              v-model="promotionSecret"
              class="promotion-secret"
              type="password"
              show-password
              placeholder="输入管理员密钥后确认推广"
            />
            <el-button size="small" type="danger" :loading="promotionLoading" @click="commitPromotion">确认推广</el-button>
            <el-alert
              v-if="promotionResult"
              class="overlay-alert"
              :type="promotionResult.status === 'promoted' || promotionResult.reason === 'promoted' ? 'success' : 'info'"
              :closable="false"
              show-icon
              :title="promotionStatusMessage"
            />
          </section>
        </section>

        <div class="drawer-actions">
          <el-button @click="overlayDrawerVisible = false">关闭</el-button>
          <el-button type="primary" :loading="overlaySubmitting" @click="submitOverlayDraft">
            {{ activeGoalDraftResolutionSessionId && overlayDraftMode === 'goal_draft' ? '创建推荐草稿' : '创建手动草稿' }}
          </el-button>
        </div>
      </div>
    </el-drawer>

    <el-dialog v-model="candidateEditor.visible" :title="candidateEditor.title" width="620px">
      <div v-if="candidateEditor.errors.length" class="candidate-editor-issue-panel">
        <strong>当前问题</strong>
        <p>{{ candidateEditorIssueSummary }}</p>
        <div v-if="candidateEditorQuickFixErrors.length" class="candidate-editor-quick-actions">
          <el-button
            v-for="error in candidateEditorQuickFixErrors"
            :key="`quick-${error}`"
            size="small"
            type="warning"
            plain
            @click="applyCandidateQuickFix(error)"
          >
            {{ quickFixLabel(error) }}
          </el-button>
        </div>
      </div>
      <el-form label-position="top">
        <template v-if="candidateEditor.kind === 'node'">
          <el-form-item label="名称"><el-input v-model="candidateEditor.form.name" /></el-form-item>
          <el-form-item label="摘要">
            <el-input v-model="candidateEditor.form.summary" type="textarea" :rows="3" />
            <p v-if="candidateEditorFieldIssue('summary')" class="candidate-editor-field-hint">{{ candidateEditorFieldIssue('summary') }}</p>
          </el-form-item>
          <el-form-item label="合法性说明">
            <el-input v-model="candidateEditor.form.legality_rationale" type="textarea" :rows="2" />
            <p v-if="candidateEditorFieldIssue('legality_rationale')" class="candidate-editor-field-hint">{{ candidateEditorFieldIssue('legality_rationale') }}</p>
          </el-form-item>
          <el-form-item label="分组 / 分类">
            <el-input v-model="candidateEditor.form.group" placeholder="group" />
            <el-input v-model="candidateEditor.form.category" class="candidate-editor-inline" placeholder="category" />
          </el-form-item>
          <el-form-item label="规划评分">
            <div class="candidate-editor-grid">
              <el-input-number v-model="candidateEditor.form.difficulty_final" :min="1" :max="5" controls-position="right" />
              <el-input-number v-model="candidateEditor.form.importance_final" :min="1" :max="5" controls-position="right" />
              <el-input-number v-model="candidateEditor.form.estimated_hours" :min="0.5" :step="0.5" controls-position="right" />
            </div>
            <p v-if="candidateEditorFieldIssue('difficulty_final') || candidateEditorFieldIssue('importance_final') || candidateEditorFieldIssue('estimated_hours')" class="candidate-editor-field-hint">
              {{ candidateEditorFieldIssue('difficulty_final') || candidateEditorFieldIssue('importance_final') || candidateEditorFieldIssue('estimated_hours') }}
            </p>
          </el-form-item>
          <el-form-item label="画像需求 req_math / req_coding / req_ml">
            <div class="candidate-editor-grid">
              <el-input-number v-model="candidateEditor.form.req_math" :min="1" :max="5" controls-position="right" />
              <el-input-number v-model="candidateEditor.form.req_coding" :min="1" :max="5" controls-position="right" />
              <el-input-number v-model="candidateEditor.form.req_ml" :min="1" :max="5" controls-position="right" />
            </div>
            <p v-if="candidateEditorFieldIssue('req_math') || candidateEditorFieldIssue('req_coding') || candidateEditorFieldIssue('req_ml')" class="candidate-editor-field-hint">
              {{ candidateEditorFieldIssue('req_math') || candidateEditorFieldIssue('req_coding') || candidateEditorFieldIssue('req_ml') }}
            </p>
          </el-form-item>
          <el-form-item label="理论 / 实践权重">
            <div class="candidate-editor-grid">
              <el-input-number v-model="candidateEditor.form.theory_weight" :min="0" :max="1" :step="0.1" controls-position="right" />
              <el-input-number v-model="candidateEditor.form.practice_weight" :min="0" :max="1" :step="0.1" controls-position="right" />
            </div>
            <p v-if="candidateEditorFieldIssue('theory_weight') || candidateEditorFieldIssue('practice_weight')" class="candidate-editor-field-hint">
              {{ candidateEditorFieldIssue('theory_weight') || candidateEditorFieldIssue('practice_weight') }}
            </p>
          </el-form-item>
        </template>
        <template v-else-if="candidateEditor.kind === 'edge'">
          <el-form-item label="来源节点 ID 或名称">
            <el-select
              v-model="candidateEditor.form.source_node_id"
              filterable
              allow-create
              default-first-option
              placeholder="搜索当前图谱或本次草稿节点，也可手动输入 ID/名称"
              style="width: 100%"
            >
              <el-option
                v-for="option in overlayEndpointOptions"
                :key="`source-${option.id}`"
                :label="option.label"
                :value="option.id"
                :disabled="option.disabled"
              >
                <span>{{ option.label }}</span>
                <span class="endpoint-option-hint">{{ option.hint }}</span>
              </el-option>
            </el-select>
            <p v-if="candidateEditorFieldIssue('source_node_id')" class="candidate-editor-field-hint">{{ candidateEditorFieldIssue('source_node_id') }}</p>
          </el-form-item>
          <el-form-item label="目标节点 ID 或名称">
            <el-select
              v-model="candidateEditor.form.target_node_id"
              filterable
              allow-create
              default-first-option
              placeholder="搜索当前图谱或本次草稿节点，也可手动输入 ID/名称"
              style="width: 100%"
            >
              <el-option
                v-for="option in overlayEndpointOptions"
                :key="`target-${option.id}`"
                :label="option.label"
                :value="option.id"
                :disabled="option.disabled"
              >
                <span>{{ option.label }}</span>
                <span class="endpoint-option-hint">{{ option.hint }}</span>
              </el-option>
            </el-select>
            <p v-if="candidateEditorFieldIssue('target_node_id')" class="candidate-editor-field-hint">{{ candidateEditorFieldIssue('target_node_id') }}</p>
          </el-form-item>
          <el-form-item label="关系类型">
            <el-select v-model="candidateEditor.form.relation_type" style="width: 100%">
              <el-option label="REQUIRES" value="REQUIRES" />
              <el-option label="RELATED_TO" value="RELATED_TO" />
            </el-select>
            <p v-if="candidateEditorFieldIssue('relation_type')" class="candidate-editor-field-hint">{{ candidateEditorFieldIssue('relation_type') }}</p>
          </el-form-item>
          <el-form-item label="合法性说明">
            <el-input v-model="candidateEditor.form.legality_rationale" type="textarea" :rows="3" />
            <p v-if="candidateEditorFieldIssue('legality_rationale')" class="candidate-editor-field-hint">{{ candidateEditorFieldIssue('legality_rationale') }}</p>
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="标题">
            <el-input v-model="candidateEditor.form.title" />
            <p v-if="candidateEditorFieldIssue('title')" class="candidate-editor-field-hint">{{ candidateEditorFieldIssue('title') }}</p>
          </el-form-item>
          <el-form-item label="URL">
            <el-input v-model="candidateEditor.form.url" />
            <p v-if="candidateEditorFieldIssue('url')" class="candidate-editor-field-hint">{{ candidateEditorFieldIssue('url') }}</p>
          </el-form-item>
          <el-form-item label="资源类型">
            <el-input v-model="candidateEditor.form.resource_type" />
            <p v-if="candidateEditorFieldIssue('resource_type')" class="candidate-editor-field-hint">{{ candidateEditorFieldIssue('resource_type') }}</p>
          </el-form-item>
          <el-form-item label="摘要">
            <el-input v-model="candidateEditor.form.summary" type="textarea" :rows="3" />
            <p v-if="candidateEditorFieldIssue('summary')" class="candidate-editor-field-hint">{{ candidateEditorFieldIssue('summary') }}</p>
          </el-form-item>
          <el-form-item label="证据来源 ID">
            <el-input v-model="candidateEditor.form.evidence_source_id" />
            <p v-if="candidateEditorFieldIssue('evidence_source_id')" class="candidate-editor-field-hint">{{ candidateEditorFieldIssue('evidence_source_id') }}</p>
          </el-form-item>
          <el-form-item label="质量分">
            <el-input-number v-model="candidateEditor.form.quality_score" :min="0" :max="1" :step="0.1" controls-position="right" />
            <p v-if="candidateEditorFieldIssue('quality_score')" class="candidate-editor-field-hint">{{ candidateEditorFieldIssue('quality_score') }}</p>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="candidateEditor.visible = false">取消</el-button>
        <el-button type="primary" :loading="candidateEditor.saving" @click="saveCandidateEditor">保存并重新校验</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index'
import { useRoute, useRouter } from 'vue-router'
import DisplayModeSwitch from '@/components/DisplayModeSwitch.vue'
import { useDisplayMode } from '@/composables/useDisplayMode'
import { useProjectStore } from '@/stores/project'
import { useGraphCacheDiagnostics } from './composables/useGraphCacheDiagnostics'
import { useGraphWorkspaceLoader, type GraphWorkspaceLoadOptions } from './composables/useGraphWorkspaceLoader'
import { useGraphReviewActions } from './composables/useGraphReviewActions'
import { useOverlayCandidateEditor } from './composables/useOverlayCandidateEditor'
import { useOverlayPostActions } from './composables/useOverlayPostActions'
import {
  OVERLAY_CANDIDATE_FILTER_OPTIONS,
  useOverlayCandidateWorkflow,
  type CandidateIssueFilter,
  type OverlayRepairTarget,
  type OverlaySessionView,
} from './composables/useOverlayCandidateWorkflow'
import { useOverlayDraftInput } from './composables/useOverlayDraftInput'
import {
  buildGraphQuery,
  graphApi,
  normalizeGraphPathId,
  normalizeGraphScope,
  type GraphEdgeData,
  type GraphElement,
  type GraphEntityMetadata,
  type GraphNodeData,
  type GraphScope,
} from '@/api/modules/graph'
import { GRAPH_CATEGORY_LEGEND, GRAPH_RELATION_LEGEND } from '@/components/Graph/graphMeta'
import {
  formatServiceReason,
  promotionPreviewStatusMeta,
  resourceTypeMeta,
  sessionStatusMeta,
  validationStatusMeta,
} from '@/utils/displayLabels'

type GraphLayout = 'cose' | 'breadthfirst'

type SelectedAdjacentEdge = GraphEdgeData & {
  direction: 'incoming' | 'outgoing'
  source_label?: string
  target_label?: string
}

type SelectedNodeContext = GraphNodeData & {
  adjacent_edges: SelectedAdjacentEdge[]
  incoming_edges: SelectedAdjacentEdge[]
  outgoing_edges: SelectedAdjacentEdge[]
}

const PROJECT_LATEST_PLAN_MISSING = 'project_latest_plan_missing'
const SEARCH_NOT_READY = 'SEARCH_NOT_READY'

const GraphToolbar = defineAsyncComponent(() => import('@/components/Graph/GraphToolbar.vue'))
const GraphCanvas = defineAsyncComponent(() => import('@/components/Graph/GraphCanvas.vue'))
const NodeDetail = defineAsyncComponent(() => import('@/components/Graph/NodeDetail.vue'))
const EntityMetadataDrawer = defineAsyncComponent(() => import('@/components/Graph/EntityMetadataDrawer.vue'))

type GraphCanvasHandle = {
  zoomIn: () => void
  zoomOut: () => void
  fitView: () => void
  focusNode: (nodeId: string) => boolean
  highlightBySearch: (keyword: string) => void
  setNodeReviewStatus: (nodeId: string, status: string) => void
  setEdgeReviewStatus: (edgeId: string, status: string) => void
}

function firstQueryValue(value: unknown): unknown {
  return Array.isArray(value) ? value[0] : value
}


function normalizeRouteSessionId(value: unknown): string | null {
  const nextValue = firstQueryValue(value)
  return typeof nextValue === 'string' && nextValue.trim() ? nextValue.trim() : null
}

function normalizeRouteNodeId(value: unknown): string | null {
  const nextValue = firstQueryValue(value)
  return typeof nextValue === 'string' && nextValue.trim() ? nextValue.trim() : null
}

function normalizeGoalDraftFlag(value: unknown): boolean {
  const nextValue = firstQueryValue(value)
  return nextValue === '1' || nextValue === 'true'
}

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const { displayMode, showAuditDetails, showTechnicalDetails } = useDisplayMode()
const projectId = computed(() => projectStore.currentProject?.id)
const currentProject = computed(() => projectStore.currentProject)
const layout = ref<GraphLayout>('cose')
const scope = ref<GraphScope>(normalizeGraphScope(route.query.scope))
const syncing = ref(false)
const selectedNodeId = ref<string | null>(null)
const graphRef = ref<GraphCanvasHandle>()
const pageRef = ref<HTMLDivElement>()
const {
  graphCacheStatsLoading,
  graphCacheStatsError,
  graphCacheDiagnosticItems,
  showGraphCacheDiagnostics,
  refreshGraphCacheStats,
} = useGraphCacheDiagnostics(() => graphApi.getGraphCacheStats())
const reviewMode = ref(false)
const entityDrawerVisible = ref(false)
const entityLoading = ref(false)
const entityMetadata = ref<GraphEntityMetadata | null>(null)
const overlayDrawerVisible = ref(false)
const overlayError = ref('')
const lastOverlaySession = ref<OverlaySessionView | null>(null)
const overlayCandidateFilter = ref<CandidateIssueFilter>('all')
let graphWorkspaceLoader: ReturnType<typeof useGraphWorkspaceLoader> | null = null
const categoryLegend = GRAPH_CATEGORY_LEGEND
const relationLegend = GRAPH_RELATION_LEGEND
const requestedScope = computed<GraphScope>(() => normalizeGraphScope(route.query.scope))
const requestedPathId = computed<string | undefined>(() => normalizeGraphPathId(requestedScope.value, route.query.path_id))
const requestedNodeId = computed<string | null>(() => normalizeRouteNodeId(route.query.nodeId))
const requestedSessionId = computed<string | null>(() => normalizeRouteSessionId(route.query.sessionId))
const goalDraftResolutionSessionId = computed<string | null>(() => (
  normalizeGoalDraftFlag(route.query.goalDraft) ? normalizeRouteSessionId(route.query.resolutionSessionId) : null
))
const emptyDescription = computed(() =>
  emptyReason.value === PROJECT_LATEST_PLAN_MISSING
    ? '当前项目尚未生成学习路径，暂时无法展示路径子图；项目图谱仍可显示领域基线与项目扩展草稿。'
    : '当前范围暂无图谱数据，可刷新或先同步领域知识包到 Neo4j',
)
const projectionAlertType = computed(() => projectionStatus.value?.status === 'ok' ? 'success' : 'warning')
const projectionStatusTitle = computed(() => {
  if (!projectionStatus.value) return ''
  const status = projectionStatus.value.status === 'ok' ? '项目扩展投影已同步' : '项目扩展投影需关注'
  const reason = formatServiceReason(projectionStatus.value.reason)
  return reason ? `${status}：${reason}` : status
})
const graphQuery = computed(() => buildGraphQuery({
  scope: scope.value,
  path_id: requestedPathId.value,
  nodeId: requestedNodeId.value || undefined,
}))

function isNodeElement(element: GraphElement): element is Extract<GraphElement, { group: 'nodes' }> {
  return element.group === 'nodes'
}

function isEdgeElement(element: GraphElement): element is Extract<GraphElement, { group: 'edges' }> {
  return element.group === 'edges'
}

const {
  overlaySubmitting,
  overlayExtractionPreviewLoading,
  overlayBridgeMessage,
  overlayForm,
  overlayDraftMode,
  overlayExtractionPreview,
  overlayCandidateValidation,
  goalDraftProposalLoading,
  manualGoalDraftLoading,
  manualGoalDraftResolutionSessionId,
  goalDraftProposalDismissed,
  activeGoalDraftResolutionSessionId,
  goalExtensionDraftDetails,
  goalDraftMissingConcepts,
  goalDraftReviewNotes,
  goalDraftReviewFocus,
  manualOverlayMode,
  goalDraftInboxProposal,
  goalDraftInboxCounts,
  goalDraftInboxMissingConcepts,
  goalDraftInboxNodes,
  goalDraftInboxEdges,
  goalDraftInboxResources,
  normalizedPreviewPayload,
  selectedPreviewCounts,
  openOverlayDrawer,
  prepareGoalDraftFromCurrentProject,
  openGoalDraftEntry,
  loadGoalDraftProposal,
  dismissGoalDraftProposal,
  togglePreviewCandidate,
  isPreviewCandidateSelected,
  previewOverlayExtractionPayload,
  submitOverlayDraft,
  resetOverlayDraftInput,
  applyWorkspaceGoalDraftProposal,
  prepareWorkspaceGoalDraftLoading,
  candidateTitle,
  edgeCandidateSummary,
} = useOverlayDraftInput({
  projectId,
  currentProject,
  routeGoalDraftResolutionSessionId: goalDraftResolutionSessionId,
  overlayDrawerVisible,
  overlayError,
  lastOverlaySession,
  loadPersistedSearchResults,
  onDraftCreated: async (session) => {
    scope.value = 'project'
    await replaceGraphRoute('project', null, session.session.session_id)
    await loadGraphWorkspace()
  },
  getErrorMessage: getOverlayErrorMessage,
  notifySuccess: (message) => ElMessage.success(message),
})
const workspaceLoader = useGraphWorkspaceLoader({
  projectId,
  graphQuery,
  requestedSessionId,
  activeGoalDraftResolutionSessionId,
  overlayDrawerVisible,
  overlayError,
  lastOverlaySession,
  selectedNodeId,
  goalDraftProposalLoading,
  resetOverlayState,
  prepareWorkspaceGoalDraftLoading,
  applyWorkspaceGoalDraftProposal,
  refreshGraphCacheStats,
  focusRequestedNode,
  notifyError: (message) => ElMessage.error(message),
})
graphWorkspaceLoader = workspaceLoader
const {
  elements,
  graphState,
  loading,
  errorMessage,
  lastRefreshError,
  emptyReason,
  projectionStatus,
  overlayPreflight,
  persistedSearchResults,
} = workspaceLoader
const nodes = computed(() => elements.value.filter(isNodeElement).map((element) => element.data))
const edges = computed(() => elements.value.filter(isEdgeElement).map((element) => element.data))
const {
  overlaySessionGuide,
  overlaySessionStats,
  overlayWorkflowSteps,
  overlayWorkflowCurrentStep,
  overlayPreflightTagType,
  overlayPreflightStatusLabel,
  overlayPreflightIssues,
  overlayPreflightGuidance,
  filteredOverlayNodes,
  filteredOverlayEdges,
  filteredOverlayResources,
  overlayCandidateFilterCounts,
  filteredOverlayCandidateCount,
  overlayCandidateRepairTarget,
  overlayCandidateRepairTargetLabel,
  overlayEndpointOptions,
} = useOverlayCandidateWorkflow({
  lastOverlaySession,
  overlayPreflight,
  nodes,
  overlayCandidateFilter,
})
const {
  candidateEditor,
  candidateEditorIssueSummary,
  candidateEditorQuickFixErrors,
  candidateEditorFieldIssue,
  openNodeCandidateEditor,
  openEdgeCandidateEditor,
  openResourceCandidateEditor,
  saveCandidateEditor,
  resetCandidateEditor,
  validationErrorMessage,
  quickFixLabel,
  applyCandidateQuickFix,
} = useOverlayCandidateEditor({
  projectId,
  lastOverlaySession,
  overlayError,
  refreshAfterSave: async () => {
    await Promise.all([loadOverlayPreflight(), loadGraphWorkspace({ includeRequestedOverlaySession: true })])
  },
  getErrorMessage: getOverlayErrorMessage,
  notifySuccess: (message) => ElMessage.success(message),
})
const {
  promotionPreview,
  promotionResult,
  promotionSecret,
  promotionLoading,
  resourceBinding,
  promotionStatusMessage,
  resourceTargetOptions,
  resetOverlayPostActions,
  bindOverlayResource,
  previewPromotion,
  commitPromotion,
} = useOverlayPostActions({
  projectId,
  nodes,
  lastOverlaySession,
  overlayError,
  refreshProjectionStatus: loadProjectionStatus,
  refreshGraphWorkspace: async () => { await loadGraphWorkspace() },
  notifySuccess: (message) => ElMessage.success(message),
})
const {
  onReviewNode,
  onReviewEdge,
  onSetOverlayPlanning,
} = useGraphReviewActions({
  projectId,
  nodes,
  edges,
  elements,
  selectedNodeId,
  refreshOverlayPreflight: loadOverlayPreflight,
  setCanvasNodeReviewStatus: (nodeId, status) => graphRef.value?.setNodeReviewStatus(nodeId, status),
  setCanvasEdgeReviewStatus: (edgeId, status) => graphRef.value?.setEdgeReviewStatus(edgeId, status),
  notifySuccess: (message) => ElMessage.success(message),
  notifyError: (message) => ElMessage.error(message),
})
const graphNodeCount = computed(() => nodes.value.length)
const graphEdgeCount = computed(() => edges.value.length)
const graphScopeLabel = computed(() => {
  if (scope.value === 'domain') return '领域基线图'
  if (scope.value === 'project') return '项目增强图'
  return '学习路径子图'
})
const graphStatusHint = computed(() => {
  if (graphState.value === 'loading') return '正在读取本地图谱视图与审核状态。'
  if (graphState.value === 'empty') return emptyDescription.value
  if (graphState.value === 'error') return errorMessage.value || '图谱读取失败，请稍后重试。'
  if (scope.value === 'path') return '仅展示最新学习路径命中的知识点和依赖关系。'
  if (scope.value === 'project') return '展示领域基线叠加已审核且允许规划的项目扩展候选。'
  return '展示领域知识包的稳定基线，不依赖 Neo4j 读取链路。'
})
const nodeLabelMap = computed(() => new Map(nodes.value.map((node) => [node.id, node.label])))
const selectedNode = computed<SelectedNodeContext | null>(() => {
  const nodeId = selectedNodeId.value
  if (!nodeId) return null

  const node = nodes.value.find((item) => item.id === nodeId)
  if (!node) return null

  const adjacentEdges = edges.value
    .filter((edge) => edge.source === nodeId || edge.target === nodeId)
    .map<SelectedAdjacentEdge>((edge) => ({
      ...edge,
      direction: edge.source === nodeId ? 'outgoing' : 'incoming',
      source_label: nodeLabelMap.value.get(edge.source),
      target_label: nodeLabelMap.value.get(edge.target),
    }))

  return {
    ...node,
    adjacent_edges: adjacentEdges,
    incoming_edges: adjacentEdges.filter((edge) => edge.direction === 'incoming'),
    outgoing_edges: adjacentEdges.filter((edge) => edge.direction === 'outgoing'),
  }
})

watch(nodes, (nextNodes) => {
  if (selectedNodeId.value && !nextNodes.some((node) => node.id === selectedNodeId.value)) {
    selectedNodeId.value = null
  }
})

function resetGraphState() {
  requireGraphWorkspaceLoader().resetGraphState()
}

function resetOverlayState() {
  resetOverlayDraftInput(activeGoalDraftResolutionSessionId.value ? 'goal_draft' : 'manual')
  overlayCandidateFilter.value = 'all'
  resetCandidateEditor()
  lastOverlaySession.value = null
  resetOverlayPostActions()
}

function requireGraphWorkspaceLoader() {
  if (!graphWorkspaceLoader) {
    throw new Error('Graph workspace loader is not initialized')
  }
  return graphWorkspaceLoader
}

function abortGraphLoad() {
  requireGraphWorkspaceLoader().abortGraphLoad()
}

function graphRouteQuery(nextScope: GraphScope, nodeId?: string | null, sessionId?: string | null) {
  return {
    ...buildGraphQuery({
      scope: nextScope,
      path_id: nextScope === 'path' ? requestedPathId.value : undefined,
      nodeId: nodeId || undefined,
    }),
    ...(sessionId ? { sessionId } : {}),
  }
}

async function replaceGraphRoute(nextScope: GraphScope, nodeId?: string | null, sessionId: string | null = requestedSessionId.value) {
  await router.replace({
    name: 'Knowledge',
    query: Object.fromEntries(
      Object.entries(graphRouteQuery(nextScope, nodeId, sessionId)).filter((entry): entry is [string, string] => typeof entry[1] === 'string'),
    ),
  })
}

async function loadPersistedSearchResults() {
  await requireGraphWorkspaceLoader().loadPersistedSearchResults()
}

async function loadProjectionStatus() {
  await requireGraphWorkspaceLoader().loadProjectionStatus()
}

async function loadOverlayPreflight() {
  await requireGraphWorkspaceLoader().loadOverlayPreflight()
}

async function loadRequestedOverlaySession() {
  await requireGraphWorkspaceLoader().loadRequestedOverlaySession()
}

async function focusRequestedNode() {
  const nodeId = requestedNodeId.value
  if (!nodeId || graphState.value !== 'ready') {
    return
  }

  await nextTick()
  const focused = graphRef.value?.focusNode(nodeId)
  if (focused) {
    selectedNodeId.value = nodeId
  }
}

async function loadGraphWorkspace(options: GraphWorkspaceLoadOptions = {}) {
  await requireGraphWorkspaceLoader().loadGraphWorkspace(options)
}

watch(
  projectId,
  async (nextProjectId, previousProjectId) => {
    if (!nextProjectId) {
      abortGraphLoad()
      manualGoalDraftResolutionSessionId.value = null
      resetGraphState()
      resetOverlayState()
      return
    }

    if (nextProjectId !== previousProjectId) {
      manualGoalDraftResolutionSessionId.value = null
      resetGraphState()
      resetOverlayState()
    }

    scope.value = requestedScope.value
    await loadGraphWorkspace({
      includePersistedSearchResults: true,
      includeRequestedOverlaySession: true,
      includeGoalDraftEntry: true,
    })
  },
  { immediate: true },
)

watch([requestedScope, requestedPathId], async ([nextScope, nextPathId], [previousScope, previousPathId]) => {
  if (!projectId.value || (scope.value === nextScope && nextScope === previousScope && nextPathId === previousPathId)) {
    return
  }

  scope.value = nextScope
  selectedNodeId.value = null
  resetOverlayState()
  await loadGraphWorkspace()
})

watch([requestedPathId, requestedNodeId, graphState], async () => {
  await focusRequestedNode()
})

async function syncRequestedOverlaySession(nextSessionId: string | null) {
  if (!nextSessionId) {
    resetOverlayState()
    return
  }
  await loadRequestedOverlaySession()
}

watch(requestedSessionId, syncRequestedOverlaySession)
watch(activeGoalDraftResolutionSessionId, async (nextSessionId) => {
  if (!nextSessionId) return
  resetOverlayState()
  await openGoalDraftEntry()
})

function onLayoutChange(newLayout: string) {
  layout.value = newLayout as GraphLayout
}

function onNodeClick(data: GraphNodeData) {
  selectedNodeId.value = data.id
  void replaceGraphRoute(scope.value, data.id)
}

function onSearch(keyword: string) {
  graphRef.value?.highlightBySearch(keyword)
}

async function onScopeChange(nextScope: GraphScope) {
  if (scope.value === nextScope) return
  scope.value = nextScope
  selectedNodeId.value = null
  resetOverlayState()
  await replaceGraphRoute(nextScope)
  await loadGraphWorkspace()
}

async function onRefresh() {
  await loadGraphWorkspace()
}

async function onSync() {
  if (!projectId.value) return

  const hasExistingGraph = elements.value.length > 0

  syncing.value = true
  errorMessage.value = ''

  try {
    await graphApi.syncGraph(projectId.value)
    ElMessage.success('知识图谱同步成功')
    await loadGraphWorkspace()
  } catch (e: any) {
    const message = e?.response?.data?.error || e?.message || '知识图谱同步失败，请稍后重试'
    errorMessage.value = message

    if (hasExistingGraph) {
      lastRefreshError.value = message
      ElMessage.error(message)
      return
    }

    lastRefreshError.value = ''

    if (graphState.value !== 'empty') {
      emptyReason.value = undefined
      graphState.value = 'error'
    }

    ElMessage.error(message)
  } finally {
    syncing.value = false
  }
}

function openOverlayRepairTarget(target: OverlayRepairTarget) {
  if (target.kind === 'node') {
    openNodeCandidateEditor(target.candidate)
  } else if (target.kind === 'edge') {
    openEdgeCandidateEditor(target.candidate)
  } else {
    openResourceCandidateEditor(target.candidate)
  }
}

function openFirstRepairableCandidate() {
  const target = overlayCandidateRepairTarget.value
  if (target) openOverlayRepairTarget(target)
}

function getOverlayErrorMessage(error: any) {
  const code = error?.response?.data?.error
  if (code === SEARCH_NOT_READY) {
    return '搜索服务尚未就绪，自定义扩展暂不可用；领域基线图谱浏览不受影响。'
  }
  return formatServiceReason(code) || code || error?.message || '扩展草稿创建失败'
}

async function onShowEntities() {
  if (!projectId.value) return

  entityDrawerVisible.value = true
  entityLoading.value = true

  try {
    entityMetadata.value = await graphApi.getGraphEntities(projectId.value)
  } catch {
    entityDrawerVisible.value = false
  } finally {
    entityLoading.value = false
  }
}

function toggleFullscreen() {
  if (!pageRef.value) return
  if (document.fullscreenElement) {
    document.exitFullscreen()
  } else {
    pageRef.value.requestFullscreen()
  }
}
</script>

<style scoped>
.page-container {
  padding: 20px;
  height: calc(100vh - 100px);
}

.graph-card {
  height: 100%;
}

.graph-wrapper {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

.graph-legend-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px;
  border-bottom: 1px solid #ebeef5;
  background: #fff;
}

.legend-section {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.legend-title {
  font-size: 12px;
  font-weight: 600;
  color: #606266;
}

.legend-items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.legend-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid #ebeef5;
  border-radius: 999px;
  background: #fafafa;
  font-size: 12px;
  color: #606266;
}

.legend-chip-edge {
  max-width: 100%;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex: 0 0 auto;
}

.legend-line {
  position: relative;
  display: inline-block;
  width: 28px;
  height: 0;
  border-top: 2px solid #909399;
  flex: 0 0 auto;
}

.legend-line-dashed {
  border-top-style: dashed;
}

.legend-line-solid {
  border-top-style: solid;
}

.legend-line-arrow::after {
  content: '';
  position: absolute;
  top: -5px;
  right: -2px;
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
  border-left: 7px solid #909399;
}

.graph-status-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 12px 12px 0;
  padding: 12px;
  border: 1px solid #e1f3d8;
  border-radius: 12px;
  background: linear-gradient(135deg, #f0f9eb 0%, #f5f7fa 100%);
}

.graph-status-panel strong {
  display: block;
  margin-bottom: 4px;
  color: #303133;
  font-size: 14px;
}

.graph-status-panel p {
  margin: 0;
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
}

.graph-status-meta,
.graph-status-tags,
.graph-cache-diagnostics {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.graph-status-meta {
  flex-direction: column;
  align-items: flex-end;
}

.graph-cache-diagnostics {
  align-items: center;
  color: #909399;
  font-size: 12px;
}

.graph-cache-title {
  font-weight: 600;
}

.graph-alert {
  margin: 12px 12px 0;
}

.overlay-preflight-panel {
  padding: 12px;
  border: 1px solid #dcdfe6;
  border-radius: 10px;
  background: #fff;
}

.overlay-preflight-header,
.overlay-preflight-tags,
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
  margin: 8px 0;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
}

.overlay-preflight-issues {
  margin-top: 8px;
  color: #e6a23c;
  font-size: 12px;
}

.overlay-drawer {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.overlay-alert {
  margin-bottom: 4px;
}

.goal-draft-entry {
  padding: 12px;
  border: 1px solid #f3d19e;
  border-radius: 10px;
  background: #fdf6ec;
}

.goal-draft-entry p {
  margin: 0;
  color: #606266;
  font-size: 13px;
  line-height: 1.7;
}

.draft-mode-switch,
.draft-inbox-actions {
  margin-top: 10px;
}

.draft-inbox-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.draft-inbox-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 10px;
}

.candidate-card-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}

.candidate-card-list.compact {
  gap: 8px;
}

.preview-candidate-card {
  padding: 10px;
  border: 1px solid #d9ecff;
  border-radius: 8px;
  background: #fff;
}

.preview-candidate-card p {
  margin: 6px 0;
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
}

.candidate-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.overlay-guidance {
  margin: 4px 0 0;
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
}

.overlay-workflow {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid #d9ecff;
  border-radius: 10px;
  background: #f4faff;
}

.overlay-workflow-header,
.overlay-workflow-step-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.overlay-workflow-header span {
  color: #409eff;
  font-size: 12px;
}

.overlay-workflow-steps {
  display: grid;
  gap: 8px;
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
}

.overlay-workflow-step {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 8px;
  padding: 10px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  background: #fff;
}

.overlay-workflow-step.is-current {
  border-color: #f3d19e;
  background: #fdf6ec;
}

.overlay-workflow-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  color: #fff;
  font-size: 12px;
  background: #909399;
}

.overlay-workflow-step.is-done .overlay-workflow-index {
  background: #67c23a;
}

.overlay-workflow-step.is-current .overlay-workflow-index {
  background: #e6a23c;
}

.overlay-candidate-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
  padding: 12px;
  border: 1px solid #f3d19e;
  border-radius: 10px;
  background: #fdf6ec;
}

.overlay-candidate-toolbar-title p,
.overlay-workflow-step p,
.overlay-empty-filter,
.candidate-editor-issue-panel p,
.candidate-editor-field-hint {
  margin: 4px 0 0;
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
}

.overlay-empty-filter {
  padding: 10px 12px;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
  background: #fff;
}

.candidate-editor-issue-panel {
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid #f3d19e;
  border-radius: 10px;
  background: #fdf6ec;
}

.candidate-editor-quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.candidate-editor-field-hint {
  color: #b88230;
}

.endpoint-option-hint {
  float: right;
  margin-left: 12px;
  color: #909399;
  font-size: 12px;
}

.candidate-editor-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  width: 100%;
}

.candidate-editor-inline {
  margin-top: 8px;
}

.candidate-checkbox-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.validation-errors {
  margin: 8px 0 0;
  padding-left: 18px;
  color: #b88230;
  font-size: 12px;
  line-height: 1.6;
}

.preview-hint {
  margin-left: 10px;
  color: #909399;
  font-size: 12px;
}

.overlay-preview {
  padding: 12px;
  border: 1px solid #d9ecff;
  border-radius: 10px;
  background: #f4faff;
}

.overlay-preview h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: #303133;
}

.overlay-result {
  padding: 14px;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  background: #fafafa;
}

.overlay-result h3 {
  margin: 0;
  font-size: 16px;
  color: #303133;
}

.overlay-result p {
  margin: 4px 0 0;
  font-size: 12px;
  color: #909399;
  word-break: break-all;
}
.overlay-subsection {
  margin-top: 14px;
}
.overlay-subsection h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: #303133;
}
.goal-draft-summary {
  padding: 12px;
  border: 1px solid #f3d19e;
  border-radius: 10px;
  background: #fdf6ec;
}
.review-notes {
  margin: 10px 0 0;
  padding-left: 18px;
  color: #606266;
  font-size: 12px;
  line-height: 1.7;
}
.review-focus-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.resource-candidate {
  padding: 10px;
  margin-bottom: 8px;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  background: #fff;
}
.resource-title {
  font-weight: 600;
  color: #303133;
}
.option-trace-id {
  float: right;
  margin-left: 12px;
  color: #c0c4cc;
  font-size: 12px;
}
.promotion-summary,
.promotion-secret {
  margin-top: 10px;
}

.drawer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 8px;
}

.graph-state-wrap,
.empty-project-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 360px;
}

.graph-loading-state {
  padding: 24px;
}

.graph-skeleton-panel {
  width: min(520px, 80%);
  padding: 24px;
  border: 1px solid #ebeef5;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(31 45 61 / 8%);
}

.graph-skeleton-header {
  width: 42%;
  height: 14px;
  margin: 0 auto 24px;
  border-radius: 999px;
  background: linear-gradient(90deg, #ebeef5 25%, #f5f7fa 50%, #ebeef5 75%);
}

.graph-skeleton-body {
  position: relative;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  padding: 12px 32px;
}

.graph-skeleton-node {
  width: 42px;
  height: 42px;
  margin: 0 auto;
  border-radius: 50%;
  background: linear-gradient(135deg, #d9ecff, #ecf5ff);
}

.graph-skeleton-panel p {
  margin: 22px 0 0;
  color: #909399;
  font-size: 13px;
  text-align: center;
}

@media (max-width: 768px) {
  .page-container {
    padding: 12px;
    height: auto;
  }

  .graph-legend-wrap,
  .graph-status-panel {
    flex-direction: column;
    align-items: flex-start;
  }

  .graph-status-tags {
    justify-content: flex-start;
  }
}
</style>
