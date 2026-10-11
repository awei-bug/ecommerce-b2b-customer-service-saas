<template>
  <div class="page pay-page">
    <div class="card">
      <div class="top">
        <div class="label">扫码支付</div>
        <div class="amount"><em>¥</em>{{ formatPrice(amount) }}</div>
        <div v-if="name" class="goods">{{ name }}</div>
        <div v-if="orderNo" class="order">
          订单号 {{ orderNo }}
          <button type="button" class="copy" @click="copy(orderNo)">{{ copied ? '已复制' : '复制' }}</button>
        </div>
      </div>

      <div v-if="qr" class="qr-box">
        <img :src="qr" alt="微信收款码" class="qr" />
        <p class="tip">请使用微信扫一扫付款</p>
        <p class="tip sub">付款备注请填写订单号，店主确认后发货</p>
      </div>
      <div v-else class="qr-missing">
        <b>暂无法在线扫码付款</b>
        <p>店主尚未上传收款码。请联系店主完成付款后再在后台确认收款。</p>
        <p v-if="shop.contactPhone">客服：{{ shop.contactPhone }}</p>
      </div>

      <ClaimPaidBox
        v-if="orderId"
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
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { loadShop, mediaUrl, shop } from '@/utils/shop'
import ClaimPaidBox from '@/components/ClaimPaidBox.vue'
// shop reactive used in template

const route = useRoute()
const copied = ref(false)
const amount = computed(() => route.query.amount || 0)
const orderNo = computed(() => String(route.query.order_no || ''))
const name = computed(() => String(route.query.name || ''))
const orderId = computed(() => route.query.order_id || '')
const claimed = ref(false)
const claimNote = ref('')
const claimProof = ref('')
function onClaimed(data) {
  claimed.value = true
  claimNote.value = data?.buyer_paid_note || claimNote.value
  claimProof.value = data?.buyer_paid_proof || ''
}
const qr = computed(() => mediaUrl(shop.payQrWechat || shop.payQrAlipay))

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
onMounted(() => loadShop())
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
