<template>
  <div class="page pay-page">
    <div class="card">
      <div class="top">
        <div class="label">商家收款码 · 人工确认</div>
        <div v-if="order" class="amount"><em>¥</em>{{ formatPrice(order.price) }}</div>
        <div v-if="orderNo" class="order">
          订单号 {{ orderNo }}
          <button type="button" class="copy" @click="copy(orderNo)">{{ copied ? '已复制' : '复制' }}</button>
        </div>
      </div>

      <p v-if="loading" class="tip" role="status">正在核对订单和收款信息…</p>
      <div v-else-if="error" class="qr-missing" role="alert">
        <b>无法确认付款信息</b>
        <p>{{ error }}</p>
        <button type="button" class="btn ghost" @click="loadPayment">重试</button>
      </div>
      <div v-else-if="order.status !== 'pending_pay'" class="qr-missing" role="status">
        <b>订单不再处于待付款状态</b>
        <p>请在订单列表查看最新状态；如有疑问，请联系商家。</p>
      </div>
      <div v-else-if="claimed" class="qr-missing" role="status">
        <b>已通知商家核对收款</b>
        <p>请勿重复付款，等待商家确认。</p>
      </div>
      <div v-else-if="qr" class="qr-box">
        <img :src="qr" :alt="qrLabel + '收款码'" class="qr" />
        <p class="tip">请使用{{ qrLabel }}扫一扫付款</p>
        <p class="tip sub">付款备注请填写订单号，店主确认后发货</p>
      </div>
      <div v-else class="qr-missing">
        <b>暂无法在线扫码付款</b>
        <p>店主尚未上传收款码。请联系店主完成付款后再在后台确认收款。</p>
        <p v-if="shop.contact_phone">客服：{{ shop.contact_phone }}</p>
      </div>

      <ClaimPaidBox
        v-if="order && order.status === 'pending_pay'"
        :order-id="orderId"
        :claimed="claimed"
        :note="claimNote"
        :proof="claimProof"
        @done="onClaimed"
      />

      <div class="actions">
        <button type="button" class="btn ghost" @click="$router.replace('/orders')">查看我的订单</button>
        <button type="button" class="btn ghost" @click="$router.replace('/')">返回首页</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getOrder, getShop } from '@/api'
import { mediaUrl } from '@/utils/shop'
import { getAuthVersion, getTenantSlug, getToken } from '@/utils/session'
import ClaimPaidBox from '@/components/ClaimPaidBox.vue'

const route = useRoute()
const copied = ref(false)
const order = ref(null)
const shop = ref({})
const loading = ref(true)
const error = ref('')
const orderNo = computed(() => order.value?.order_no || '')
const orderId = computed(() => order.value?.id || '')
const claimed = ref(false)
const claimNote = ref('')
const claimProof = ref('')
let loadVersion = 0
function invalidatePayment() {
  loadVersion++
  order.value = null
  shop.value = {}
  loading.value = false
  error.value = '登录或店铺已发生变化，请重新查看订单。'
}
function onClaimed(data) {
  claimed.value = true
  claimNote.value = data?.buyer_paid_note || claimNote.value
  claimProof.value = data?.buyer_paid_proof || ''
}
const qr = computed(() => mediaUrl(shop.value.pay_qr_wechat || shop.value.pay_qr_alipay))
const qrLabel = computed(() => shop.value.pay_qr_wechat ? '微信' : '支付宝')

async function loadPayment() {
  const version = ++loadVersion
  loading.value = true
  error.value = ''
  order.value = null
  shop.value = {}
  const tenant = getTenantSlug()
  const token = getToken()
  const authVersion = getAuthVersion()
  const id = String(route.query.order_id || '')
  try {
    if (!/^[1-9]\d*$/.test(id)) throw new Error('订单编号无效，请返回订单列表。')
    const [orderRes, shopRes] = await Promise.all([getOrder(id), getShop()])
    if (version !== loadVersion) return
    if (tenant !== getTenantSlug() || token !== getToken() || authVersion !== getAuthVersion()) {
      throw new Error('登录或店铺已发生变化，请重新查看订单。')
    }
    if (orderRes.status !== 200 || !orderRes.data) throw new Error(orderRes.msg || '订单加载失败，请返回订单列表。')
    if (shopRes.status !== 200 || !shopRes.data) throw new Error(shopRes.msg || '收款信息加载失败，请稍后重试。')
    const amount = Number(orderRes.data.price)
    if (!Number.isFinite(amount) || amount <= 0 || !orderRes.data.order_no) {
      throw new Error('订单金额或订单号异常，请联系商家核对。')
    }
    shop.value = shopRes.data
    order.value = orderRes.data
    claimed.value = !!orderRes.data.buyer_paid_claimed
    claimNote.value = orderRes.data.buyer_paid_note || ''
    claimProof.value = orderRes.data.buyer_paid_proof || ''
  } catch (err) {
    if (version === loadVersion) error.value = err.message || '付款信息加载失败，请稍后重试。'
  } finally {
    if (version === loadVersion) loading.value = false
  }
}

function formatPrice(n) {
  return Number(n || 0).toFixed(2)
}
async function copy(text) {
  try {
    await navigator.clipboard.writeText(String(text || ''))
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    window.prompt('复制订单号', String(text || ''))
  }
}
watch(() => route.query.order_id, loadPayment, { immediate: true })
onMounted(() => window.addEventListener('mall:auth-change', invalidatePayment))
onUnmounted(() => {
  loadVersion++
  window.removeEventListener('mall:auth-change', invalidatePayment)
})
</script>

<style scoped>
.pay-page {
  min-height: 70vh;
  display: grid;
  place-items: center;
  padding: 20px 12px 40px;
}
.card {
  width: min(400px, 100%);
  background: #fff;
  border-radius: 18px;
  border: 1px solid #eee7de;
  box-shadow: 0 12px 40px rgba(28, 25, 23, 0.08);
  padding: 22px 18px 18px;
  text-align: center;
}
.label {
  font-size: 13px;
  color: #78716c;
  margin-bottom: 6px;
}
.amount {
  font-size: 40px;
  font-weight: 800;
  color: #0f172a;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
}
.amount em {
  font-style: normal;
  font-size: 22px;
  margin-right: 2px;
}
.goods {
  margin-top: 8px;
  font-size: 14px;
  color: #57534e;
}
.order {
  margin-top: 10px;
  font-size: 12.5px;
  color: #78716c;
  display: flex;
  gap: 8px;
  justify-content: center;
  align-items: center;
  flex-wrap: wrap;
  word-break: break-all;
}
.copy {
  border: 0;
  background: #f5f5f4;
  color: #07c160;
  font-weight: 700;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 999px;
  cursor: pointer;
}
.qr-box {
  margin: 18px auto 8px;
  width: min(280px, 100%);
}
.qr {
  width: 100%;
  display: block;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06);
}
.tip {
  margin: 12px 0 0;
  font-size: 14px;
  color: #1c1917;
  font-weight: 600;
}
.tip.sub {
  margin-top: 4px;
  font-size: 12.5px;
  color: #a8a29e;
  font-weight: 400;
}
.qr-missing {
  margin: 20px 0;
  padding: 16px;
  background: #fff7ed;
  color: #9a3412;
  border-radius: 12px;
  font-size: 13px;
}
.actions {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.actions .btn {
  width: 100%;
  min-height: 44px;
}
</style>
