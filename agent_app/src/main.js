import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './assets/main.css'

const app = createApp(App)

app.use(router)
// 等初始导航解析完成再挂载，避免首屏 matched 为空导致路由出口空白
router.isReady().then(() => {
  app.mount('#app')
})