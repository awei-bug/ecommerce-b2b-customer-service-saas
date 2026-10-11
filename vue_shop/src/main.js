import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import elementIcon from './plugins/icons'
import echartsPlugin from './plugins/echarts'
import ElementPlus from 'element-plus'
import { ElMessage } from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import './styles/admin.css'

const app = createApp(App)

app.config.errorHandler = (err, instance, info) => {
  console.error('[vue error]', info, err)
  try { ElMessage.error(err?.message || '页面出错') } catch (e) {}
}

app.use(router)
app.use(ElementPlus, { locale: zhCn })
app.use(elementIcon)
app.use(echartsPlugin)
app.mount('#app')

router.onError((err) => {
  console.error('[router error]', err)
  ElMessage.error('页面加载失败: ' + (err?.message || '未知错误'))
})
