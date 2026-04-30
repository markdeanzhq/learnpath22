<template>
  <el-dialog v-model="dialogVisible" :title="candidateEditor.title" width="620px">
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
          @click="emit('quick-fix', error)"
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
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :loading="candidateEditor.saving" @click="emit('save')">保存并重新校验</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { CandidateEditorState } from './composables/useOverlayCandidateEditor'

type OverlayEndpointOption = {
  id: string
  label: string
  hint: string
  disabled?: boolean
}

const props = defineProps<{
  visible: boolean
  candidateEditor: CandidateEditorState
  candidateEditorIssueSummary: string
  candidateEditorQuickFixErrors: string[]
  overlayEndpointOptions: OverlayEndpointOption[]
  candidateEditorFieldIssue: (field: string) => string
  quickFixLabel: (error: string) => string
}>()

const emit = defineEmits<{
  'update:visible': [visible: boolean]
  'quick-fix': [error: string]
  save: []
}>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (visible) => emit('update:visible', visible),
})
</script>

<style scoped>
.candidate-editor-issue-panel {
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid #f3d19e;
  border-radius: 10px;
  background: #fdf6ec;
}

.candidate-editor-issue-panel p,
.candidate-editor-field-hint {
  margin: 4px 0 0;
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
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
</style>
