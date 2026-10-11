<template>
  <div class="page">
    <button class="back" type="button" @click="$router.push('/')">← 返回</button>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="error" class="empty error">{{ error }}</div>
    <div v-else-if="product" class="detail-layout page-card">
      <div class="hero-img">
        <img v-if="hasProductImage(product)" :src="imgUrl(product)" :alt="product.name" />
        <img v-else class="hero-ph" :src="placeholderForProduct(product)" :alt="product.name" />
      </div>

      <div class="panel">
        <div class="badge">现货</div>
        <h1 class="title">{{ product.name }}</h1>
        <div class="price"><small>¥</small>{{ formatPrice(product.price) }}</div>
        <p class="stock">库存 {{ product.number ?? 0 }}</p>
        <p class="desc">{{ product.introduce || '精选好物' }}</p>

        <button
          class="btn primary buy"
          type="button"
          :disabled="!canBuy || submitting"
          @click="openConfirm"
        >
          {{ canBuy ? '立即购买' : '暂时缺货' }}
        </button>

        <div class="lead-capture">
          <div class="lead-capture-head">
            <strong>想先了解再决定？</strong>
            <span>留下联系方式，获取报价、库存和交付信息</span>
          </div>
          <div v-if="leadSubmitted" class="lead-success" role="status">
            已收到咨询，商家会尽快联系你。
          </div>
          <form v-else class="lead-form" @submit.prevent="submitLead">
            <label>
              <span>称呼（选填）</span>
              <input v-model.trim="leadForm.contactName" maxlength="64" autocomplete="name" placeholder="怎么称呼你" />
            </label>
            <div class="lead-contact-row">
              <label>
                <span>联系方式</span>
                <select v-model="leadForm.contactType" aria-label="联系方式类型">
                  <option value="phone">手机号</option>
                  <option value="wechat">微信</option>
                  <option value="email">邮箱</option>
                  <option value="other">其他</option>
                </select>
              </label>
              <label class="lead-contact-value">
                <span>联系账号</span>
                <input v-model.trim="leadForm.contactValue" required maxlength="128" autocomplete="tel" placeholder="请输入手机号、微信或邮箱" />
              </label>
            </div>
            <label>
              <span>你的需求（选填）</span>
              <textarea v-model.trim="leadForm.demand" maxlength="1000" rows="3" placeholder="例如：需要 20 件，想确认优惠和到货时间" />
            </label>
            <button class="btn lead-submit" type="submit" :disabled="leadSubmitting">
              {{ leadSubmitting ? '正在提交…' : '提交咨询' }}
            </button>
            <small>提交即表示同意商家就本次咨询与你联系。</small>
          </form>
        </div>
      </div>
    </div>

    <OrderConfirmModal
      v-model="showConfirm"
      v-model:qty="qty"
      :product="product"
      :submitting="submitting"
      :default-phone="defaultPhone"
      :need-login="!loggedIn"
      :freight-amount="quote.freight"
      :freight-name="quote.freightName"
      :discount-amount="quote.discount"
      :coupon-label="quote.couponLabel"
      :has-pay-qr="quote.hasPayQr"
      @confirm="onConfirmPay"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createGrowthLead, createOrder, getProduct, previewFreight, smsLogin } from '@/api'
import { getCustomer, isLoggedIn, saveAuth } from '@/utils/session'
import { mediaUrl, loadShop, shop } from '@/utils/shop'
import { hasProductImage, placeholderForProduct } from '@/utils/placeholders'
import OrderConfirmModal from '@/components/OrderConfirmModal.vue'

const route = useRoute()
const router = useRouter()
const product = ref(null)
const loading = ref(false)
const error = ref('')
const qty = ref(1)
const showConfirm = ref(false)
const submitting = ref(false)
const defaultPhone = ref('')
const quote = ref({ freight: 0, freightName: '', discount: 0, couponLabel: '', hasPayQr: true, couponId: null })
const leadSubmitting = ref(false)
const leadSubmitted = ref(false)
const leadForm = ref({ contactName: '', contactType: 'phone', contactValue: '', demand: '' })

