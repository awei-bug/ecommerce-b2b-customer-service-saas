<template>
  <div class="page">
    <div class="page-bar">
      <div>
        <h2>我的订单</h2>
        <p class="hint">登录后可查看本店订单</p>
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
      >
        {{ t.label }}
      </button>
    </div>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="error" class="empty error">{{ error }}</div>
    <div v-else-if="!filtered.length" class="empty">
      暂无订单
      <div style="margin-top: 12px">
        <button class="btn primary" @click="$router.push('/')">去首页购物</button>
      </div>
    </div>
    <div v-else class="table-wrap page-card">
      <table class="order-table">
        <thead>
          <tr>
            <th>订单号</th>
            <th>状态</th>
            <th>收货信息</th>
            <th>金额</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="o in filtered" :key="o.id">
            <td class="mono">{{ o.order_no || ('#' + o.id) }}</td>
            <td>
              <span class="tag" :class="tagClass(o.status)">{{ o.status_label || o.status }}</span>
            </td>
            <td class="addr">{{ o.address || '—' }}</td>
            <td class="price">￥{{ formatPrice(o.price) }}</td>
            <td class="ops">
              <button class="btn ghost" @click="goDetail(o)">详情</button>
              <button
                v-if="o.status === 'pending_pay'"
                class="btn primary"
                :disabled="busyId === o.id"
                @click="onPay(o)"
              >
                {{ busyId === o.id ? '支付中…' : '去支付' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getOrders, payExistingOrder } from '@/api'

const router = useRouter()
const list = ref([])
const loading = ref(false)
const error = ref('')
const busyId = ref(null)
const tab = ref('all')

const tabs = [
  { key: 'all', label: '全部' },
  { key: 'pending_pay', label: '待付款' },
  { key: 'paid', label: '待发货' },
  { key: 'shipped', label: '待收货' },
]

const filtered = computed(() => {
  if (tab.value === 'all') return list.value
  return list.value.filter((o) => o.status === tab.value)
})

function formatPrice(n) {
  return Number(n || 0).toFixed(2)
}

function tagClass(status) {
  if (['paid', 'shipped', 'completed'].includes(status)) return 'ok'
  if (status === 'pending_pay') return 'warn'
  if (status === 'refunding') return 'warn'
  if (status === 'refunded') return 'danger'
  return 'muted'
}

function goDetail(o) {
  router.push(`/order/${o.id}`)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await getOrders()
    if (res.status === 401) {
      error.value = '请先登录'
      list.value = []
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

async function onPay(o) {
  busyId.value = o.id
  try {
    await payExistingOrder(o.id)
    router.push({
      path: '/pay-result',
      query: {
        order_id: o.id,
        order_no: o.order_no,
        status: 'success',
        amount: o.price,
      },
    })
  } catch (e) {
    window.alert(e.message || '支付失败')
  } finally {
    busyId.value = null
  }
}

onMounted(() => {
  load()
  window.addEventListener('mall:auth-change', load)
})
onUnmounted(() => {
  window.removeEventListener('mall:auth-change', load)
})
</script>

<style scoped>
.page-bar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}
.page-bar h2 {
  margin: 0;
  font-size: 20px;
}
.hint {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 13px;
}
.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px 12px;
}
.tabs button {
  border: none;
  background: transparent;
  color: var(--muted);
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 13px;
  cursor: pointer;
}
.tabs button.active {
  background: #e6f4ff;
  color: var(--primary);
  font-weight: 600;
}
.table-wrap {
  padding: 0;
  overflow: auto;
}
.order-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.order-table th,
.order-table td {
  padding: 14px 16px;
  border-bottom: 1px solid #f0f0f0;
  text-align: left;
  vertical-align: middle;
}
.order-table th {
  background: #fafafa;
  color: #646a73;
  font-weight: 600;
}
.mono {
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  word-break: break-all;
  max-width: 200px;
}
.addr {
  color: #4e5969;
  max-width: 280px;
  line-height: 1.4;
}
.price {
  color: var(--danger);
  font-weight: 700;
  white-space: nowrap;
}
.ops {
  display: flex;
  gap: 8px;
  white-space: nowrap;
}
.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  background: #f5f5f5;
  color: #8c8c8c;
}
.tag.ok { background: #f6ffed; color: var(--ok); }
.tag.warn { background: #fff7e6; color: var(--warn); }
.tag.danger { background: #fff1f0; color: var(--danger); }
</style>
