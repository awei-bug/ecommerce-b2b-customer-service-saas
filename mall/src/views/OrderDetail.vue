<template>
  <div class="page">
    <button class="back" type="button" @click="$router.back()">← 返回</button>
    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="error" class="empty error">{{ error }}</div>
    <template v-else-if="order">
      <section class="card">
        <div class="status" :class="tagClass(order.status)">
          {{ order.status_label || order.status }}
        </div>
        <div class="order-no">{{ order.order_no }}</div>
        <div class="amount-box">
          <div class="amount-row">
            <span>商品金额</span>
            <span>￥{{ formatPrice(order.goods_amount ?? order.price) }}</span>
          </div>
          <div class="amount-row">
            <span>运费</span>
            <span>￥{{ formatPrice(order.freight_amount || 0) }}</span>
          </div>
          <div class="amount-row total">
            <span>应付合计</span>
            <span class="price">￥{{ formatPrice(order.price) }}</span>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="h">收货信息</div>
        <p class="p">{{ order.address || '—' }}</p>
      </section>

      <section class="card" v-if="order.details?.length">
        <div class="h">商品明细</div>
        <div v-for="d in order.details" :key="d.id" class="line">
          <span>商品 #{{ d.pid }}</span>
          <span>×{{ d.number }}</span>
          <span>￥{{ formatPrice(d.total_price) }}</span>
        </div>
      </section>

      <button
        v-if="order.status === 'pending_pay'"
        class="btn primary block"
        :disabled="paying"
        @click="onPay"
      >
        {{ paying ? '支付中…' : '去支付' }}
      </button>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getOrder, payExistingOrder } from '@/api'

const route = useRoute()
const router = useRouter()
const order = ref(null)
const loading = ref(false)
const error = ref('')
const paying = ref(false)

function formatPrice(n) {
  return Number(n || 0).toFixed(2)
}

function tagClass(status) {
  if (['paid', 'shipped', 'completed'].includes(status)) return 'ok'
  if (status === 'pending_pay') return 'warn'
  return ''
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await getOrder(route.params.id)
    if (res.status !== 200) {
      error.value = res.msg || '订单不存在'
      return
    }
    order.value = res.data
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function onPay() {
  paying.value = true
  try {
    await payExistingOrder(order.value.id)
    router.replace({
      path: '/pay-result',
      query: {
        order_id: order.value.id,
        order_no: order.value.order_no,
        status: 'success',
        amount: order.value.price,
      },
    })
  } catch (e) {
    window.alert(e.message || '支付失败')
  } finally {
    paying.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page {
  max-width: 720px;
}
.back {
  border: none;
  background: transparent;
  color: var(--primary);
  font-size: 14px;
  padding: 0 0 12px;
  cursor: pointer;
}
.card {
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 18px 20px;
  margin-bottom: 12px;
}
.status {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  background: #f5f5f5;
  color: #8c8c8c;
}
.status.ok { background: #f6ffed; color: var(--ok); }
.status.warn { background: #fff7e6; color: var(--warn); }
.order-no {
  margin-top: 10px;
  font-size: 13px;
  color: var(--muted);
  word-break: break-all;
}
.amount-box {
  margin-top: 12px;
  display: grid;
  gap: 6px;
}
.amount-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: #4e5969;
}
.amount-row.total {
  margin-top: 4px;
  padding-top: 8px;
  border-top: 1px dashed #eee;
  font-weight: 600;
  color: var(--text);
}
.price {
  color: var(--danger);
  font-size: 20px;
  font-weight: 700;
}
.h {
  font-weight: 600;
  margin-bottom: 8px;
}
.p {
  margin: 0;
  color: #4e5969;
  font-size: 13px;
  line-height: 1.5;
}
.line {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 8px;
  font-size: 13px;
  padding: 6px 0;
  border-bottom: 1px solid #f0f0f0;
}
.block {
  width: 100%;
  border-radius: 12px;
  padding: 14px;
}
</style>
