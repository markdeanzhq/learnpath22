import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

function getManualChunk(id: string) {
  const normalizedId = id.replace(/\\/g, '/')
  if (!normalizedId.includes('/node_modules/')) return undefined

  if (normalizedId.includes('/cytoscape/')) return 'graph-vendor'
  if (normalizedId.includes('/@element-plus/icons-vue/')) return 'element-icons'
  if (
    normalizedId.includes('/element-plus/') ||
    normalizedId.includes('/@vueuse/') ||
    normalizedId.includes('/@floating-ui/') ||
    normalizedId.includes('/async-validator/') ||
    normalizedId.includes('/lodash-unified/') ||
    normalizedId.includes('/dayjs/')
  ) {
    return 'element-plus'
  }
  if (
    normalizedId.includes('/vue/') ||
    normalizedId.includes('/@vue/') ||
    normalizedId.includes('/vue-router/') ||
    normalizedId.includes('/pinia/')
  ) {
    return 'vue-vendor'
  }
  if (normalizedId.includes('/axios/')) return 'http-vendor'
  return 'vendor'
}

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: getManualChunk,
      },
    },
  },
})
