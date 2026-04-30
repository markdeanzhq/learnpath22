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
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { useRoute, useRouter } from 'vue-router'
import DisplayModeSwitch from '@/components/DisplayModeSwitch.vue'
import { useDisplayMode } from '@/composables/useDisplayMode'
import { useProjectStore } from '@/stores/project'
import { useGraphCacheDiagnostics } from './composables/useGraphCacheDiagnostics'
import { useOverlayCandidateEditor } from './composables/useOverlayCandidateEditor'
import {
  OVERLAY_CANDIDATE_FILTER_OPTIONS,
  useOverlayCandidateWorkflow,
  type CandidateIssueFilter,
  type OverlayRepairTarget,
  type OverlaySessionView,
} from './composables/useOverlayCandidateWorkflow'
import {
  buildGraphQuery,
  graphApi,
  normalizeGraphPathId,
  normalizeGraphScope,
  type GraphData,
  type GraphEdgeData,
  type GraphElement,
  type GraphEntityMetadata,
  type GraphNodeData,
  type GraphScope,
  type GraphWorkspaceData,
  type GoalExtensionDraftProposal,
  type GoalExtensionDraftProposalResponse,
  type GoalExtensionDraftResponse,
  type OverlayProjectionStatusResponse,
  type OverlayPreflightResponse,
  type OverlayElementGroup,
  type OverlayExtractionPayloadPreviewResponse,
  type OverlayExtractionPayloadValidationResponse,
  type OverlayReviewStatus,
  type OverlaySourceRequest,
  type ReviewStatus,
} from '@/api/modules/graph'
import { GRAPH_CATEGORY_LEGEND, GRAPH_RELATION_LEGEND } from '@/components/Graph/graphMeta'
import { searchApi, type PersistedSearchResult } from '@/api/modules/search'
import { projectApi, type GoalResolutionPreviewResponse, type ReviewExtensionDraftCoverageResponse } from '@/api/modules/project'
import { resourceApi } from '@/api/modules/resource'
import { isCanceledRequest } from '@/api/request'
import {
  formatServiceReason,
  promotionPreviewStatusMeta,
  resourceTypeMeta,
  sessionStatusMeta,
  validationStatusMeta,
} from '@/utils/displayLabels'

type GraphState = 'loading' | 'ready' | 'empty' | 'error'
type GraphLayout = 'cose' | 'breadthfirst'
type OverlaySourceType = 'pasted_text' | 'search_url' | 'saved_search'
type OverlayExtractionMode = 'default' | 'custom_extension'
type OverlayDraftMode = 'goal_draft' | 'manual'
type OverlayPreviewGroup = 'nodes' | 'edges' | 'resources'

type PreviewPayload = {
  nodes: Array<Record<string, any>>
  edges: Array<Record<string, any>>
  resources: Array<Record<string, any>>
  warnings: string[]
}

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

