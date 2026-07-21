<template>
  <div class="page result-page">
    <div class="card page-card">
      <div class="icon" :class="statusClass">
        {{ iconText }}
      </div>
      <h2>{{ title }}</h2>
      <p class="msg">{{ message }}</p>

      <div v-if="orderNo || amount" class="meta">
        <div v-if="orderNo" class="row"><span>订单号</span><span>{{ orderNo }}</span></div>
        <div v-if="amount" class="row">
          <span>金额</span><span class="price">￥{{ formatPrice(amount) }}</span>
        </div>
      </div>

      <div v-if="payGuide && (status === 'await_manual' || status === 'unpaid')" class="guide-box">
        <div class="g-title">请按商家说明付款</div>
        <pre class="g-text">{{ payGuide }}</pre>
        <div v-if="contactPhone" class="phone">联系电话：{{ contactPhone }}</div>
      </div>

      <div class="actions">
        <button class="btn primary" type="button" @click="$router.replace('/orders')">
          查看我的订单
        </button>
        <button class="btn ghost" type="button" @click="$router.replace('/')">
          继续购物
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getShop } from '@/api'

const route = useRoute()
const payGuide = ref('')
const contactPhone = ref('')
const status = computed(() => String(route.query.status || 'await_manual'))
const orderNo = computed(() => route.query.order_no || '')
const amount = computed(() => route.query.amount || '')

const message = computed(() => {
  if (route.query.msg) return String(route.query.msg)
  if (status.value === 'success') return '订单已支付，商家将尽快处理发货'
  if (status.value === 'await_manual') {
    return '订单已提交。请按付款说明完成转账，并备注订单号；商家确认到账后会更新状态。'
  }
  if (status.value === 'unpaid') return '订单已创建，等待付款确认'
  return '支付未完成，可在订单列表查看状态'
})

const title = computed(() => {
  if (status.value === 'success') return '支付成功'
  if (status.value === 'await_manual') return '订单已提交'
  if (status.value === 'unpaid') return '待支付'
  return '未完成'
})

const iconText = computed(() => {
  if (status.value === 'success') return '✓'
  if (status.value === 'await_manual' || status.value === 'unpaid') return '!'
  return '✗'
})

const statusClass = computed(() => {
  if (status.value === 'success') return 'success'
  if (status.value === 'await_manual' || status.value === 'unpaid') return 'unpaid'
  return 'fail'
})

function formatPrice(n) {
  return Number(n || 0).toFixed(2)
}

onMounted(async () => {
  try {
    const res = await getShop()
    if (res.status === 200) {
      payGuide.value = res.data?.pay_guide || ''
      contactPhone.value = res.data?.contact_phone || ''
    }
  } catch (_) {
    /* ignore */
  }
})
</script>

<style scoped>
.result-page {
  display: flex;
  justify-content: center;
  padding-top: 40px;
}
.card {
  width: 100%;
  max-width: 520px;
  text-align: center;
  padding: 36px 32px;
}
.icon {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  margin: 0 auto 12px;
  display: grid;
  place-items: center;
  font-size: 28px;
  color: #fff;
  background: var(--ok);
}
.icon.fail,
.icon.error {
  background: var(--danger);
}
.icon.unpaid {
  background: var(--warn, #fa8c16);
}
h2 {
  margin: 8px 0;
  font-size: 22px;
}
.msg {
  color: var(--muted);
  font-size: 14px;
  line-height: 1.6;
  margin: 0 0 16px;
}
.meta {
  text-align: left;
  background: #f7f8fa;
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 16px;
}
.row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  padding: 4px 0;
}
.price {
  color: var(--danger);
  font-weight: 700;
}
.guide-box {
  text-align: left;
  border: 1px dashed #ffd591;
  background: #fffbe6;
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 16px;
}
.g-title {
  font-weight: 600;
  margin-bottom: 8px;
  font-size: 14px;
}
.g-text {
  margin: 0;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.6;
  color: #595959;
}
.phone {
  margin-top: 10px;
  font-size: 13px;
  color: #8c8c8c;
}
.actions {
  display: flex;
  gap: 10px;
  justify-content: center;
  flex-wrap: wrap;
}
</style>
