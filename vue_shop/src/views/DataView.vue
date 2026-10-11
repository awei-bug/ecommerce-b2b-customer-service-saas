<template>
  <section class="owner-page">
    <header class="page-head">
      <div>
        <div class="title-line">
          <h1>经营驾驶舱</h1>
          <el-tag :type="isDemo ? 'warning' : 'success'" effect="plain" size="small">
            {{ isDemo ? '演示数据' : '真实经营数据' }}
          </el-tag>
        </div>
        <p>先看结果，再处理风险。客服价值按近 30 天口径统计。</p>
      </div>
      <div class="head-actions">
        <span v-if="generatedAt" class="updated">更新于 {{ generatedAt }}</span>
        <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
      </div>
    </header>

    <el-alert
      v-if="isDemo"
      class="source-alert"
      type="warning"
      :closable="false"
      show-icon
      title="当前指标来自标准演示业务数据，用于交付验收，不代表真实经营业绩。"
    />

    <div class="outcome-grid" aria-label="核心经营结果">
      <article v-for="item in outcomes" :key="item.label" class="outcome-item">
        <div class="outcome-label"><el-icon><component :is="item.icon" /></el-icon>{{ item.label }}</div>
        <strong>{{ item.value }}</strong>
        <span>{{ item.note }}</span>
      </article>
    </div>

    <div class="decision-grid">
      <section class="surface priority-surface">
        <div class="section-head">
          <div>
            <h2>今天优先处理</h2>
            <p>按顾客等待和资金风险排序</p>
          </div>
          <el-tag v-if="priorities.length" type="danger" effect="plain">{{ priorities.length }} 项</el-tag>
        </div>

        <div v-if="priorities.length" class="priority-list">
          <button
            v-for="(item, index) in priorities"
            :key="item.code"
            type="button"
            class="priority-row"
            @click="$router.push(item.route)"
          >
            <span class="rank" :class="item.level">{{ index + 1 }}</span>
            <span class="priority-copy">
              <strong>{{ item.title }}</strong>
              <small>{{ item.detail }}</small>
            </span>
            <span class="priority-count">{{ item.count }}</span>
            <el-icon><ArrowRight /></el-icon>
          </button>
        </div>
        <el-empty v-else :image-size="76" description="当前没有高优先级待办" />
      </section>

      <section class="surface service-surface">
        <div class="section-head">
          <div>
            <h2>客服效率</h2>
            <p>AI 与人工协同结果</p>
          </div>
          <el-button link type="primary" @click="$router.push('/customer_service')">进入工作台</el-button>
        </div>
        <div class="service-meter">
          <div class="meter-value">{{ percent(service.ai_resolution_rate) }}</div>
          <div class="meter-track" aria-label="AI 独立解决率">
            <span :style="{ width: `${clampedRate}%` }"></span>
          </div>
          <p>AI 独立解决率</p>
        </div>
        <dl class="service-facts">
          <div><dt>总咨询会话</dt><dd>{{ service.sessions || 0 }}</dd></div>
          <div><dt>转人工</dt><dd>{{ service.transferred || 0 }}</dd></div>
          <div><dt>平均首次响应</dt><dd>{{ minutes(service.avg_first_response_minutes) }}</dd></div>
          <div><dt>待接待 / 处理中</dt><dd>{{ service.waiting || 0 }} / {{ service.active || 0 }}</dd></div>
        </dl>
      </section>
    </div>

    <section class="surface queue-surface">
      <div class="section-head">
        <div>
          <h2>业务队列</h2>
          <p>需要员工实际完成的订单与库存动作</p>
        </div>
      </div>
      <div class="queue-grid">
        <button v-for="item in queuesSummary" :key="item.label" type="button" @click="$router.push(item.route)">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <small>{{ item.note }}</small>
          <el-icon><ArrowRight /></el-icon>
        </button>
      </div>
    </section>

    <div class="analysis-grid">
      <section class="surface chart-surface">
        <div class="section-head">
          <div>
            <h2>近 7 日订单与成交额</h2>
            <p>成交额只统计已支付及后续状态</p>
          </div>
        </div>
        <div ref="trendRef" class="chart"></div>
      </section>

      <section class="surface detail-surface">
        <div class="section-head">
          <div>
            <h2>客服辅助成交口径</h2>
            <p>订单创建时显式记录客服会话号</p>
          </div>
        </div>
        <div class="conversion-number">¥{{ money(conversion.assisted_gmv) }}</div>
        <p class="conversion-caption">{{ conversion.assisted_paid_orders || 0 }} 笔已支付 · {{ conversion.assisted_orders || 0 }} 笔辅助订单</p>
        <div class="method-note">
          <el-icon><InfoFilled /></el-icon>
          <span>这里只统计建立了明确会话关系的订单，不把时间接近的订单推测为 AI 成交。</span>
        </div>
        <div class="status-list">
          <div v-for="item in statusPie" :key="item.status">
            <span>{{ item.name }}</span><strong>{{ item.value }}</strong>
          </div>
          <el-empty v-if="!statusPie.length" :image-size="60" description="暂无订单" />
        </div>
      </section>
    </div>
  </section>