function createOverlayForm() {
  return {
    sourceType: 'pasted_text' as OverlaySourceType,
    selectedResultIds: [] as string[],
    rawText: '',
    url: '',
    title: '',
    snippet: '',
    summary: '',
    mode: 'default' as OverlayExtractionMode,
  }
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

function isReviewExtensionDraftResponse(response: GoalResolutionPreviewResponse): response is ReviewExtensionDraftCoverageResponse {
  return response.result_type === 'review_extension_draft' && response.coverage_status === 'in_domain_uncovered'
}

function normalizePreviewGoalType(value: unknown): 'domain' | 'concept' | 'problem' | undefined {
  return value === 'domain' || value === 'concept' || value === 'problem' ? value : undefined
}

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const { displayMode, showAuditDetails, showTechnicalDetails } = useDisplayMode()
const projectId = computed(() => projectStore.currentProject?.id)
const elements = ref<GraphElement[]>([])
const layout = ref<GraphLayout>('cose')
const scope = ref<GraphScope>(normalizeGraphScope(route.query.scope))
const graphState = ref<GraphState>('loading')
const loading = ref(false)
const syncing = ref(false)
const errorMessage = ref('')
const lastRefreshError = ref('')
const emptyReason = ref<string | undefined>()
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
const projectionStatus = ref<OverlayProjectionStatusResponse | null>(null)
const overlayPreflight = ref<OverlayPreflightResponse | null>(null)
const overlayDrawerVisible = ref(false)
const overlaySubmitting = ref(false)
const overlayExtractionPreviewLoading = ref(false)
const overlayError = ref('')
const overlayBridgeMessage = ref('')
const overlayForm = ref(createOverlayForm())
const overlayDraftMode = ref<OverlayDraftMode>('manual')
const overlayExtractionPreview = ref<OverlayExtractionPayloadPreviewResponse | null>(null)
const selectedPreviewCandidates = ref<Record<OverlayPreviewGroup, number[]>>({ nodes: [], edges: [], resources: [] })
const goalDraftProposal = ref<GoalExtensionDraftProposalResponse | null>(null)
const goalDraftProposalLoading = ref(false)
const manualGoalDraftLoading = ref(false)
const manualGoalDraftResolutionSessionId = ref<string | null>(null)
const goalDraftProposalDismissed = ref(false)
const persistedSearchResults = ref<PersistedSearchResult[]>([])
const lastOverlaySession = ref<OverlaySessionView | null>(null)
const overlayCandidateValidation = ref<OverlayExtractionPayloadValidationResponse | null>(null)
const overlayCandidateFilter = ref<CandidateIssueFilter>('all')
const promotionPreview = ref<any | null>(null)
const promotionResult = ref<any | null>(null)
const promotionSecret = ref('')
const promotionLoading = ref(false)
const resourceBinding = ref({ resourceId: '', targetType: 'project_node', targetId: '' })
let graphLoadRequestId = 0
let graphLoadController: AbortController | null = null
const categoryLegend = GRAPH_CATEGORY_LEGEND
const relationLegend = GRAPH_RELATION_LEGEND
const requestedScope = computed<GraphScope>(() => normalizeGraphScope(route.query.scope))
const requestedPathId = computed<string | undefined>(() => normalizeGraphPathId(requestedScope.value, route.query.path_id))
const requestedNodeId = computed<string | null>(() => normalizeRouteNodeId(route.query.nodeId))
const requestedSessionId = computed<string | null>(() => normalizeRouteSessionId(route.query.sessionId))
const goalDraftResolutionSessionId = computed<string | null>(() => (
  normalizeGoalDraftFlag(route.query.goalDraft) ? normalizeRouteSessionId(route.query.resolutionSessionId) : null
))
const activeGoalDraftResolutionSessionId = computed(() => goalDraftResolutionSessionId.value || manualGoalDraftResolutionSessionId.value)
const emptyDescription = computed(() =>
  emptyReason.value === PROJECT_LATEST_PLAN_MISSING
    ? '当前项目尚未生成学习路径，暂时无法展示路径子图；项目图谱仍可显示领域基线与项目扩展草稿。'
    : '当前范围暂无图谱数据，可刷新或先同步领域知识包到 Neo4j',
)
const promotionStatusMessage = computed(() => {
  if (!promotionResult.value) return ''
  if (promotionResult.value.reason === 'promoted') return '推广成功，候选已归档隐藏。'
  return formatServiceReason(promotionResult.value.reason) || promotionPreviewStatusMeta(promotionResult.value.status).label || '推广状态已更新'
})
const projectionAlertType = computed(() => projectionStatus.value?.status === 'ok' ? 'success' : 'warning')
const projectionStatusTitle = computed(() => {
  if (!projectionStatus.value) return ''
  const status = projectionStatus.value.status === 'ok' ? '项目扩展投影已同步' : '项目扩展投影需关注'
  const reason = formatServiceReason(projectionStatus.value.reason)
  return reason ? `${status}：${reason}` : status
})
const resourceTargetOptions = computed(() => nodes.value.map((node) => ({
  id: node.id,
  label: node.label || node.id,
})))
const goalExtensionDraftDetails = computed(() => {
  const session = lastOverlaySession.value
  if (!session?.gap_analysis && !session?.review_notes?.length && !session?.draft_metadata) {
    return null
  }
  return session
})
const goalDraftMissingConcepts = computed(() => (
  goalExtensionDraftDetails.value?.gap_analysis?.missing_concepts
  || goalExtensionDraftDetails.value?.missing_concepts
  || []
))
const goalDraftReviewNotes = computed(() => goalExtensionDraftDetails.value?.review_notes || [])
const goalDraftReviewFocus = computed(() => goalExtensionDraftDetails.value?.gap_analysis?.recommended_review_focus || [])
const manualOverlayMode = computed(() => !activeGoalDraftResolutionSessionId.value || overlayDraftMode.value === 'manual')
const goalDraftInboxProposal = computed<GoalExtensionDraftProposal | null>(() => goalDraftProposal.value?.draft_proposal || null)
const goalDraftInboxCounts = computed(() => goalDraftInboxProposal.value?.counts || { nodes: 0, edges: 0, resources: 0 })
const goalDraftInboxMissingConcepts = computed(() => goalDraftInboxProposal.value?.missing_concepts || goalDraftMissingConcepts.value)
const goalDraftInboxNodes = computed(() => goalDraftInboxProposal.value?.nodes || [])
const goalDraftInboxEdges = computed(() => goalDraftInboxProposal.value?.edges || [])
const goalDraftInboxResources = computed(() => goalDraftInboxProposal.value?.resources || [])
const normalizedPreviewPayload = computed(() => normalizePreviewPayload(overlayExtractionPreview.value?.extraction_payload))
const selectedPreviewCounts = computed(() => ({
  nodes: selectedPreviewCandidates.value.nodes.length,
  edges: selectedPreviewCandidates.value.edges.length,
  resources: selectedPreviewCandidates.value.resources.length,
}))
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

function normalizePreviewPayload(payload: unknown): PreviewPayload {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return { nodes: [], edges: [], resources: [], warnings: [] }
  }
  const record = payload as Record<string, unknown>
  return {
    nodes: Array.isArray(record.nodes) ? record.nodes.filter((item): item is Record<string, any> => Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : [],
    edges: Array.isArray(record.edges) ? record.edges.filter((item): item is Record<string, any> => Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : [],
    resources: Array.isArray(record.resources) ? record.resources.filter((item): item is Record<string, any> => Boolean(item) && typeof item === 'object' && !Array.isArray(item)) : [],
    warnings: Array.isArray(record.warnings) ? record.warnings.filter((item): item is string => typeof item === 'string') : [],
  }
}

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

watch(overlayForm, () => {
  overlayExtractionPreview.value = null
  overlayCandidateValidation.value = null
  selectedPreviewCandidates.value = { nodes: [], edges: [], resources: [] }
}, { deep: true })

watch(overlayDraftMode, (nextMode) => {
  overlayError.value = ''
  overlayExtractionPreview.value = null
  overlayCandidateValidation.value = null
  selectedPreviewCandidates.value = { nodes: [], edges: [], resources: [] }
  if (nextMode === 'goal_draft') {
    goalDraftProposalDismissed.value = false
  }
})

function resetGraphState() {
  elements.value = []
  selectedNodeId.value = null
  errorMessage.value = ''
  lastRefreshError.value = ''
  emptyReason.value = undefined
  graphState.value = 'loading'
  projectionStatus.value = null
  overlayPreflight.value = null
}

function resetOverlayState() {
  overlayDrawerVisible.value = false
  overlaySubmitting.value = false
  overlayExtractionPreviewLoading.value = false
  overlayError.value = ''
  overlayBridgeMessage.value = ''
  overlayForm.value = createOverlayForm()
  overlayDraftMode.value = activeGoalDraftResolutionSessionId.value ? 'goal_draft' : 'manual'
  overlayExtractionPreview.value = null
  overlayCandidateValidation.value = null
  selectedPreviewCandidates.value = { nodes: [], edges: [], resources: [] }
  overlayCandidateFilter.value = 'all'
  resetCandidateEditor()
  goalDraftProposal.value = null
  goalDraftProposalLoading.value = false
  goalDraftProposalDismissed.value = false
  lastOverlaySession.value = null
  promotionPreview.value = null
  promotionResult.value = null
  promotionSecret.value = ''
  resourceBinding.value = { resourceId: '', targetType: 'project_node', targetId: '' }
}

function createGraphLoadController() {
  graphLoadController?.abort()
  graphLoadController = new AbortController()
  return graphLoadController
}

function clearGraphLoadController(controller: AbortController) {
  if (graphLoadController === controller) {
    graphLoadController = null
  }
}

function abortGraphLoad() {
  graphLoadController?.abort()
  graphLoadController = null
}

function workspaceErrorMessage(detail?: { message?: string } | null, fallback?: string | null) {
  return detail?.message || fallback || ''
}

function performanceNow() {
  return typeof performance !== 'undefined' ? performance.now() : Date.now()
}

function logKnowledgePerformance(event: string, payload: Record<string, unknown>) {
  if (!import.meta.env.DEV || typeof console === 'undefined') {
    return
  }
  console.debug('[Knowledge performance]', { event, ...payload })
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
  const currentProjectId = projectId.value
  if (!currentProjectId) {
    persistedSearchResults.value = []
    return
  }
  const results = await searchApi.listPersistedResults(currentProjectId)
  if (projectId.value === currentProjectId) {
    persistedSearchResults.value = results
  }
}

async function loadProjectionStatus() {
  const currentProjectId = projectId.value
  if (!currentProjectId) {
    projectionStatus.value = null
    return
  }
  try {
    const status = await graphApi.getOverlayProjectionStatus(currentProjectId)
    if (projectId.value === currentProjectId) {
      projectionStatus.value = status
    }
  } catch {
    if (projectId.value === currentProjectId) {
      projectionStatus.value = {
        project_id: currentProjectId,
        status: 'error',
        ready: false,
        in_sync: false,
        reason: 'projection_status_unavailable',
      }
    }
  }
}

async function loadOverlayPreflight() {
  const currentProjectId = projectId.value
  if (!currentProjectId) {
    overlayPreflight.value = null
    return
  }
  try {
    const preflight = await graphApi.getOverlayPreflight(currentProjectId)
    if (projectId.value === currentProjectId) {
      overlayPreflight.value = preflight
    }
  } catch {
    if (projectId.value === currentProjectId) {
      overlayPreflight.value = null
    }
  }
}

function applyGraphData(data: GraphData) {
  const nextElements = data.elements ?? []

  elements.value = nextElements
  errorMessage.value = ''
  lastRefreshError.value = ''
  emptyReason.value = data.empty_reason
  graphState.value = nextElements.length > 0 ? 'ready' : 'empty'
}

async function loadRequestedOverlaySession() {
  const currentProjectId = projectId.value
  const currentSessionId = requestedSessionId.value
  if (!currentProjectId || !currentSessionId) {
    return
  }

  try {
    const session = await graphApi.getOverlayExtractionSession(
      currentProjectId,
      currentSessionId,
    )
    if (projectId.value !== currentProjectId || requestedSessionId.value !== currentSessionId) {
      return
    }
    lastOverlaySession.value = session
    overlayDrawerVisible.value = true
  } catch (error: any) {
    if (projectId.value !== currentProjectId || requestedSessionId.value !== currentSessionId) {
      return
    }
    resetOverlayState()
    overlayError.value = error?.response?.data?.error || '扩展抽取会话加载失败'
  }
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

type CompanionLoadOptions = {
  includePersistedSearchResults?: boolean
  includeRequestedOverlaySession?: boolean
  includeGoalDraftEntry?: boolean
}

type GoalDraftEntryOptions = {
  refreshPersistedSearchResults?: boolean
}

async function loadGraphWorkspace(options: CompanionLoadOptions = {}) {
  const currentProjectId = projectId.value
  const currentGraphQuery = graphQuery.value
  const currentSessionId = options.includeRequestedOverlaySession ? requestedSessionId.value : null
  const currentGoalDraftResolutionSessionId = options.includeGoalDraftEntry ? activeGoalDraftResolutionSessionId.value : null
  const requestId = ++graphLoadRequestId

  if (!currentProjectId) {
    abortGraphLoad()
    resetGraphState()
    loading.value = false
    return
  }

  const controller = createGraphLoadController()
  const loadStartedAt = performanceNow()
  const hasExistingGraph = elements.value.length > 0
  if (!hasExistingGraph) {
    graphState.value = 'loading'
  }

  if (currentGoalDraftResolutionSessionId) {
    overlayDrawerVisible.value = true
    overlayDraftMode.value = 'goal_draft'
    overlayError.value = ''
    overlayBridgeMessage.value = ''
    overlayForm.value = createOverlayForm()
    goalDraftProposalLoading.value = true
  }

  loading.value = true
  errorMessage.value = ''

  try {
    const workspace: GraphWorkspaceData = await graphApi.getGraphWorkspace(currentProjectId, {
      ...currentGraphQuery,
      include_persisted_search_results: options.includePersistedSearchResults,
      session_id: currentSessionId,
      goal_draft_resolution_session_id: currentGoalDraftResolutionSessionId,
    }, {
      signal: controller.signal,
      silent: true,
    })
    const requestDurationMs = Math.round(performanceNow() - loadStartedAt)
    if (requestId !== graphLoadRequestId || projectId.value !== currentProjectId) {
      logKnowledgePerformance('workspace_stale_response', {
        project_id: currentProjectId,
        scope: currentGraphQuery.scope,
        path_id: currentGraphQuery.path_id,
        duration_ms: requestDurationMs,
      })
      return
    }

    applyGraphData(workspace.graph)
    projectionStatus.value = workspace.projection_status
    overlayPreflight.value = workspace.overlay_preflight ?? null

    if (options.includePersistedSearchResults) {
      persistedSearchResults.value = workspace.persisted_search_results ?? []
    }

    if (currentSessionId) {
      const overlaySessionError = workspaceErrorMessage(
        workspace.overlay_session_error_detail,
        workspace.overlay_session_error,
      )
      if (overlaySessionError) {
        resetOverlayState()
        overlayError.value = overlaySessionError
      } else if (workspace.overlay_session) {
        lastOverlaySession.value = workspace.overlay_session
        overlayDrawerVisible.value = true
      }
    }

    if (currentGoalDraftResolutionSessionId) {
      goalDraftProposal.value = workspace.goal_draft_proposal ?? null
      const goalDraftError = workspaceErrorMessage(
        workspace.goal_draft_error_detail,
        workspace.goal_draft_error,
      )
      if (goalDraftError) {
        overlayError.value = goalDraftError
      }
    }

    logKnowledgePerformance('workspace_loaded', {
      project_id: currentProjectId,
      scope: workspace.graph.scope,
      path_id: workspace.graph.path_id ?? currentGraphQuery.path_id ?? null,
      duration_ms: requestDurationMs,
      elements: workspace.graph.elements?.length ?? 0,
      optional_errors: [
        workspace.overlay_preflight_error_detail?.code,
        workspace.persisted_search_results_error_detail?.code,
        workspace.overlay_session_error_detail?.code,
        workspace.goal_draft_error_detail?.code,
      ].filter(Boolean),
    })
    void refreshGraphCacheStats()
  } catch (e: any) {
    const durationMs = Math.round(performanceNow() - loadStartedAt)
    if (isCanceledRequest(e)) {
      logKnowledgePerformance('workspace_canceled', {
        project_id: currentProjectId,
        scope: currentGraphQuery.scope,
        path_id: currentGraphQuery.path_id,
        duration_ms: durationMs,
      })
      return
    }
    if (requestId !== graphLoadRequestId || projectId.value !== currentProjectId) {
      return
    }
    const message = e?.response?.data?.error || e?.message || '知识图谱加载失败，请稍后重试'

    logKnowledgePerformance('workspace_failed', {
      project_id: currentProjectId,
      scope: currentGraphQuery.scope,
      path_id: currentGraphQuery.path_id,
      duration_ms: durationMs,
      message,
    })
    errorMessage.value = message
    if (hasExistingGraph) {
      lastRefreshError.value = message
      graphState.value = 'ready'
      ElMessage.error(message)
    } else {
      selectedNodeId.value = null
      lastRefreshError.value = ''
      emptyReason.value = undefined
      graphState.value = 'error'
    }
  } finally {
    clearGraphLoadController(controller)
    if (requestId === graphLoadRequestId && projectId.value === currentProjectId) {
      loading.value = false
      if (currentGoalDraftResolutionSessionId) {
        goalDraftProposalLoading.value = false
      }
    }
  }

  await focusRequestedNode()
}

function getElementGroup(data: GraphNodeData | GraphEdgeData): OverlayElementGroup {
  return 'source' in data && 'target' in data ? 'edges' : 'nodes'
}

function normalizeOverlayReviewStatus(status: string): OverlayReviewStatus {
  return status === 'rejected' ? 'rejected' : status as OverlayReviewStatus
}

function isMessageBoxCancel(error: unknown): boolean {
  if (typeof error === 'string') {
    return error === 'cancel' || error === 'close'
  }
  if (error && typeof error === 'object' && 'action' in error) {
    const action = (error as { action?: unknown }).action
    return action === 'cancel' || action === 'close'
  }
  return false
}

function overlayElementLabel(group: OverlayElementGroup): string {
  return group === 'nodes' ? '节点' : '关系'
}

async function confirmOverlayReview(group: OverlayElementGroup, status: OverlayReviewStatus): Promise<boolean> {
  if (status !== 'confirmed') {
    return true
  }

  try {
    await ElMessageBox.confirm(
      `确认该扩展${overlayElementLabel(group)}有效后，它会进入“已确认候选”；是否参与增强图谱规划仍由规划开关控制。`,
      '确认扩展候选有效',
      {
        type: 'warning',
        confirmButtonText: '确认有效',
        cancelButtonText: '取消',
      },
    )
    return true
  } catch (error) {
    if (isMessageBoxCancel(error)) {
      return false
    }
    throw error
  }
}

async function confirmOverlayPlanning(data: GraphNodeData | GraphEdgeData, enabled: boolean): Promise<boolean> {
  if (!enabled) {
    return true
  }

  const label = data.label ? `「${data.label}」` : '该扩展候选'
  try {
    await ElMessageBox.confirm(
      `${label}开启规划后会进入增强图谱预检和路径对比，但不会直接保存为正式学习路径。`,
      '纳入增强图谱规划',
      {
        type: 'warning',
        confirmButtonText: '纳入规划',
        cancelButtonText: '取消',
      },
    )
    return true
  } catch (error) {
    if (isMessageBoxCancel(error)) {
      return false
    }
    throw error
  }
}

function patchElementLifecycle(
  elementId: string,
  lifecycle: {
    review_status?: string
    planning_enabled?: boolean
    validation_status?: string
    promotion_status?: string
  },
) {
  elements.value = elements.value.map((element) => {
    if (element.data.id !== elementId) {
      return element
    }

    return {
      ...element,
      data: {
        ...element.data,
        ...lifecycle,
      },
    } as GraphElement
  })
}

function updateNodeReviewStatus(nodeId: string, status: ReviewStatus) {
  elements.value = elements.value.map((element) => {
    if (!isNodeElement(element) || element.data.id !== nodeId) {
      return element
    }

    return {
      ...element,
      data: {
        ...element.data,
        review_status: status,
      },
    }
  })
}

function updateEdgeReviewStatus(edgeId: string, status: ReviewStatus) {
  elements.value = elements.value.map((element) => {
    if (!isEdgeElement(element) || element.data.id !== edgeId) {
      return element
    }

    return {
      ...element,
      data: {
        ...element.data,
        review_status: status,
      },
    }
  })
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

async function onReviewNode(nodeId: string, status: string) {
  if (!projectId.value) return
  const node = nodes.value.find((item) => item.id === nodeId)
  try {
    if (node?.origin === 'overlay') {
      const nextStatus = normalizeOverlayReviewStatus(status)
      if (!(await confirmOverlayReview('nodes', nextStatus))) {
        return
      }
      const result = await graphApi.reviewOverlayElement(
        projectId.value,
        'nodes',
        nodeId,
        nextStatus,
      )
      selectedNodeId.value = nodeId
      patchElementLifecycle(nodeId, result)
      graphRef.value?.setNodeReviewStatus(nodeId, result.review_status)
      await loadOverlayPreflight()
    } else {
      const nextStatus = status as ReviewStatus
      await graphApi.reviewNode(projectId.value, nodeId, nextStatus)
      selectedNodeId.value = nodeId
      updateNodeReviewStatus(nodeId, nextStatus)
      graphRef.value?.setNodeReviewStatus(nodeId, nextStatus)
    }
    ElMessage.success('节点审核状态已更新')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '节点审核失败')
  }
}

async function onReviewEdge(edgeId: string, status: string) {
  if (!projectId.value) return
  const edge = edges.value.find((item) => item.id === edgeId)
  try {
    if (edge?.origin === 'overlay') {
      const nextStatus = normalizeOverlayReviewStatus(status)
      if (!(await confirmOverlayReview('edges', nextStatus))) {
        return
      }
      const result = await graphApi.reviewOverlayElement(
        projectId.value,
        'edges',
        edgeId,
        nextStatus,
      )
      patchElementLifecycle(edgeId, result)
      graphRef.value?.setEdgeReviewStatus(edgeId, result.review_status)
      await loadOverlayPreflight()
    } else {
      const nextStatus = status as ReviewStatus
      await graphApi.reviewEdge(projectId.value, edgeId, nextStatus)
      updateEdgeReviewStatus(edgeId, nextStatus)
      graphRef.value?.setEdgeReviewStatus(edgeId, nextStatus)
    }
    ElMessage.success('边审核状态已更新')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '边审核失败')
  }
}

async function onSetOverlayPlanning(data: GraphNodeData | GraphEdgeData, enabled: boolean) {
  if (!projectId.value || data.origin !== 'overlay') return
  try {
    if (!(await confirmOverlayPlanning(data, enabled))) {
      return
    }
    const result = await graphApi.setOverlayPlanning(
      projectId.value,
      getElementGroup(data),
      data.id,
      enabled,
    )
    patchElementLifecycle(data.id, result)
    await loadOverlayPreflight()
    ElMessage.success(enabled ? '已允许参与规划' : '已从规划中排除')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.error || '规划开关更新失败')
  }
}

async function openOverlayDrawer() {
  overlayDrawerVisible.value = true
  overlayDraftMode.value = activeGoalDraftResolutionSessionId.value ? overlayDraftMode.value : 'manual'
  overlayError.value = ''
  overlayBridgeMessage.value = ''
  await loadPersistedSearchResults()
}

async function prepareGoalDraftFromCurrentProject() {
  if (!projectId.value || !projectStore.currentProject?.goal_text) return
  manualGoalDraftLoading.value = true
  overlayError.value = ''
  goalDraftProposalDismissed.value = false
  try {
    const preview = await projectApi.previewForProject(projectId.value, {
      goal_text: projectStore.currentProject.goal_text,
      requested_goal_type: normalizePreviewGoalType(projectStore.currentProject.goal_type),
      domain: projectStore.currentProject.domain,
    })
    if (!isReviewExtensionDraftResponse(preview) || !preview.session_id || !preview.draft_proposal) {
      overlayDraftMode.value = 'manual'
      overlayError.value = '当前目标已被现有图谱覆盖，暂不需要生成自动扩展草稿。'
      return
    }
    manualGoalDraftResolutionSessionId.value = preview.session_id
    goalDraftProposal.value = {
      resolution_session_id: preview.session_id,
      project_id: projectId.value,
      session_status: 'draft_previewed',
      expires_at: preview.expires_at || undefined,
      draft_proposal: preview.draft_proposal,
    }
    overlayDraftMode.value = 'goal_draft'
    overlayDrawerVisible.value = true
  } catch (error: any) {
    overlayError.value = getOverlayErrorMessage(error)
  } finally {
    manualGoalDraftLoading.value = false
  }
}

async function openGoalDraftEntry({ refreshPersistedSearchResults = true }: GoalDraftEntryOptions = {}) {
  if (!activeGoalDraftResolutionSessionId.value) return
  overlayDrawerVisible.value = true
  overlayDraftMode.value = 'goal_draft'
  overlayError.value = ''
  overlayBridgeMessage.value = ''
  overlayForm.value = createOverlayForm()
  if (refreshPersistedSearchResults) {
    await loadPersistedSearchResults()
  }
  await loadGoalDraftProposal()
}

async function loadGoalDraftProposal() {
  const currentProjectId = projectId.value
  const currentResolutionSessionId = activeGoalDraftResolutionSessionId.value
  if (!currentProjectId || !currentResolutionSessionId) return
  goalDraftProposalLoading.value = true
  try {
    const proposal = await graphApi.getGoalExtensionDraftProposal(
      currentProjectId,
      currentResolutionSessionId,
    )
    if (projectId.value === currentProjectId && activeGoalDraftResolutionSessionId.value === currentResolutionSessionId) {
      goalDraftProposal.value = proposal
    }
  } catch (error: any) {
    if (projectId.value === currentProjectId && activeGoalDraftResolutionSessionId.value === currentResolutionSessionId) {
      overlayError.value = getOverlayErrorMessage(error)
    }
  } finally {
    if (projectId.value === currentProjectId && activeGoalDraftResolutionSessionId.value === currentResolutionSessionId) {
      goalDraftProposalLoading.value = false
    }
  }
}

function dismissGoalDraftProposal() {
  goalDraftProposalDismissed.value = true
  overlayDraftMode.value = 'manual'
}

function selectAllPreviewCandidates(payload: PreviewPayload) {
  selectedPreviewCandidates.value = {
    nodes: payload.nodes.map((_, index) => index),
    edges: payload.edges.map((_, index) => index),
    resources: payload.resources.map((_, index) => index),
  }
}

function togglePreviewCandidate(group: OverlayPreviewGroup, index: number, checked: boolean) {
  const current = new Set(selectedPreviewCandidates.value[group])
  if (checked) {
    current.add(index)
  } else {
    current.delete(index)
  }
  selectedPreviewCandidates.value = {
    ...selectedPreviewCandidates.value,
    [group]: [...current].sort((a, b) => a - b),
  }
}

function isPreviewCandidateSelected(group: OverlayPreviewGroup, index: number) {
  return selectedPreviewCandidates.value[group].includes(index)
}

function filteredPreviewPayload(preview: OverlayExtractionPayloadPreviewResponse) {
  const payload = normalizePreviewPayload(preview.extraction_payload)
  return {
    nodes: payload.nodes.filter((_, index) => selectedPreviewCandidates.value.nodes.includes(index)),
    edges: payload.edges.filter((_, index) => selectedPreviewCandidates.value.edges.includes(index)),
    resources: payload.resources.filter((_, index) => selectedPreviewCandidates.value.resources.includes(index)),
    warnings: payload.warnings,
  }
}

function candidateTitle(candidate: Record<string, any>, fallback: string) {
  return candidate.name || candidate.title || candidate.relation_type || fallback
}

function edgeCandidateSummary(candidate: Record<string, any>) {
  const source = candidate.source_name_or_id || candidate.source_node_id || '未知来源'
  const target = candidate.target_name_or_id || candidate.target_node_id || '未知目标'
  return `${source} → ${target}`
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

function buildOverlaySourcePayload(): OverlaySourceRequest | null {
  const form = overlayForm.value
  if (form.sourceType === 'pasted_text') {
    const rawText = form.rawText.trim()
    if (!rawText) {
      overlayError.value = '请先粘贴资料文本'
      return null
    }
    return {
      source_type: 'pasted_text',
      raw_text: rawText,
      raw_text_excerpt: rawText.slice(0, 12000),
      summary: form.summary.trim() || null,
    }
  }

  if (form.sourceType === 'search_url') {
    const url = form.url.trim()
    if (!url) {
      overlayError.value = '请填写搜索结果 URL'
      return null
    }

    return {
      source_type: 'search_url',
      url,
      title: form.title.trim() || url,
      snippet: form.snippet.trim() || null,
      summary: form.summary.trim() || null,
      provider: 'manual',
    }
  }

  return null
}

async function resolveOverlaySourceIds() {
  const form = overlayForm.value
  if (form.sourceType === 'saved_search') {
    if (!projectId.value || !form.selectedResultIds.length) {
      overlayError.value = '请选择已保存搜索结果'
      return null
    }
    const bridged = await searchApi.bridgeOverlaySources(projectId.value, form.selectedResultIds)
    overlayBridgeMessage.value = `已解析 ${bridged.source_ids.length} 个项目扩展来源，${bridged.results.filter((item) => item.reused).length} 个复用。`
    return bridged.source_ids
  }

  const sourcePayload = buildOverlaySourcePayload()
  if (!sourcePayload || !projectId.value) return null
  const source = await graphApi.createOverlaySource(projectId.value, sourcePayload)
  return [source.source_id]
}

function getOverlayErrorMessage(error: any) {
  const code = error?.response?.data?.error
  if (code === SEARCH_NOT_READY) {
    return '搜索服务尚未就绪，自定义扩展暂不可用；领域基线图谱浏览不受影响。'
  }
  return formatServiceReason(code) || code || error?.message || '扩展草稿创建失败'
}

async function previewOverlayExtractionPayload() {
  if (!projectId.value || !manualOverlayMode.value) return null

  overlayExtractionPreviewLoading.value = true
  overlayError.value = ''
  overlayBridgeMessage.value = ''

  try {
    const sourceIds = await resolveOverlaySourceIds()
    if (!sourceIds) return null
    const preview = await graphApi.previewOverlayExtractionPayload(projectId.value, {
      source_ids: sourceIds,
      mode: overlayForm.value.mode,
    })
    overlayExtractionPreview.value = preview
    selectAllPreviewCandidates(normalizePreviewPayload(preview.extraction_payload))
    ElMessage.success('AI 抽取预览已生成，创建草稿时仍会经过校验。')
    return preview
  } catch (error: any) {
    overlayError.value = getOverlayErrorMessage(error)
    return null
  } finally {
    overlayExtractionPreviewLoading.value = false
  }
}

async function validateSelectedOverlayPayload(preview: OverlayExtractionPayloadPreviewResponse) {
  if (!projectId.value) return null
  const extractionPayload = filteredPreviewPayload(preview)
  const validation = await graphApi.validateOverlayExtractionPayload(projectId.value, {
    source_ids: preview.source_ids,
    mode: overlayForm.value.mode,
    extraction_payload: extractionPayload,
  })
  overlayCandidateValidation.value = validation
  if (validation.summary.has_blocking_errors) {
    await ElMessageBox.confirm(
      `预校验发现 ${validation.summary.invalid_count} 个校验失败候选。仍可创建草稿并在下方“编辑修复”，是否继续？`,
      '候选需要修复',
      {
        type: 'warning',
        confirmButtonText: '继续创建草稿',
        cancelButtonText: '返回调整',
      },
    )
  }
  return extractionPayload
}

async function bindOverlayResource() {
  if (!projectId.value || !resourceBinding.value.resourceId || !resourceBinding.value.targetId.trim()) {
    overlayError.value = '请选择资源和绑定目标'
    return
  }
  try {
    await resourceApi.bindProjectResource(projectId.value, {
      resource_id: resourceBinding.value.resourceId,
      target_type: resourceBinding.value.targetType as 'project_node' | 'path_stage',
      target_id: resourceBinding.value.targetId.trim(),
      binding_source: 'overlay',
    })
    if (lastOverlaySession.value) {
      lastOverlaySession.value = await graphApi.getOverlayExtractionSession(projectId.value, lastOverlaySession.value.session.session_id)
    }
    await loadProjectionStatus()
    ElMessage.success('资源绑定已保存')
  } catch (error: any) {
    overlayError.value = error?.response?.data?.error || '资源绑定失败'
  }
}

async function previewPromotion() {
  if (!projectId.value) return
  promotionLoading.value = true
  promotionResult.value = null
  try {
    promotionPreview.value = await graphApi.previewOverlayPromotion(projectId.value)
  } catch (error: any) {
    overlayError.value = formatServiceReason(error?.response?.data?.error) || '推广预览失败'
  } finally {
    promotionLoading.value = false
  }
}

async function commitPromotion() {
  const currentProjectId = projectId.value
  if (!currentProjectId) return
  if (!promotionSecret.value.trim()) {
    overlayError.value = '请输入 admin secret'
    return
  }
  promotionLoading.value = true
  try {
    promotionResult.value = await graphApi.commitOverlayPromotion(currentProjectId, {
      admin_secret: promotionSecret.value,
      requested_by: 'frontend',
    })
    promotionSecret.value = ''
    const sessionId = lastOverlaySession.value?.session.session_id
    await Promise.all([
      loadGraphWorkspace(),
      sessionId
        ? graphApi.getOverlayExtractionSession(currentProjectId, sessionId).then((session) => {
          if (projectId.value === currentProjectId) {
            lastOverlaySession.value = session
          }
        })
        : Promise.resolve(),
    ])
  } catch (error: any) {
    const code = error?.response?.data?.error
    overlayError.value = formatServiceReason(code) || '确认推广失败'
    promotionResult.value = error?.response?.data?.details?.preview || error?.response?.data?.details || null
  } finally {
    promotionLoading.value = false
  }
}

async function submitOverlayDraft() {
  if (!projectId.value) return

  overlaySubmitting.value = true
  overlayError.value = ''
  overlayBridgeMessage.value = ''

  try {
    if (activeGoalDraftResolutionSessionId.value && overlayDraftMode.value === 'goal_draft') {
      lastOverlaySession.value = await graphApi.createGoalExtensionDraft(
        projectId.value,
        activeGoalDraftResolutionSessionId.value,
      ) as GoalExtensionDraftResponse
    } else {
      const preview = overlayExtractionPreview.value || await previewOverlayExtractionPayload()
      if (!preview) return
      const extractionPayload = await validateSelectedOverlayPayload(preview)
      if (!extractionPayload) return
      lastOverlaySession.value = await graphApi.createOverlayExtractionSession(projectId.value, {
        source_ids: preview.source_ids,
        mode: overlayForm.value.mode,
        extraction_payload: extractionPayload,
        session_provenance: {
          ...preview.provenance,
          selected_counts: selectedPreviewCounts.value,
          filtered_by_user: true,
          pre_validation_summary: overlayCandidateValidation.value?.summary,
        },
      })
    }
    overlayForm.value = createOverlayForm()
    overlayExtractionPreview.value = null
    overlayCandidateValidation.value = null
    selectedPreviewCandidates.value = { nodes: [], edges: [], resources: [] }
    goalDraftProposalDismissed.value = Boolean(activeGoalDraftResolutionSessionId.value)
    ElMessage.success('扩展草稿已创建，请在项目图谱中审核候选节点和关系')
    scope.value = 'project'
    await replaceGraphRoute('project', null, lastOverlaySession.value.session.session_id)
    await loadGraphWorkspace()
  } catch (error: any) {
    if (isMessageBoxCancel(error)) return
    overlayError.value = getOverlayErrorMessage(error)
  } finally {
    overlaySubmitting.value = false
  }
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
