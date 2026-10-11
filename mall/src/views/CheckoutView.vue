<template>
  <div class="page checkout-page">
    <button class="back" type="button" @click="$router.back()">← 返回</button>
    <h2 class="page-h fx-rise">确认订单</h2>

    <div v-if="loading" class="empty">加载中…</div>
    <div v-else-if="error" class="empty error">{{ error }}</div>
    <div v-else class="layout">
      <div class="main-col">
        <section class="page-card reveal">
          <div class="card-h">收货信息</div>
          <div v-if="addresses.length" class="addr-list">
            <label
              v-for="a in addresses"
              :key="a.id"
              class="addr-item"
              :class="{ active: addressId === a.id }"
            >
              <input v-model="addressId" type="radio" :value="a.id" />
              <div>
                <div class="line1">{{ a.contact_name }} {{ a.contact_phone }}</div>
                <div class="line2">{{ a.full_address || `${a.region || ''}${a.detail}` }}</div>
              </div>
            </label>
          </div>
          <div v-else class="muted-box">暂无地址，请填写下方信息</div>

          <div class="new-addr">
            <div class="card-h small">新建地址</div>
            <div class="form-grid">
              <input v-model="form.contact_name" placeholder="收货人" />
              <input v-model="form.contact_phone" placeholder="手机号" maxlength="11" />
              <input v-model="form.region" placeholder="省市区（可选）" class="full" />
              <input v-model="form.detail" placeholder="详细地址" class="full" />
            </div>
            <button class="btn ghost" type="button" :disabled="savingAddr" @click="saveAddress">
              {{ savingAddr ? '保存中…' : '保存为收货地址' }}
            </button>
          </div>
        </section>

        <section class="page-card reveal" v-if="product">
          <div class="card-h">商品信息</div>
          <div class="goods">
            <div class="g-name">{{ product.name }}</div>
            <div class="g-meta">
              <span>单价 ￥{{ formatPrice(product.price) }}</span>
              <span>数量 × {{ qty }}</span>
            </div>
          </div>
        </section>
      </div>


        <section class="page-card pay-guide-card">
          <PayGuidePanel compact />
        </section>

        <aside class="side-col page-card reveal delay-2">
        <div class="card-h">应付合计</div>
        <div class="row">
          <span>商品金额</span>
          <span>￥{{ formatPrice(goodsAmount) }}</span>
        </div>
        <div class="row">
          <span>运费{{ freightName ? `（${freightName}）` : '' }}</span>
          <span>{{ freightAmount > 0 ? `￥${formatPrice(freightAmount)}` : '包邮' }}</span>
        </div>
        <div class="row" v-if="discountAmount > 0">
          <span>{{ couponLabel || '优惠' }}</span>
          <span class="off">-￥{{ formatPrice(discountAmount) }}</span>
        </div>
        <div class="row strong">
          <span>实付</span>
          <span class="price">￥{{ formatPrice(payAmount) }}</span>
        </div>
        <p v-if="!hasPayQr" class="tip err">店主尚未上传收款码，暂时不能提交订单。请联系店主。</p>
        <div class="pay-guide" v-if="false && payGuide">
          <div class="card-h small">付款说明</div>
          <pre class="guide-text">{{ payGuide }}</pre>
        </div>
        <button class="btn primary submit" type="button" :disabled="submitting || !hasPayQr" @click="submit">
          {{ !hasPayQr ? '暂不可支付' : (submitting ? '提交中…' : '提交订单并去付款') }}
        </button>
        <p class="tip">
          提交后将显示收款码：微信扫码付款，备注订单号即可。

        </p>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { shop } from '@/utils/shop'
import PayGuidePanel from '@/components/PayGuidePanel.vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  createAddress,
  createOrder,
  createPayment,
  getAddresses,
  getProduct,
  getShop,
  mockPay,
  previewFreight,
} from '@/api'

const route = useRoute()
const router = useRouter()