</template>

<script setup>
import { ArrowRight, ChatDotRound, InfoFilled, Money, Refresh, Star, Timer } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import api from '@/api/index.js'

const loading = ref(false)
const trendRef = ref(null)
let trendChart = null

const dashboard = reactive({
  today: {},
  todo: {},
  products: {},
  trend_7d: [],
  status_pie: [],
  business: { service: {}, conversion: {}, priorities: [] },
})

const business = computed(() => dashboard.business || {})
const service = computed(() => business.value.service || {})
const conversion = computed(() => business.value.conversion || {})
const priorities = computed(() => business.value.priorities || [])
const statusPie = computed(() => dashboard.status_pie || [])
const isDemo = computed(() => business.value.data_source === 'demo')
const generatedAt = computed(() => {
  const value = business.value.generated_at
  if (!value) return ''
  return new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
})
const clampedRate = computed(() => Math.max(0, Math.min(Number(service.value.ai_resolution_rate || 0), 100)))

const outcomes = computed(() => [
  {
    label: '客服辅助成交',
    value: `¥${money(conversion.value.assisted_gmv)}`,
    note: `${conversion.value.assisted_paid_orders || 0} 笔已支付订单`,
    icon: Money,
  },
  {
    label: 'AI 独立解决',
    value: percent(service.value.ai_resolution_rate),
    note: `${service.value.ai_resolved || 0} 个会话无需人工`,
    icon: ChatDotRound,
  },
  {
    label: '估算节省工时',
    value: `${Number(service.value.estimated_saved_hours || 0).toFixed(1)} 小时`,
    note: `按每会话 ${service.value.baseline_minutes || 6} 分钟估算`,
    icon: Timer,
  },
  {
    label: '人工服务满意度',
    value: service.value.satisfaction == null ? '暂无' : `${Number(service.value.satisfaction).toFixed(1)} / 5`,
    note: `${service.value.rated_count || 0} 个有效评价`,
    icon: Star,
  },
])

const queuesSummary = computed(() => [
  { label: '已报付款', value: dashboard.todo.claimed_pay || 0, note: '等待核对到账', route: '/order_list?status=pending_pay&claimed=1' },
  { label: '待发货', value: dashboard.todo.pending_ship || 0, note: '已付款待履约', route: '/order_list?status=paid' },
  { label: '售后中', value: dashboard.todo.refunding || 0, note: '等待人工处理', route: '/order_list?status=refunding' },
  { label: '低库存', value: dashboard.products.low_stock || 0, note: `在售 ${dashboard.products.on_sale || 0} 个`, route: '/product_list' },
])

