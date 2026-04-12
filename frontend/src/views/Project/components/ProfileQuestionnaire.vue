<template>
  <div class="questionnaire">
    <div v-if="loadingQuestions" class="loading-wrapper">
      <el-skeleton :rows="5" animated />
    </div>
    <template v-else-if="questions.length > 0">
      <el-alert
        v-if="source === 'static'"
        title="标准画像问卷"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 20px"
      />
      <el-alert
        v-else
        title="智能个性化问卷"
        type="success"
        :closable="false"
        show-icon
        style="margin-bottom: 20px"
      />

      <el-form label-position="top">
        <el-form-item v-for="q in questions" :key="q.id" :label="q.question">
          <el-radio-group v-model="answers[q.id]">
            <el-radio v-for="opt in q.options" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>

      <el-button
        type="primary"
        @click="handleSubmit"
        :loading="submitting"
        :disabled="!allAnswered"
      >
        提交画像
      </el-button>
    </template>
    <el-empty v-else description="暂无问卷数据" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { profileApi } from '@/api/modules/profile'

interface QuestionOption { label: string; value: number }
interface Question { id: string; field: string; question: string; options: QuestionOption[] }

const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ completed: [] }>()

const questions = ref<Question[]>([])
const source = ref('')
const answers = reactive<Record<string, number>>({})
const loadingQuestions = ref(false)
const submitting = ref(false)

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

async function handleSubmit() {
  submitting.value = true
  try {
    const answerList = questions.value.map(q => ({
      question_id: q.id,
      field: q.field,
      value: answers[q.id],
    }))
    await profileApi.submitAnswers(props.projectId, { answers: answerList })
    emit('completed')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.questionnaire { padding: 10px 0; }
.loading-wrapper { padding: 20px 0; }
</style>
