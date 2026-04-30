<template>
  <div class="questionnaire">
    <div v-if="loadingQuestions" class="loading-wrapper">
      <el-skeleton :rows="5" animated />
    </div>
    <template v-else-if="questions.length > 0">
      <section class="questionnaire-header">
        <div>
          <p class="questionnaire-eyebrow">第二步：画像采集</p>
          <h2>让路径更贴合你的基础、偏好和时间</h2>
          <p>这些回答会分别影响前置补强、理论/案例排序、路径完整度、资源推荐形态、练习密度和时间预算提示，不会改变知识图谱中的硬依赖。</p>
        </div>
        <el-tag :type="source === 'static' ? 'info' : 'success'">
          {{ source === 'static' ? '标准画像问卷' : '智能个性化问卷' }}
        </el-tag>
      </section>

      <div class="progress-card">
        <div>
          <strong>已回答 {{ answeredCount }} / {{ questions.length }}</strong>
          <p>{{ allAnswered ? '画像信息已完整，可以提交。' : `还差 ${remainingCount} 题，完成后才能提交画像。` }}</p>
        </div>
        <el-progress :percentage="progressPercent" :stroke-width="8" />
      </div>

      <div class="question-card-list">
        <article v-for="(q, index) in questions" :key="q.id" class="question-card">
          <div class="question-card-header">
            <span class="question-index">{{ index + 1 }}</span>
            <div>
              <h3>{{ q.question }}</h3>
              <p>{{ impactHint(q.field) }}</p>
            </div>
          </div>

          <div class="option-card-grid">
            <button
              v-for="opt in q.options"
              :key="String(opt.value)"
              type="button"
              class="option-card"
              :class="{ selected: answers[q.id] === opt.value }"
              @click="selectAnswer(q.id, opt.value)"
            >
              {{ opt.label }}
            </button>
          </div>
        </article>
      </div>

      <section class="submit-card">
        <div>
          <strong>提交后将生成画像参数</strong>
          <p>系统会把问卷答案映射为基础水平、排序偏好、路径完整度、资源形态、练习密度和时间预算等规划输入。</p>
        </div>
        <el-button
          type="primary"
          size="large"
          @click="handleSubmit"
          :loading="submitting"
          :disabled="!allAnswered"
        >
          {{ allAnswered ? '提交画像' : `还差 ${remainingCount} 题` }}
        </el-button>
      </section>
    </template>
    <el-empty v-else description="暂无问卷数据">
      <template #default>
        <p class="empty-hint">画像问卷暂时不可用，请稍后重试或检查后端画像采集服务。</p>
      </template>
    </el-empty>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { profileApi } from '@/api/modules/profile'

type AnswerValue = number | string
interface QuestionOption { label: string; value: AnswerValue }
interface Question { id: string; field: string; question: string; options: QuestionOption[] }

const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ completed: [] }>()

const questions = ref<Question[]>([])
const source = ref('')
const answers = reactive<Record<string, AnswerValue>>({})
const loadingQuestions = ref(false)
const submitting = ref(false)

const answeredCount = computed(() => questions.value.filter(q => answers[q.id] !== undefined).length)
const remainingCount = computed(() => Math.max(questions.value.length - answeredCount.value, 0))
const progressPercent = computed(() => questions.value.length ? Math.round((answeredCount.value / questions.value.length) * 100) : 0)
const allAnswered = computed(() => {
  return questions.value.length > 0 && questions.value.every(q => answers[q.id] !== undefined)
})

onMounted(async () => {
  loadingQuestions.value = true
  try {
    const data = await profileApi.getQuestions(props.projectId)
    questions.value = data.questions ?? []
    source.value = data.source ?? 'static'
  } catch {
    questions.value = []
  } finally {
    loadingQuestions.value = false
  }
})

function selectAnswer(questionId: string, value: AnswerValue) {
  answers[questionId] = value
}

function impactHint(field: string) {
  const hints: Record<string, string> = {
    math_level: '影响是否补充线性代数、概率统计等数学前置内容。',
    coding_level: '影响是否需要补充 Python、代码阅读等编程前置内容，不直接代表练习密度。',
    ml_level: '影响机器学习基础概念的补强深度和起点。',
    theory_weight: '只影响知识点排序更偏理论理解还是案例上手，不代表练习数量。',
    practice_weight: '与理论权重互补，用于排序侧重，不等同于练习密度。',
    weekly_hours: '影响学习路径的时间预算和每周推进节奏。',
    deadline_weeks: '影响系统对压缩路径和预算风险的提示。',
    path_mode_preference: '影响首次生成时默认采用标准或压缩路径，表达路径完整度。',
    learning_goal_orientation: '帮助解释系统为什么偏向基础、项目、考试或职业目标。',
    resource_preference: '影响资源搜索提示、推荐结果标记和轻量排序加权。',
    practice_intensity: '表达练习密度，用于学习引导和资源行动建议，不会硬塞无关知识点。',
  }
  return hints[field] || '用于生成学习者画像，让路径排序和解释更贴近你的情况。'
}

async function handleSubmit() {
  if (!allAnswered.value || submitting.value) {
    return
  }
  submitting.value = true
  try {
    const answerList = questions.value.map(q => ({
      question_id: q.id,
      field: q.field,
      value: answers[q.id],
    }))
    await profileApi.submitAnswers(props.projectId, { source: source.value, answers: answerList })
    emit('completed')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.questionnaire {
  padding: 4px 0;
}

.loading-wrapper {
  padding: 20px 0;
}

.questionnaire-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 18px;
  border-radius: 14px;
  background: var(--el-fill-color-light);
}

.questionnaire-eyebrow {
  margin: 0 0 6px;
  color: var(--el-color-primary);
  font-size: 13px;
  font-weight: 700;
}

.questionnaire-header h2 {
  margin: 0;
  font-size: 22px;
}

.questionnaire-header p,
.progress-card p,
.submit-card p,
.empty-hint {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.progress-card,
.submit-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 220px;
  gap: 16px;
  align-items: center;
  margin-top: 16px;
  padding: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  background: var(--el-fill-color-blank);
}

.question-card-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 16px;
}

.question-card {
  padding: 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 14px;
  background: var(--el-fill-color-blank);
}

.question-card-header {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.question-index {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  flex-shrink: 0;
}

.question-card h3 {
  margin: 0;
  font-size: 16px;
  line-height: 1.5;
}

.question-card p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.option-card-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.option-card {
  min-height: 46px;
  padding: 10px 12px;
  border: 1px solid var(--el-border-color);
  border-radius: 10px;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-primary);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.option-card:hover,
.option-card:focus-visible,
.option-card.selected {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px var(--el-color-primary-light-8);
  outline: none;
}

.option-card.selected {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 700;
}

.submit-card {
  grid-template-columns: minmax(0, 1fr) auto;
}

.submit-card :deep(.el-button) {
  min-height: 44px;
}

@media (max-width: 768px) {
  .questionnaire-header,
  .progress-card,
  .submit-card {
    grid-template-columns: 1fr;
    flex-direction: column;
  }

  .option-card-grid {
    grid-template-columns: 1fr;
  }
}
</style>