function money(value) { return Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function percent(value) { return value == null ? '暂无' : `${Number(value).toFixed(1)}%` }
function minutes(value) { return value == null ? '暂无' : `${Number(value).toFixed(1)} 分钟` }

async function renderTrend() {
  await nextTick()
  if (!trendRef.value) return
  if (!trendChart) trendChart = echarts.init(trendRef.value)
  const rows = dashboard.trend_7d || []
  trendChart.setOption({
    animationDuration: 320,
    tooltip: { trigger: 'axis' },
    legend: { top: 0, right: 0, data: ['下单量', '成交额'] },
    grid: { left: 46, right: 50, top: 42, bottom: 26 },
    xAxis: { type: 'category', boundaryGap: true, data: rows.map(item => String(item.date || '').slice(5)), axisLine: { lineStyle: { color: '#d9d5ce' } } },
    yAxis: [
      { type: 'value', minInterval: 1, splitLine: { lineStyle: { color: '#efede8' } } },
      { type: 'value', splitLine: { show: false } },
    ],
    series: [
      { name: '下单量', type: 'bar', barMaxWidth: 26, data: rows.map(item => item.orders || 0), itemStyle: { color: '#0f766e', borderRadius: [3, 3, 0, 0] } },
      { name: '成交额', type: 'line', yAxisIndex: 1, smooth: true, symbolSize: 7, data: rows.map(item => Number(item.gmv || 0)), lineStyle: { width: 2, color: '#c2410c' }, itemStyle: { color: '#c2410c' } },
    ],
  }, true)
}

async function load() {
  loading.value = true
  try {
    const response = await api.dashboard_kpi()
    const body = response?.data || {}
    if (body.status !== 200) throw new Error(body.msg || '经营数据加载失败')
    Object.assign(dashboard, body.data || {})
    await renderTrend()
  } catch (error) {
    ElMessage.error(error.message || '经营数据加载失败')
  } finally {
    loading.value = false
  }
}

function onResize() { trendChart?.resize() }

onMounted(() => {
  load()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  trendChart?.dispose()
})
</script>

<style scoped>
.owner-page { max-width: 1440px; margin: 0 auto; color: #24211d; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; margin-bottom: 14px; }
.title-line { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.page-head h1 { margin: 0; font-size: 22px; line-height: 1.35; letter-spacing: 0; }
.page-head p { margin: 5px 0 0; color: #777168; font-size: 13px; }
.head-actions { display: flex; align-items: center; gap: 12px; }
.updated { color: #918b82; font-size: 12px; }
.source-alert { margin-bottom: 14px; }
.outcome-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid #dfdbd3; background: #fff; }
.outcome-item { min-width: 0; padding: 18px; border-right: 1px solid #ebe7df; }
.outcome-item:last-child { border-right: 0; }
.outcome-label { display: flex; align-items: center; gap: 7px; color: #716b62; font-size: 12px; font-weight: 650; }
.outcome-label .el-icon { color: #0f766e; }
.outcome-item strong { display: block; margin-top: 10px; color: #191714; font-size: 27px; line-height: 1.15; font-variant-numeric: tabular-nums; }
.outcome-item > span { display: block; margin-top: 7px; color: #8b857c; font-size: 12px; }
.decision-grid { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(300px, .55fr); gap: 14px; margin-top: 14px; }
.surface { background: #fff; border: 1px solid #dfdbd3; }
.section-head { min-height: 58px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 16px; border-bottom: 1px solid #ebe7df; }
.section-head h2 { margin: 0; font-size: 15px; line-height: 1.35; letter-spacing: 0; }
.section-head p { margin: 3px 0 0; color: #8b857c; font-size: 12px; }
.priority-list { display: flex; flex-direction: column; }
.priority-row { display: grid; grid-template-columns: 28px minmax(0, 1fr) auto 18px; align-items: center; gap: 12px; width: 100%; min-height: 64px; padding: 10px 16px; border: 0; border-bottom: 1px solid #f0ede7; background: transparent; text-align: left; cursor: pointer; color: inherit; }
.priority-row:last-child { border-bottom: 0; }
.priority-row:hover { background: #f8f7f4; }
.rank { width: 26px; height: 26px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid #d8d4cc; border-radius: 50%; color: #6f6960; font-size: 12px; font-weight: 700; }
.rank.urgent { border-color: #efb1a8; background: #fff1ef; color: #b42318; }
.rank.warning { border-color: #f1c98e; background: #fff8e8; color: #a15c07; }
.priority-copy { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.priority-copy strong { font-size: 13px; }
.priority-copy small { overflow: hidden; color: #847e75; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.priority-count { color: #24211d; font-size: 18px; font-weight: 750; font-variant-numeric: tabular-nums; }
.service-surface { min-width: 0; }
.service-meter { padding: 20px 16px 14px; }
.meter-value { color: #0f766e; font-size: 32px; font-weight: 760; font-variant-numeric: tabular-nums; }
.meter-track { height: 7px; margin-top: 10px; overflow: hidden; background: #e8e5df; }
.meter-track span { display: block; height: 100%; background: #0f766e; }
.service-meter p { margin: 7px 0 0; color: #817b72; font-size: 12px; }
.service-facts { display: grid; grid-template-columns: 1fr 1fr; margin: 0; border-top: 1px solid #ebe7df; }
.service-facts div { min-width: 0; padding: 12px 16px; border-right: 1px solid #ebe7df; border-bottom: 1px solid #ebe7df; }
.service-facts div:nth-child(2n) { border-right: 0; }
.service-facts div:nth-last-child(-n+2) { border-bottom: 0; }
.service-facts dt { color: #8b857c; font-size: 11px; }
.service-facts dd { margin: 5px 0 0; color: #2d2924; font-size: 14px; font-weight: 700; }
.queue-surface { margin-top: 14px; }
.queue-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.queue-grid button { position: relative; min-width: 0; min-height: 100px; padding: 16px; border: 0; border-right: 1px solid #ebe7df; background: transparent; text-align: left; cursor: pointer; color: inherit; }
.queue-grid button:last-child { border-right: 0; }
.queue-grid button:hover { background: #f8f7f4; }
.queue-grid span { display: block; color: #706a61; font-size: 12px; }
.queue-grid strong { display: block; margin: 5px 0; font-size: 24px; font-variant-numeric: tabular-nums; }
.queue-grid small { color: #8e887f; }
.queue-grid .el-icon { position: absolute; top: 18px; right: 14px; color: #aaa49a; }
.analysis-grid { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(300px, .5fr); gap: 14px; margin-top: 14px; }
.chart { width: 100%; height: 300px; padding: 8px 10px 4px; }
.conversion-number { padding: 20px 16px 0; font-size: 30px; font-weight: 760; color: #191714; font-variant-numeric: tabular-nums; }
.conversion-caption { margin: 5px 16px 16px; color: #746e65; font-size: 12px; }
.method-note { display: flex; align-items: flex-start; gap: 8px; margin: 0 16px 14px; padding: 10px; background: #edf6f3; color: #41635d; font-size: 11px; line-height: 1.55; }
.method-note .el-icon { flex: 0 0 auto; margin-top: 2px; }
.status-list { border-top: 1px solid #ebe7df; }
.status-list > div { display: flex; align-items: center; justify-content: space-between; padding: 9px 16px; border-bottom: 1px solid #f0ede7; font-size: 12px; }
.status-list > div:last-child { border-bottom: 0; }
@media (max-width: 1080px) {
  .outcome-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .outcome-item:nth-child(2) { border-right: 0; }
  .outcome-item:nth-child(-n+2) { border-bottom: 1px solid #ebe7df; }
  .decision-grid, .analysis-grid { grid-template-columns: 1fr; }
}
@media (max-width: 680px) {
  .page-head { align-items: stretch; flex-direction: column; }
  .head-actions { justify-content: space-between; }
  .outcome-grid { grid-template-columns: 1fr 1fr; }
  .outcome-item { padding: 14px; }
  .outcome-item strong { font-size: 21px; }
  .queue-grid { grid-template-columns: 1fr 1fr; }
  .queue-grid button:nth-child(2) { border-right: 0; }
  .queue-grid button:nth-child(-n+2) { border-bottom: 1px solid #ebe7df; }
  .priority-row { grid-template-columns: 26px minmax(0, 1fr) auto; gap: 9px; padding: 10px 12px; }
  .priority-row > .el-icon { display: none; }
  .priority-copy small { white-space: normal; }
  .section-head { padding: 11px 12px; }
  .chart { height: 260px; }
}
</style>
