import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/project',
      component: () => import('@/components/Layout/AppLayout.vue'),
      children: [
        { path: 'project', name: 'Project', component: () => import('@/views/Project/index.vue'), meta: { title: '学习项目', icon: 'Document' } },
        { path: 'knowledge', name: 'Knowledge', component: () => import('@/views/Knowledge/index.vue'), meta: { title: '知识图谱', icon: 'Connection' } },
        { path: 'path', name: 'Path', component: () => import('@/views/Path/index.vue'), meta: { title: '学习路径', icon: 'Guide' } },
        { path: 'search', name: 'Search', component: () => import('@/views/Search/index.vue'), meta: { title: '项目资料库', icon: 'Search' } },
        { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard/index.vue'), meta: { title: '学习进度', icon: 'DataAnalysis' } },
        { path: 'settings', name: 'Settings', component: () => import('@/views/Settings/index.vue'), meta: { title: '设置', icon: 'Setting' } },
      ],
    },
  ],
})

export default router
