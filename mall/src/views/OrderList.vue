<template>
  <div class="page">
    <div class="page-bar">
      <div>
        <h2>我的订单</h2>
        <p class="hint">状态会随店长确认收款与发货更新；待付款请备注订单号转账</p>
      </div>
      <button class="btn ghost" :disabled="loading" @click="load">刷新</button>
    </div>

    <div class="tabs page-card">
      <button
        v-for="t in tabs"
        :key="t.key"
        type="button"
        :class="{ active: tab === t.key }"
        @click="tab = t.key"
      >{{ t.label }}</button>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="error" class="empty error">{{ error }}</div>
    <div v-else-if="!filtered.length" class="empty empty-card">
      <div class="empty-title">这里还没有订单</div>
      <p class="hint">去首页挑一件心仪的商品下单吧。</p>
      <button class="btn primary" type="button" @click="$router.push('/')">去选购</button>
    </div>
    <div v-else class="list">
      <article v-for="o in filtered" :key="o.id" class="order-card page-card" @click="goDetail(o)">
        <div class="top">
          <div class="no">{{ o.order_no || ('#' + o.id) }}</div>
          <span class="tag" :class="tagClass(o.status)">{{ o.status_label || labelOf(o.status) }}</span>
          <span v-if="o.status === 'pending_pay' && o.buyer_paid_claimed" class="tag claimed">已报付款</span>
        </div>
        <div class="addr">{{ o.address || '—' }}</div>
        <div class="bottom">
          <div class="amt">¥{{ formatPrice(o.price) }}</div>
          <div class="ops" @click.stop>
            <button class="btn ghost" type="button" @click="goDetail(o)">详情</button>
            <button
              v-if="o.status === 'pending_pay'"
              class="btn primary"
              type="button"
              @click="goPayGuide(o)"
            >查看付款说明</button>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getOrders } from '@/api'
import { isLoggedIn } from '@/utils/session'

const router = useRouter()
const list = ref([])
const loading = ref(false)
const error = ref('')
const tab = ref('all')

const tabs = [
  { key: 'all', label: '全部' },
  { key: 'pending_pay', label: '待付款' },
  { key: 'paid', label: '待发货' },
  { key: 'shipped', label: '已发货' },
  { key: 'completed', label: '已完成' },
]

const filtered = computed(() => {
  if (tab.value === 'all') return list.value
  return list.value.filter((o) => o.status === tab.value)
})

function formatPrice(n) { return Number(n || 0).toFixed(2) }
function labelOf(s) {
  return ({
    pending_pay: '待付款', paid: '待发货', shipped: '已发货',
    completed: '已完成', closed: '已关闭', refunding: '售后中', refunded: '已退款',
  })[s] || s
}
function tagClass(status) {
  if (['paid', 'shipped', 'completed'].includes(status)) return 'ok'
  if (status === 'pending_pay' || status === 'refunding') return 'warn'
  if (status === 'refunded' || status === 'closed') return 'danger'
  return ''
}
function goDetail(o) { router.push(`/order/${o.id}`) }
function goPayGuide(o) {
  router.push({
    path: '/pay-result',
    query: {
      order_id: o.id,
      order_no: o.order_no || o.id,
      status: 'await_manual',
      amount: o.price,
    },
  })
}

async function load() {
  if (!isLoggedIn()) {
    router.push({ path: '/login', query: { redirect: '/orders' } })
    return
  }
  loading.value = true
  error.value = ''
  try {
    const res = await getOrders()
    if (res.status === 401) {
      router.push({ path: '/login', query: { redirect: '/orders' } })
      return
    }
    if (res.status !== 200) {
      error.value = res.msg || '加载失败'
      list.value = []
      return
    }
    list.value = res.data || []
  } catch (e) {
    error.value = e.message || '加载失败'
    list.value = []
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page-bar { display:flex; justify-content:space-between; align-items:flex-end; gap:12px; margin-bottom:14px; }
.page-bar h2 { margin:0; font-size:24px; }
.hint { margin:6px 0 0; color:var(--muted); font-size:13px; }
.tabs { display:flex; gap:8px; flex-wrap:wrap; padding:10px 12px; margin-bottom:12px; }
.tabs button {
  border:1px solid var(--line); background:#fff; border-radius:999px;
  padding:6px 12px; cursor:pointer; color:var(--text-soft); font-size:13px;
}
.tabs button.active { background:var(--primary); border-color:var(--primary); color:#fff; font-weight:600; }
.list { display:grid; gap:12px; }
.order-card { cursor:pointer; padding:16px 18px; transition: box-shadow .15s ease; }
.order-card:hover { box-shadow: var(--shadow); }
.top { display:flex; justify-content:space-between; gap:10px; align-items:center; }
.no { font-weight:650; font-size:14px; }
.tag { font-size:12px; padding:3px 10px; border-radius:999px; background:#f3f0ea; color:#5b564e; }
.tag.ok { background:#ecfdf5; color:#047857; }
.tag.warn { background:#fff7ed; color:#c2410c; }
.tag.danger { background:#fef2f2; color:#b91c1c; }
.addr { margin-top:10px; color:var(--muted); font-size:13px; line-height:1.5; }
.bottom { margin-top:14px; display:flex; justify-content:space-between; align-items:center; gap:12px; }
.amt { font-size:18px; font-weight:700; color:var(--price); }
.ops { display:flex; gap:8px; }
.empty-card{padding:36px 16px;text-align:center}.empty-title{font-weight:800;margin-bottom:8px}.empty-card .hint{margin:0 auto 14px;max-width:280px;color:#8a8278}
.tag.claimed { background:#fff7ed; color:#c2410c; margin-left:6px; }
</style>
