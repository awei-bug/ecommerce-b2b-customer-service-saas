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

      <PayGuidePanel
        v-if="order.status === 'pending_pay'"
        class="pay-gap"
        :order-no="order.order_no || ''"
        :amount="order.price"
        title=""
      />
      <ClaimPaidBox
        v-if="order.status === 'pending_pay'"
        class="pay-gap"
        :order-id="order.id"
        :claimed="!!order.buyer_paid_claimed"
        :note="order.buyer_paid_note || ''"
        :proof="order.buyer_paid_proof || ''"
        @done="onClaimed"
      />

      <section class="card">
        <div class="h">收货信息</div>
        <p class="p">{{ order.address || '—' }}</p>
      </section>

      <section class="card" v-if="(order.details || order.order_detail || []).length">
        <div class="h">商品明细</div>
        <div v-for="d in (order.details || order.order_detail)" :key="d.id" class="line">
          <span>{{ d.product_name || d.name || ('商品 #' + d.pid) }}</span>
          <span>×{{ d.number }}</span>
          <span>￥{{ formatPrice(d.total_price) }}</span>
        </div>
      </section>

      <section class="card" v-if="order.express || order.express_content">
        <div class="h">物流信息</div>
        <p class="p">{{ order.express || order.express_content }}</p>
      </section>

      <button
        v-if="order.status === 'pending_pay'"
        class="btn primary block"
        type="button"
        @click="goPayGuide"
      >
        查看付款说明 / 复制订单号
      </button>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getOrder } from '@/api'
import PayGuidePanel from '@/components/PayGuidePanel.vue'
import ClaimPaidBox from '@/components/ClaimPaidBox.vue'
import { loadShop } from '@/utils/shop'

const route = useRoute()
const router = useRouter()
const order = ref(null)
const loading = ref(false)
const error = ref('')

function onClaimed(data) {
  if (data) order.value = { ...order.value, ...data }
}
function formatPrice(n) {
  return Number(n || 0).toFixed(2)
}
function tagClass(status) {
  if (['paid', 'shipped', 'completed'].includes(status)) return 'ok'
  if (status === 'pending_pay') return 'warn'
  return ''
}
function goPayGuide() {
  if (!order.value) return
  router.push({
    path: '/pay-result',
    query: {
      order_id: order.value.id,
      order_no: order.value.order_no,
      status: 'await_manual',
      amount: order.value.price,
    },
  })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    await loadShop()
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

onMounted(load)
</script>

<style scoped>
.page { max-width: 720px; }
.back {
  border: none;
  background: transparent;
  color: var(--brand, #0f766e);
  font-size: 14px;
  margin-bottom: 12px;
  cursor: pointer;
}
.card {
  background: var(--bg-elevated, #fff);
  border: 1px solid var(--line, #e8e0d4);
  border-radius: 16px;
  padding: 16px;
  margin-bottom: 12px;
}
.status {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
  background: #f1f5f9;
  color: #475569;
}
.status.ok { background: #ecfdf5; color: #047857; }
.status.warn { background: #fff7ed; color: #c2410c; }
.order-no {
  margin-top: 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  color: #64748b;
  word-break: break-all;
}
.amount-box { margin-top: 12px; }
.amount-row {
  display: flex;
  justify-content: space-between;
  font-size: 14px;
  margin: 6px 0;
  color: #57534e;
}
.amount-row.total { font-weight: 800; color: #1c1917; margin-top: 10px; }
.price { color: var(--price, #c2410c); }
.h { font-weight: 700; margin-bottom: 8px; }
.p { margin: 0; color: #57534e; line-height: 1.5; }
.line {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 10px;
  padding: 8px 0;
  border-top: 1px dashed #eee6da;
  font-size: 13.5px;
}
.pay-gap { margin-bottom: 12px; }
.btn.block { width: 100%; margin-top: 4px; }
.empty { padding: 40px 12px; text-align: center; color: #8a8278; }
.empty.error { color: #b91c1c; }
</style>
