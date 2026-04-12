<template>
  <el-form :model="form" :rules="rules" ref="formRef" label-position="top">
    <el-form-item label="项目标题" prop="title">
      <el-input v-model="form.title" placeholder="例如：机器学习基础学习计划" />
    </el-form-item>
    <el-form-item label="学习目标" prop="goal_text">
      <el-input v-model="form.goal_text" type="textarea" :rows="3" placeholder="描述你想学什么，例如：我想系统学习机器学习基础" />
    </el-form-item>
    <el-form-item label="目标类型" prop="goal_type">
      <el-radio-group v-model="form.goal_type">
        <el-radio-button value="domain">领域型</el-radio-button>
        <el-radio-button value="concept">概念型</el-radio-button>
        <el-radio-button value="problem">问题型</el-radio-button>
      </el-radio-group>
      <div class="type-desc">
        <el-text v-if="form.goal_type === 'domain'" type="info">系统学习整个领域的知识体系</el-text>
        <el-text v-else-if="form.goal_type === 'concept'" type="info">深入理解某个具体概念</el-text>
        <el-text v-else-if="form.goal_type === 'problem'" type="info">解决某个特定的学习问题</el-text>
      </div>
    </el-form-item>
    <el-form-item>
      <el-button type="primary" @click="handleSubmit" :loading="loading">创建项目</el-button>
    </el-form-item>
  </el-form>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useProjectStore } from '@/stores/project'
import type { CreateProjectDto, Project } from '@/api/modules/project'

const emit = defineEmits<{ created: [project: Project] }>()
const projectStore = useProjectStore()
const formRef = ref<FormInstance>()
const loading = ref(false)

const form = reactive<CreateProjectDto>({
  title: '',
  goal_text: '',
  goal_type: 'domain',
  domain: 'machine_learning',
})

const rules: FormRules = {
  title: [{ required: true, message: '请输入项目标题', trigger: 'blur' }],
  goal_text: [{ required: true, message: '请描述学习目标', trigger: 'blur' }],
  goal_type: [{ required: true, message: '请选择目标类型', trigger: 'change' }],
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    const project = await projectStore.create(form)
    emit('created', project)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.type-desc { margin-top: 8px; }
</style>