const canBuy = computed(() => Number(product.value?.number || 0) > 0)
const loggedIn = computed(() => isLoggedIn())

function formatPrice(n) {
  return Number(n || 0).toFixed(2)
}
function imgUrl(p) {
  return mediaUrl(p.big_img || p.small_img)
}

async function load({ silent = false } = {}) {
  if (!silent) loading.value = true
  error.value = ''
  try {
    await loadShop()
    const res = await getProduct(route.params.id)
    if (res.status !== 200) {
      error.value = res.msg || '商品不存在'
      return
    }
    const previousId = product.value?.id
    product.value = res.data
    if (!silent || previousId !== product.value.id) qty.value = 1
    const c = getCustomer()
    defaultPhone.value = c?.phone || ''
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    if (!silent) loading.value = false
  }
}


async function refreshQuote() {
  quote.value.hasPayQr = !!(shop.hasPayQr || shop.payQrWechat || shop.payQrAlipay)
  if (!product.value) return
  try {
    const res = await previewFreight({
      goods_amount: Number(product.value.price || 0) * Number(qty.value || 1),
      total_pieces: Number(qty.value || 1),
    })
    if (res && res.status === 200) {
      const d = res.data || {}
      quote.value.freight = Number(d.freight_amount || 0)
      quote.value.freightName = d.template?.name || ''
      quote.value.discount = Number(d.discount_amount || 0)
      quote.value.couponLabel = d.coupon?.name || ''
      quote.value.couponId = d.coupon?.id || null
    }
  } catch (e) {}
}

async function submitLead() {
  if (!product.value || !leadForm.value.contactValue) return
  leadSubmitting.value = true
  try {
    const res = await createGrowthLead({
      product_id: product.value.id,
      contact_name: leadForm.value.contactName,
      contact_type: leadForm.value.contactType,
      contact_value: leadForm.value.contactValue,
      demand: leadForm.value.demand,
      consent: true,
    })
    if (!res || res.status !== 200) {
      window.alert((res && res.msg) || '提交失败，请稍后重试')
      return
    }
    leadSubmitted.value = true
  } catch (e) {
    window.alert(e.message || '提交失败，请稍后重试')
  } finally {
    leadSubmitting.value = false
  }
}

function openConfirm() {
  if (!canBuy.value) return
  const c = getCustomer()
  defaultPhone.value = c?.phone || defaultPhone.value || ''
  refreshQuote()
  showConfirm.value = true
}

async function onConfirmPay({ phone, qty: q, address: addr = '', note = '', code = '' }) {
  if (!product.value) return
  submitting.value = true
  try {
    if (!isLoggedIn()) {
      const loginRes = await smsLogin({ phone, code })
      if (!loginRes || loginRes.status !== 200) {
        window.alert((loginRes && loginRes.msg) || '登录失败，请先获取验证码')
        return
      }
      saveAuth({ token: loginRes.data?.token, customer: loginRes.data?.customer })
    }
    const number = Number(q || 1)
    const addrPart = (addr || '').trim() || '地址待补充'
    const notePart = (note || '').trim()
    const address = `收货人电话 ${phone}；地址：${addrPart}` + (notePart ? `；备注：${notePart}` : '')
    const orderRes = await createOrder({
      items: [{ pid: product.value.id, number }],
      address,
      contact_name: '顾客',
      contact_phone: phone,
      coupon_id: quote.value.couponId,
    })
    if (orderRes.status !== 200) {
      window.alert(orderRes.msg || '下单失败')
      return
    }
    const order = orderRes.data || {}
    showConfirm.value = false
    router.replace({
      path: '/pay',
      query: {
        order_id: order.id,
        order_no: order.order_no || '',
        amount: order.price ?? Number(product.value.price) * number,
        name: product.value.name || '',
      },
    })
  } catch (e) {
    window.alert(e.message || '下单失败')
  } finally {
    submitting.value = false
  }
}

