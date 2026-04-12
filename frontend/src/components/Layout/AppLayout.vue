<template>
  <el-container class="app-layout">
    <el-aside :width="'220px'">
      <div class="logo">
        <h2>LearnPath-KG</h2>
      </div>
      <el-menu :default-active="currentRoute" router>
        <el-menu-item index="/project">
          <el-icon><Document /></el-icon>
          <span>学习项目</span>
        </el-menu-item>
        <el-menu-item index="/knowledge">
          <el-icon><Connection /></el-icon>
          <span>知识图谱</span>
        </el-menu-item>
        <el-menu-item index="/path">
          <el-icon><Guide /></el-icon>
          <span>学习路径</span>
        </el-menu-item>
        <el-menu-item index="/search">
          <el-icon><Search /></el-icon>
          <span>资料搜索</span>
        </el-menu-item>
        <el-menu-item index="/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <span>学习进度</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header>
        <span class="header-title">{{ pageTitle }}</span>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Document, Connection, Guide, Search, DataAnalysis, Setting } from '@element-plus/icons-vue'

const route = useRoute()
const currentRoute = computed(() => route.path)
const pageTitle = computed(() => (route.meta.title as string) || 'LearnPath-KG')
</script>

<style scoped>
.app-layout {
  height: 100vh;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-bottom: 1px solid #e6e6e6;
}

.logo h2 {
  margin: 0;
  font-size: 18px;
  color: var(--lp-primary);
}

.el-aside {
  border-right: 1px solid #e6e6e6;
  background: #fff;
}

.el-header {
  display: flex;
  align-items: center;
  border-bottom: 1px solid #e6e6e6;
  background: #fff;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
}

.el-main {
  background: var(--lp-bg);
}

@media (max-width: 768px) {
  .app-layout {
    height: auto;
    min-height: 100vh;
    flex-direction: column;
  }

  .el-aside {
    width: 100% !important;
    border-right: none;
    border-bottom: 1px solid #e6e6e6;
  }

  .el-header {
    height: auto;
    min-height: 56px;
    padding: 0 12px;
  }

  .el-main {
    padding: 12px;
  }

  .logo h2 {
    font-size: 16px;
  }
}
</style>