export const GRAPH_CATEGORY_LEGEND = [
  { key: 'foundation', label: '编程基础', color: '#E6A23C' },
  { key: 'math_foundation', label: '数学基础', color: '#409EFF' },
  { key: 'ml_core', label: '机器学习核心', color: '#F56C6C' },
  { key: 'algorithm', label: '核心算法', color: '#8B5CF6' },
  { key: 'evaluation', label: '评估与泛化', color: '#909399' },
  { key: 'practice', label: '实践应用', color: '#67C23A' },
] as const

export const CATEGORY_COLORS: Record<string, string> = Object.fromEntries(
  GRAPH_CATEGORY_LEGEND.map(({ key, color }) => [key, color]),
)

export const CATEGORY_LABELS: Record<string, string> = Object.fromEntries(
  GRAPH_CATEGORY_LEGEND.map(({ key, label }) => [key, label]),
)

export const GRAPH_RELATION_LEGEND = [
  {
    type: 'REQUIRES',
    label: '前置依赖',
    description: '必须先学，箭头指向后续知识点',
    lineStyle: 'solid',
    hasArrow: true,
  },
  {
    type: 'RELATED_TO',
    label: '相关关联',
    description: '推荐结合了解，虚线表示弱依赖',
    lineStyle: 'dashed',
    hasArrow: false,
  },
] as const