watch(qty, () => { if (showConfirm.value) refreshQuote() })

let syncTimer = null
let syncing = false
async function refreshProduct() {
  if (syncing || document.visibilityState === 'hidden') return
  syncing = true
  try { await load({ silent: true }) } finally { syncing = false }
}
function startProductSync() {
  syncTimer = window.setInterval(refreshProduct, 5000)
  window.addEventListener('focus', refreshProduct)
  document.addEventListener('visibilitychange', refreshProduct)
}
function stopProductSync() {
  if (syncTimer) clearInterval(syncTimer)
  syncTimer = null
  window.removeEventListener('focus', refreshProduct)
  document.removeEventListener('visibilitychange', refreshProduct)
}

onMounted(async () => {
  await load()
  startProductSync()
  if (product.value && String(route.query.buy) === '1') {
    openConfirm()
  }
})
watch(() => route.params.id, () => load())
onUnmounted(stopProductSync)
</script>

<style scoped>
.page { max-width: 960px; margin: 0 auto; }
.back {
  border: 0;
  background: transparent;
  color: #78716c;
  margin-bottom: 12px;
  cursor: pointer;
}
.detail-layout {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 24px;
  padding: 20px;
}
.hero-img {
  border-radius: 16px;
  overflow: hidden;
  background: #f5f2ec;
  min-height: 320px;
}
.hero-img img, .hero-ph {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  min-height: 320px;
}
.badge {
  display: inline-block;
  font-size: 12px;
  font-weight: 700;
  color: #0f766e;
  background: #ecfdf5;
  padding: 2px 8px;
  border-radius: 999px;
  margin-bottom: 8px;
}
.title {
  margin: 0 0 10px;
  font-size: 26px;
  line-height: 1.25;
}
.price {
  font-size: 32px;
  font-weight: 800;
  color: #c2410c;
  margin-bottom: 6px;
}
.price small { font-size: 18px; margin-right: 2px; }
.stock { color: #78716c; font-size: 13px; margin: 0 0 10px; }
.desc { color: #57534e; line-height: 1.6; margin: 0 0 18px; }
.buy {
  width: 100%;
  min-height: 48px;
  font-size: 16px;
}
.lead-capture {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid #e7e2da;
}
.lead-capture-head { display: grid; gap: 3px; margin-bottom: 12px; }
.lead-capture-head strong { color: #292524; font-size: 15px; }
.lead-capture-head span { color: #78716c; font-size: 12px; line-height: 1.5; }
.lead-form { display: grid; gap: 10px; }
.lead-form label { display: grid; gap: 5px; min-width: 0; }
.lead-form label > span { color: #57534e; font-size: 12px; font-weight: 700; }
.lead-form input,
.lead-form select,
.lead-form textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #d6d3d1;
  border-radius: 8px;
  padding: 9px 10px;
  color: #292524;
  background: #fff;
  font: inherit;
}
.lead-form input:focus,
.lead-form select:focus,
.lead-form textarea:focus {
  border-color: #c2410c;
  outline: 3px solid rgba(194, 65, 12, .12);
}
.lead-form textarea { resize: vertical; }
.lead-contact-row { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 8px; }
.lead-submit { min-height: 42px; color: #9a3412; background: #fff7ed; border: 1px solid #fdba74; }
.lead-submit:hover { background: #ffedd5; }
.lead-form small { color: #78716c; font-size: 11px; line-height: 1.5; }
.lead-success { padding: 12px; border-radius: 8px; color: #166534; background: #f0fdf4; font-size: 13px; }
.empty { padding: 48px; text-align: center; color: #8a8278; }
.empty.error { color: #b91c1c; }
@media (max-width: 800px) {
  .detail-layout { grid-template-columns: 1fr; padding: 12px; }
}
@media (max-width: 480px) {
  .lead-contact-row { grid-template-columns: 1fr; }
}
</style>
