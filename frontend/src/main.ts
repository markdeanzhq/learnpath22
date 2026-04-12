import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import { useSettingsStore } from './stores/settings'
import './styles/variables.css'

async function bootstrap() {
  const app = createApp(App)
  const pinia = createPinia()

  app.use(pinia)

  const settingsStore = useSettingsStore(pinia)
  await settingsStore.bootstrapSyncToBackend()

  app.use(router)
  app.use(ElementPlus)
  app.mount('#app')
}

void bootstrap()
