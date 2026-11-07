<template>
  <div class="operations-page">
    <header class="operations-head">
      <div><h1>自动化运营中心</h1><p>查看运营检查和执行记录，也可以向运营助手询问店铺待办。</p></div>
      <el-button v-if="activeTab === 'checks'" :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
    </header>
    <el-tabs v-model="activeTab" aria-label="运营中心功能">
      <el-tab-pane label="运营检查" name="checks">
    <div v-loading="loading">
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <div v-else-if="!loading" class="operations-body">
      <section class="operations-section" aria-labelledby="rule-title">
        <div class="section-heading"><div><h2 id="rule-title">运营检查</h2><p>手动运行已有规则，结果记录在下方。</p></div></div>
        <el-table :data="rules" empty-text="暂无可用规则" row-key="id">
          <el-table-column prop="name" label="检查规则" min-width="180" />
          <el-table-column label="状态" width="100"><template #default="{ row }">{{ row.status === 'enabled' ? '已启用' : '已停用' }}</template></el-table-column>
          <el-table-column label="最近运行" min-width="160"><template #default="{ row }">{{ formatTime(row.last_run_at) }}</template></el-table-column>
          <el-table-column label="操作" width="120"><template #default="{ row }"><el-button link type="primary" :loading="running === row.id" :disabled="running !== null" @click="run(row)">运行检查</el-button></template></el-table-column>
        </el-table>
      </section>
      <section class="operations-section" aria-labelledby="history-title">
        <div class="section-heading"><div><h2 id="history-title">最近运行记录</h2><p>结果来自当前商家店铺。</p></div></div>
        <ul v-if="runs.length" class="history-list"><li v-for="item in runs" :key="item.id"><div><strong>{{ item.summary || '运行记录' }}</strong><span>{{ item.status === 'success' ? '已完成' : item.status === 'failed' ? '失败' : '处理中' }}</span></div><time>{{ formatTime(item.finished_at || item.started_at) }}</time></li></ul>
        <el-empty v-else description="暂无运行记录" :image-size="64" />
      </section>
    </div>
    </div>
      </el-tab-pane>
      <el-tab-pane label="运营助手" name="assistant" lazy><AgentOpsView /></el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import api from '@/api/index.js'
import AgentOpsView from './AgentOpsView.vue'

const route = useRoute()
const router = useRouter()
const activeTab = computed({
  get: () => route.query.tab === 'assistant' ? 'assistant' : 'checks',
  set: (tab) => router.replace({ path: '/operations_center', query: tab === 'assistant' ? { tab } : {} }),
})
const loading = ref(false)
const running = ref(null)
const error = ref('')
const rules = ref([])
const runs = ref([])
function formatTime(value) { return value ? String(value).replace('T', ' ').slice(0, 16) : '尚未运行' }
async function load() {
  loading.value = true
  error.value = ''
  try {
    const [overview, ruleResponse] = await Promise.all([api.automation_overview({ days: 30 }), api.automation_rules()])
    if (overview.data.status !== 200 || ruleResponse.data.status !== 200) throw new Error(overview.data.msg || ruleResponse.data.msg || '运营数据加载失败')
    rules.value = ruleResponse.data.data || []
    runs.value = overview.data.data?.automation?.recent_runs || []
  } catch (cause) {
    rules.value = []
    runs.value = []
    error.value = cause?.message || '运营数据加载失败，请稍后重试'
  } finally { loading.value = false }
}
async function run(row) {
  running.value = row.id
  try {
    const result = await api.run_automation_rule(row.id)
    if (result.data.status !== 200) throw new Error(result.data.msg || '检查未能运行')
    if (result.data.data?.status === 'failed') ElMessage.error(result.data.data.summary || '检查执行失败')
    else ElMessage.success('检查已执行')
    await load()
  } catch (cause) { ElMessage.error(cause?.message || '检查未能运行') }
  finally { running.value = null }
}
onMounted(load)
</script>

<style scoped>
.operations-page { max-width: 1320px; margin: 0 auto; }
.operations-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 24px; }
.operations-head h1 { font-size: 24px; margin: 0 0 8px; color: var(--el-text-color-primary); }
.operations-head p, .section-heading p { color: var(--el-text-color-secondary); margin: 0; line-height: 1.6; }
.operations-body { display: grid; gap: 20px; }
.operations-section { background: var(--el-bg-color); border: 1px solid var(--el-border-color-light); border-radius: 12px; padding: 22px; }
.section-heading { margin-bottom: 16px; }
.section-heading h2 { font-size: 17px; margin: 0 0 6px; }
.history-list { list-style: none; margin: 0; padding: 0; }
.history-list li { display: flex; justify-content: space-between; gap: 16px; align-items: center; padding: 14px 0; border-top: 1px solid var(--el-border-color-lighter); }
.history-list li div { display: grid; gap: 5px; }
.history-list span, .history-list time { color: var(--el-text-color-secondary); font-size: 13px; }
@media (max-width: 700px) { .operations-head { flex-wrap: wrap; } .operations-section { padding: 16px; } .history-list li { align-items: flex-start; flex-direction: column; gap: 6px; } }
</style>