const product = ref(null)
const qty = ref(Number(route.query.qty || 1) || 1)
const addresses = ref([])
const addressId = ref(null)
const loading = ref(true)
const error = ref('')
const savingAddr = ref(false)
const submitting = ref(false)
const freightAmount = ref(0)
const freightName = ref('')
const discountAmount = ref(0)
const couponLabel = ref('')
const couponId = ref(null)
const hasPayQr = ref(true)
const payGuide = ref('')
const allowDevMock = ref(false)

const form = reactive({
  contact_name: '',
  contact_phone: '',
  region: '',
  detail: '',
})

const goodsAmount = computed(() => Number(product.value?.price || 0) * qty.value)
const payAmount = computed(() => {
  const n = goodsAmount.value + Number(freightAmount.value || 0) - Number(discountAmount.value || 0)
  return n > 0 ? n : 0
})

function formatPrice(n) {
  return Number(n || 0).toFixed(2)
}

async function refreshFreight() {
  if (!product.value) {
    freightAmount.value = 0
    freightName.value = ''
    return
  }
  try {
    const res = await previewFreight({
      goods_amount: goodsAmount.value,
      total_pieces: qty.value,
    })
    if (res.status === 200) {
      freightAmount.value = Number(res.data?.freight_amount || 0)
      freightName.value = res.data?.template?.name || ''
      discountAmount.value = Number(res.data?.discount_amount || 0)
      couponLabel.value = res.data?.coupon?.name || ''
      couponId.value = res.data?.coupon?.id || null
    }
  } catch {
    freightAmount.value = 0
    freightName.value = ''
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const pid = route.query.pid
    if (!pid) {
      error.value = '缺少商品信息，请从商品详情进入'
      return
    }
    const [pRes, aRes, shopRes] = await Promise.all([
      getProduct(pid),
      getAddresses(),
      getShop().catch(() => null),
    ])
    if (pRes.status !== 200) {
      error.value = pRes.msg || '商品不存在'
      return
    }
    product.value = pRes.data
    if (Number(product.value.number || 0) < qty.value) {
      error.value = '库存不足'
      return
    }
    if (aRes.status === 200) {
      addresses.value = aRes.data || []
      const def = addresses.value.find((a) => a.is_default) || addresses.value[0]
      addressId.value = def?.id || null
    }
    if (shopRes?.status === 200) {
      payGuide.value = shopRes.data?.pay_guide || ''
      hasPayQr.value = !!(shopRes.data?.has_pay_qr || shopRes.data?.pay_qr_wechat || shopRes.data?.pay_qr_alipay)
    }
    // 开发环境：仅当后端允许 mock 时才自动模拟支付
    allowDevMock.value = import.meta.env.DEV === true
    await refreshFreight()
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function saveAddress() {
  if (!form.contact_name || !form.contact_phone || !form.detail) {
    window.alert('请填写收货人、手机号和详细地址')
    return
  }
  savingAddr.value = true
  try {
    const res = await createAddress({
      contact_name: form.contact_name,
      contact_phone: form.contact_phone,
      region: form.region,
      detail: form.detail,
      is_default: addresses.value.length ? 0 : 1,
    })
    if (res.status !== 200) {
      window.alert(res.msg || '保存失败')
      return
    }
    addresses.value = [res.data, ...addresses.value]
    addressId.value = res.data.id
    form.contact_name = ''
    form.contact_phone = ''
    form.region = ''
    form.detail = ''
  } catch (e) {
    window.alert(e.message || '保存失败')
  } finally {
    savingAddr.value = false
  }
}

async function submit() {
  if (!product.value) return
  if (!addressId.value && !form.detail) {
    window.alert('请选择或填写收货地址')
    return
  }
  submitting.value = true
  try {
    let finalAddressId = addressId.value
    if (!finalAddressId && form.detail) {
      const res = await createAddress({
        contact_name: form.contact_name || '买家',
        contact_phone: form.contact_phone || '13900001111',
        region: form.region,
        detail: form.detail,
        is_default: 1,
      })
      if (res.status !== 200) throw new Error(res.msg || '地址保存失败')
      finalAddressId = res.data.id
    }

    if (!hasPayQr.value) {
      throw new Error('店主尚未上传收款码，无法提交订单')
    }
    const orderRes = await createOrder({
      address_id: finalAddressId,
      items: [{ pid: product.value.id, number: qty.value }],
      coupon_id: couponId.value,
    })
    if (orderRes.status !== 200) throw new Error(orderRes.msg || '下单失败')
    const order = orderRes.data
    router.replace({
      path: '/pay',
      query: {
        order_id: order.id,
        order_no: order.order_no,
        amount: order.price,
        name: product.value.name || '',
      },
    })
  } catch (e) {
    window.alert(e.message || '提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.back {
  border: none;
  background: transparent;
  color: var(--primary);
  font-size: 14px;
  padding: 0 0 8px;
  cursor: pointer;
}
.page-h {
  margin: 0 0 16px;
  font-size: 20px;
}
.layout {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 16px;
  align-items: start;
}
.main-col {
  display: grid;
  gap: 16px;
}
.card-h {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 12px;
}
.card-h.small {
  margin-top: 16px;
  font-size: 13px;
  color: var(--muted);
  font-weight: 500;
}
.pay-guide {
  margin: 12px 0 4px;
  text-align: left;
}
.guide-text {
  margin: 0;
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 12px;
  line-height: 1.55;
  color: #595959;
  background: #fffbe6;
  border: 1px dashed #ffd591;
  border-radius: 14px;
  padding: 10px;
  max-height: 140px;
  overflow: auto;
}
.addr-list {
  display: grid;
  gap: 10px;
}
.addr-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  border: 1px solid #eef0f4;
  border-radius: 14px;
  padding: 12px;
  cursor: pointer;
}
.addr-item.active {
  border-color: var(--primary);
  background: #f0f7ff;
}
.line1 {
  font-size: 14px;
  font-weight: 600;
}
.line2 {
  margin-top: 4px;
  font-size: 13px;
  color: var(--muted);
  line-height: 1.4;
}
.muted-box {
  font-size: 13px;
  color: var(--muted);
  padding: 4px 0 8px;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 10px;
}
.form-grid input {
  border: 1px solid #e5e6eb;
  border-radius: 14px;
  padding: 10px 12px;
  font-size: 14px;
}
.form-grid .full {
  grid-column: 1 / -1;
}
.goods .g-name {
  font-size: 15px;
  font-weight: 600;
}
.g-meta {
  margin-top: 10px;
  display: flex;
  justify-content: space-between;
  color: var(--muted);
  font-size: 13px;
}
.side-col .row {
  display: flex;
  justify-content: space-between;
  font-size: 14px;
  margin-bottom: 10px;
}
.side-col .strong {
  margin: 16px 0;
  font-weight: 600;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}
.price {
  color: var(--danger);
  font-size: 22px;
}
.submit {
  width: 100%;
  padding: 12px;
  font-size: 15px;
}
.tip {
  text-align: center;
  color: var(--muted);
  font-size: 12px;
  margin: 12px 0 0;
}
@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
  }
}

.pay-guide-card { margin-top: 12px; }
.pay-guide-text {
  white-space: pre-wrap;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.6;
  color: #134e4a;
  background: #f0fdfa;
  border-radius: 12px;
  padding: 12px;
  margin: 0 0 8px;
  border: 1px dashed #5eead4;
}
.pay-tip { margin: 0 0 4px; font-size: 12.5px; color: #5c564e; }
@media (max-width: 800px) {
  .layout { grid-template-columns: 1fr !important; }
  .side-col { position: static !important; }
}
.off { color:#c2410c; font-weight:700; }
.tip.err { color:#b91c1c; }
</style>
