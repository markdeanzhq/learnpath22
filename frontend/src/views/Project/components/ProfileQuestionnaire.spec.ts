import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProfileQuestionnaire from './ProfileQuestionnaire.vue'

const { getQuestionsMock, submitAnswersMock } = vi.hoisted(() => ({
  getQuestionsMock: vi.fn(),
  submitAnswersMock: vi.fn(),
}))

vi.mock('@/api/modules/profile', () => ({
  profileApi: {
    getQuestions: getQuestionsMock,
    submitAnswers: submitAnswersMock,
  },
}))

const buttonStub = defineComponent({
  props: {
    disabled: { type: Boolean, default: false },
    loading: { type: Boolean, default: false },
  },
  emits: ['click'],
  template: '<button :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
})

const progressStub = defineComponent({
  props: {
    percentage: { type: Number, default: 0 },
  },
  template: '<div data-testid="progress">{{ percentage }}%</div>',
})

const emptyStub = defineComponent({
  props: {
    description: { type: String, default: '' },
  },
  template: '<div>{{ description }}<slot /></div>',
})

const slotStub = (tag: string) => defineComponent({
  template: `<${tag}><slot /></${tag}>`,
})

function mountQuestionnaire() {
  return mount(ProfileQuestionnaire, {
    props: {
      projectId: 'project-001',
    },
    global: {
      stubs: {
        ElSkeleton: slotStub('div'),
        ElTag: slotStub('span'),
        ElProgress: progressStub,
        ElButton: buttonStub,
        ElEmpty: emptyStub,
      },
    },
  })
}

function mockQuestions() {
  getQuestionsMock.mockResolvedValue({
    source: 'static',
    questions: [
      {
        id: 'math',
        field: 'math_level',
        question: '你的数学基础如何？',
        options: [
          { label: '刚入门', value: 1 },
          { label: '比较熟悉', value: 4 },
        ],
      },
      {
        id: 'coding',
        field: 'coding_level',
        question: '你的编程基础如何？',
        options: [
          { label: '很少写代码', value: 1 },
          { label: '能完成小项目', value: 4 },
        ],
      },
      {
        id: 'weekly',
        field: 'weekly_hours',
        question: '每周可投入多少小时？',
        options: [
          { label: '5 小时', value: 5 },
          { label: '10 小时', value: 10 },
        ],
      },
    ],
  })
}

function findButtonByText(wrapper: ReturnType<typeof mountQuestionnaire>, text: string) {
  const matched = wrapper.findAll('button').find((button) => button.text().includes(text))
  if (!matched) {
    throw new Error(`Button not found: ${text}`)
  }
  return matched
}

describe('ProfileQuestionnaire', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockQuestions()
    submitAnswersMock.mockResolvedValue({ id: 'profile-001' })
  })

  it('renders card questionnaire with progress and impact hints', async () => {
    const wrapper = mountQuestionnaire()
    await flushPromises()

    expect(getQuestionsMock).toHaveBeenCalledWith('project-001')
    expect(wrapper.text()).toContain('第二步：画像采集')
    expect(wrapper.text()).toContain('已回答 0 / 3')
    expect(wrapper.text()).toContain('还差 3 题')
    expect(wrapper.text()).toContain('影响是否补充线性代数、概率统计等数学前置内容。')
    expect(wrapper.text()).toContain('影响是否需要补充 Python、代码阅读等编程前置内容，不直接代表练习密度。')
    expect(wrapper.get('[data-testid="progress"]').text()).toContain('0%')
  })

  it('renders distinct semantics for path mode, resources, and practice density', async () => {
    getQuestionsMock.mockResolvedValueOnce({
      source: 'static',
      questions: [
        {
          id: 'theory',
          field: 'theory_weight',
          question: '你希望知识点排序更偏向理论理解还是案例上手？',
          options: [{ label: '理论优先', value: 0.8 }],
        },
        {
          id: 'path-mode',
          field: 'path_mode_preference',
          question: '你希望学习路径的完整度如何？',
          options: [{ label: '标准路径', value: 'standard' }],
        },
        {
          id: 'resource',
          field: 'resource_preference',
          question: '你偏好的学习资料形态是什么？',
          options: [{ label: '代码示例', value: 'code' }],
        },
        {
          id: 'practice',
          field: 'practice_intensity',
          question: '你希望每个阶段的练习密度多高？',
          options: [{ label: '高强度实践', value: 5 }],
        },
      ],
    })

    const wrapper = mountQuestionnaire()
    await flushPromises()

    expect(wrapper.text()).toContain('理论/案例排序、路径完整度、资源推荐形态、练习密度')
    expect(wrapper.text()).toContain('只影响知识点排序更偏理论理解还是案例上手，不代表练习数量。')
    expect(wrapper.text()).toContain('影响首次生成时默认采用标准或压缩路径，表达路径完整度。')
    expect(wrapper.text()).toContain('影响资源搜索提示、推荐结果标记和轻量排序加权。')
    expect(wrapper.text()).toContain('表达练习密度，用于学习引导和资源行动建议，不会硬塞无关知识点。')
    expect(wrapper.text()).not.toContain('理论优先或实践优先')
  })

  it('selects option cards, updates progress, and submits answers', async () => {
    const wrapper = mountQuestionnaire()
    await flushPromises()

    await findButtonByText(wrapper, '比较熟悉').trigger('click')
    await findButtonByText(wrapper, '能完成小项目').trigger('click')
    await findButtonByText(wrapper, '10 小时').trigger('click')

    expect(wrapper.text()).toContain('已回答 3 / 3')
    expect(wrapper.text()).toContain('画像信息已完整，可以提交。')
    expect(wrapper.get('[data-testid="progress"]').text()).toContain('100%')

    await findButtonByText(wrapper, '提交画像').trigger('click')
    await flushPromises()

    expect(submitAnswersMock).toHaveBeenCalledWith('project-001', {
      source: 'static',
      answers: [
        { question_id: 'math', field: 'math_level', value: 4 },
        { question_id: 'coding', field: 'coding_level', value: 4 },
        { question_id: 'weekly', field: 'weekly_hours', value: 10 },
      ],
    })
    expect(wrapper.emitted('completed')).toBeTruthy()
  })

  it('shows empty guidance when questions cannot be loaded', async () => {
    getQuestionsMock.mockRejectedValueOnce(new Error('failed'))

    const wrapper = mountQuestionnaire()
    await flushPromises()

    expect(wrapper.text()).toContain('暂无问卷数据')
    expect(wrapper.text()).toContain('画像问卷暂时不可用')
  })
})
