<template>
  <div class="page-card" v-loading="loading">
    <h2>统一经营看板</h2>
    <p>
      四个系统的真实数据由服务端一次聚合。云购订单与库存事件驱动跨境预警、
      内容平台补货草稿与数据中心运营提示；任一上游不可用时该路标记不可用，
      页面不补演示数据。
    </p>

    <el-row :gutter="12" style="margin-top: 12px">
      <el-col v-for="card in cards" :key="card.key" :xs="24" :sm="12" :md="6">
        <el-card shadow="never">
          <div>{{ card.label }}</div>
          <h3 style="margin: 6px 0">{{ card.value }}</h3>
          <el-space wrap size="small">
            <el-tag :type="card.status === 'ok' ? 'success' : 'info'" size="small">
              {{ card.status === 'ok' ? '实时' : '不可用' }}
            </el-tag>
            <span>{{ card.sub }}</span>
            <span v-if="card.latency !== null">{{ card.latency }} ms</span>
          </el-space>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" style="margin-top: 12px">
      <el-col :span="24">
        <el-space wrap>
          <el-button size="small" :loading="loading" @click="load">刷新</el-button>
          <span v-if="overview">生成时间 {{ overview.generated_at }}</span>
          <span v-if="overview">健康来源 {{ overview.summary.healthy }} / {{ overview.summary.total }}</span>
        </el-space>
      </el-col>
    </el-row>

    <el-alert
      v-for="item in unavailable"
      :key="item.key"
      type="warning"
      :closable="false"
      show-icon
      :title="`${item.label} 暂不可用：${item.error}`"
      style="margin-top: 10px"
    />

    <h3 style="margin-top: 20px">最近云购订单</h3>
    <el-table :data="recentOrders" size="small" empty-text="暂无订单">
      <el-table-column prop="order_no" label="订单号" min-width="200" />
      <el-table-column prop="price" label="金额" width="110" />
      <el-table-column prop="status" label="状态" width="130" />
      <el-table-column prop="created_at" label="创建时间" min-width="160" />
    </el-table>

    <h3 style="margin-top: 20px">跨境低库存预警（来自云购库存事件）</h3>
    <el-table :data="alerts" size="small" empty-text="暂无预警">
      <el-table-column prop="item_title" label="商品" min-width="180" />
      <el-table-column prop="product_id" label="云购商品 ID" width="120" />
      <el-table-column prop="stock_after" label="当前库存" width="110" />
      <el-table-column prop="source" label="来源" width="110" />
      <el-table-column prop="occurred_at" label="事件时间" min-width="170" />
    </el-table>

    <h3 style="margin-top: 20px">内容平台补货草稿（回推数据中心 ops_note）</h3>
    <el-table :data="drafts" size="small" empty-text="暂无草稿">
      <el-table-column prop="title" label="草稿" min-width="220" show-overflow-tooltip />
      <el-table-column prop="itemTitle" label="商品" min-width="160" />
      <el-table-column prop="stockAfter" label="库存" width="90" />
      <el-table-column prop="hubStatus" label="回推状态" width="120" />
      <el-table-column prop="createdAt" label="生成时间" min-width="170" />
    </el-table>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/index.js'

const overview = ref(null)
const loading = ref(false)
let timer = null

const cards = computed(() => {
  const s = overview.value?.sources || {}
  return [
    {
      key: 'shop', label: '云购订单',
      value: s.shop?.orders ?? '—',
      sub: `领域事件 ${s.shop?.events ?? '—'} 条`,
      status: s.shop?.status, latency: s.shop?.latency_ms ?? null,
    },
    {
      key: 'cross', label: '低库存预警',
      value: s.cross?.alerts ?? '—',
      sub: `已投影 ${s.cross?.total_projections ?? '—'} 条`,
      status: s.cross?.status, latency: s.cross?.latency_ms ?? null,
    },
    {
      key: 'content', label: '补货草稿',
      value: s.content?.drafts ?? '—',
      sub: '内容平台按事件生成',
      status: s.content?.status, latency: s.content?.latency_ms ?? null,
    },
    {
      key: 'hub', label: '数据中心商品',
      value: s.hub?.products ?? '—',
      sub: '已登记外部标识',
      status: s.hub?.status, latency: s.hub?.latency_ms ?? null,
    },
  ]
})

const unavailable = computed(() =>
  cards.value
    .filter((card) => card.status === 'unavailable')
    .map((card) => ({
      key: card.key,
      label: card.label,
      error: overview.value?.sources?.[card.key]?.error || '未知原因',
    })),
)

const sources = computed(() => overview.value?.sources || {})
const recentOrders = computed(() => sources.value.shop?.recent_orders || [])
const alerts = computed(() => sources.value.cross?.items || [])
const drafts = computed(() => sources.value.content?.items || [])

async function load() {
  loading.value = true
  try {
    const res = await api.get_unified_overview()
    if (res?.data?.status === 200) overview.value = res.data.data
    else ElMessage.warning(res?.data?.msg || '统一看板数据读取失败')
  } catch (error) {
    ElMessage.error(error?.userMessage || '统一看板数据读取失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  timer = window.setInterval(load, 30000)
})
onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})
</script>
