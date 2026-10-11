<template>
  <div v-if="modelValue" class="mask" @click.self="close">
    <div class="dialog" role="dialog" aria-modal="true">
      <div class="dlg-head">
        <span class="dlg-title">订单确认</span>
        <button type="button" class="icon-btn" aria-label="关闭" @click="close">×</button>
      </div>

      <div class="goods">
        <div class="g-left">
          <div class="g-name">{{ product?.name }}</div>
          <div class="g-desc">{{ product?.introduce || '精选好物' }}</div>
          <div class="tags">
            <span class="tag green">确认收款后发货</span>
            <span class="tag blue">{{ minBuy }}件起购</span>
          </div>
        </div>
        <div class="g-right">x{{ qty }}</div>
      </div>

      <div class="field">
        <label><i>*</i>联系方式</label>
        <input
          v-model="phone"
          type="tel"
          maxlength="11"
          placeholder="请填写手机号"
          @input="onPhone"
        />
        <p class="field-tip">用于发货与售后联系</p>
        <p v-if="phoneErr" class="field-err">{{ phoneErr }}</p>
      </div>

      <div v-if="needLogin" class="field">
        <label><i>*</i>短信验证码</label>
        <div class="sms-row">
          <input v-model="code" maxlength="8" placeholder="未登录时需验证码后下单" />
          <button type="button" class="sms-btn" :disabled="sending || cooldown > 0" @click="sendCode">
            {{ cooldown > 0 ? (cooldown + 's') : (sending ? '发送中' : '获取验证码') }}
          </button>
        </div>
        <p v-if="smsHint" class="field-tip">{{ smsHint }}</p>
        <p v-if="smsErr" class="field-err">{{ smsErr }}</p>
      </div>

      <div class="field">
        <label>收货地址</label>
        <input
          v-model="addressDetail"
          type="text"
          maxlength="120"
          placeholder="省市区 + 详细地址（选填，虚拟商品可写「无需快递」）"
        />
      </div>

      <div class="field">
        <label>订单备注</label>
        <input
          v-model="note"
          type="text"
          maxlength="80"
          placeholder="选填，如颜色、尺码偏好"
        />
      </div>

      <div class="price-row">
        <div class="price">¥{{ formatPrice(lineTotal) }}</div>
        <div class="qty">
          <button type="button" :disabled="qty <= 1" @click="dec">−</button>
          <input v-model.number="qtyLocal" type="number" min="1" :max="maxQty" @change="clampQty" />
          <button type="button" :disabled="qty >= maxQty" @click="inc">+</button>
        </div>
      </div>

      <div class="quote">
        <div class="q-row"><span>商品</span><span>¥{{ formatPrice(lineTotal) }}</span></div>
        <div class="q-row"><span>运费{{ freightName ? `（${freightName}）` : '' }}</span><span>{{ Number(freightAmount||0) > 0 ? ('¥'+formatPrice(freightAmount)) : '包邮' }}</span></div>
        <div v-if="Number(discountAmount||0) > 0" class="q-row off"><span>{{ couponLabel || '优惠' }}</span><span>-¥{{ formatPrice(discountAmount) }}</span></div>
        <div class="q-row pay"><span>应付</span><span>¥{{ formatPrice(payAmount) }}</span></div>
      </div>

      <div class="pay-method">
        <button type="button" class="method active">
          <span class="wx-icon">微</span>
          微信支付
        </button>
        <p v-if="!hasPayQr" class="pay-tip err">店主尚未上传收款码，暂时不能在线扫码。请联系店主后再下单。</p>
        <p v-else class="pay-tip">点击「去支付」后将生成订单并展示收款码；请备注订单号。</p>
      </div>

      <div class="footer">
        <button type="button" class="link" @click="close">取消</button>
        <button type="button" class="go" :disabled="submitting || !hasPayQr" @click="goPay">
          {{ !hasPayQr ? '暂不可支付' : (submitting ? '提交中…' : '去支付') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { sendSmsCode } from '@/api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  product: { type: Object, default: null },
  qty: { type: Number, default: 1 },
  submitting: { type: Boolean, default: false },
  defaultPhone: { type: String, default: '' },
  needLogin: { type: Boolean, default: false },
  freightAmount: { type: Number, default: 0 },
  freightName: { type: String, default: '' },
  discountAmount: { type: Number, default: 0 },
  couponLabel: { type: String, default: '' },
  hasPayQr: { type: Boolean, default: true },
})
const emit = defineEmits(['update:modelValue', 'update:qty', 'confirm', 'cancel'])

const phone = ref('')
const phoneErr = ref('')
const addressDetail = ref('')
const note = ref('')
const qtyLocal = ref(1)
const code = ref('')
const sending = ref(false)
const cooldown = ref(0)
const smsHint = ref('')
const smsErr = ref('')
let timer = null

const maxQty = computed(() => Math.max(1, Number(props.product?.number || 1)))
const minBuy = computed(() => 1)
const lineTotal = computed(() => Number(props.product?.price || 0) * Number(props.qty || 1))
const payAmount = computed(() => {
  const goods = Number(lineTotal.value || 0)
  const freight = Number(props.freightAmount || 0)
  const off = Number(props.discountAmount || 0)
  const n = goods + freight - off
  return n > 0 ? n : 0
})

watch(
  () => props.modelValue,
  (v) => {
    if (v) {
      phone.value = String(props.defaultPhone || '').replace(/\D/g, '').slice(0, 11)
      phoneErr.value = ''
      addressDetail.value = ''
      note.value = ''
      qtyLocal.value = props.qty
      code.value = ''
      smsHint.value = ''
      smsErr.value = ''
    }
  },
)
watch(
  () => props.qty,
  (v) => { qtyLocal.value = v },
)

function formatPrice(n) {
  return Number(n || 0).toFixed(2)
}
function close() {
  emit('update:modelValue', false)
  emit('cancel')
}
function onPhone(e) {
  phone.value = String(e?.target?.value || phone.value).replace(/\D/g, '').slice(0, 11)
  phoneErr.value = ''
}
function dec() {
  const n = Math.max(1, Number(props.qty || 1) - 1)
  emit('update:qty', n)
}
function inc() {
  const n = Math.min(maxQty.value, Number(props.qty || 1) + 1)
  emit('update:qty', n)
}
function clampQty() {
  let n = Number(qtyLocal.value || 1)
  if (!Number.isFinite(n) || n < 1) n = 1
  if (n > maxQty.value) n = maxQty.value
  qtyLocal.value = n
  emit('update:qty', n)
}
async function sendCode() {
  smsErr.value = ''
  smsHint.value = ''
  const p = String(phone.value || '').trim()
  if (!/^1[3-9]\d{9}$/.test(p)) {
    phoneErr.value = '请先填写正确的 11 位手机号'
    return
  }
  sending.value = true
  try {
    const res = await sendSmsCode(p)
    if (!res || res.status !== 200) {
      smsErr.value = (res && res.msg) || '发送失败'
      return
    }
    const d = res.data || {}
    cooldown.value = Math.max(1, Number(d.cooldown || 10))
    clearInterval(timer)
    timer = setInterval(() => {
      cooldown.value -= 1
      if (cooldown.value <= 0) clearInterval(timer)
    }, 1000)
    if (d.dev_code) {
      code.value = String(d.dev_code)
      smsHint.value = `验证码已填入：${d.dev_code}`
    } else {
      smsHint.value = res.msg || '验证码已发送'
    }
  } catch (e) {
    smsErr.value = e.message || '发送失败'
  } finally {
    sending.value = false
  }
}
function goPay() {
  if (!props.hasPayQr) {
    phoneErr.value = '店主未上传收款码，无法下单支付'
    return
  }
  const p = String(phone.value || '').trim()
  if (!/^1[3-9]\d{9}$/.test(p)) {
    phoneErr.value = '请填写正确的 11 位手机号'
    return
  }
  if (props.needLogin && !String(code.value || '').trim()) {
    smsErr.value = '请先获取并填写验证码'
    return
  }
  emit('confirm', {
    phone: p,
    qty: Number(props.qty || 1),
    address: String(addressDetail.value || '').trim(),
    note: String(note.value || '').trim(),
    code: String(code.value || '').trim(),
  })
}
</script>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(15, 23, 42, 0.45);
  display: grid;
  place-items: center;
  padding: 16px;
}
.dialog {
  width: min(420px, 100%);
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.18);
  padding: 18px 18px 14px;
}
.dlg-head {
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  margin-bottom: 16px;
}
.dlg-title {
  font-size: 16px;
  font-weight: 700;
  color: #1f2937;
}
.icon-btn {
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  border: 0;
  background: transparent;
  font-size: 22px;
  line-height: 1;
  color: #9ca3af;
  cursor: pointer;
  width: 32px;
  height: 32px;
}
.goods {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 1px solid #f3f4f6;
}
.g-name {
  font-size: 15px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 6px;
}
.g-desc {
  font-size: 13px;
  color: #6b7280;
  line-height: 1.45;
  margin-bottom: 8px;
}
.tags { display: flex; flex-wrap: wrap; gap: 6px; }
.tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 600;
}
.tag.green { background: #ecfdf5; color: #059669; }
.tag.blue { background: #eff6ff; color: #2563eb; }
.g-right {
  color: #9ca3af;
  font-size: 14px;
  flex-shrink: 0;
}
.field {
  margin-top: 16px;
}
.field label {
  display: block;
  font-size: 13px;
  color: #374151;
  margin-bottom: 8px;
  font-weight: 600;
}
.field label i {
  color: #ef4444;
  font-style: normal;
  margin-right: 2px;
}
.field input {
  width: 100%;
  height: 40px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 0 12px;
  background: #f9fafb;
  outline: none;
  box-sizing: border-box;
}
.field input:focus {
  border-color: #93c5fd;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
}
.field-tip {
  margin: 6px 0 0;
  font-size: 12px;
  color: #9ca3af;
}
.field-err {
  margin: 6px 0 0;
  font-size: 12px;
  color: #dc2626;
}
.price-row {
  margin-top: 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.price {
  font-size: 28px;
  font-weight: 800;
  color: #2563eb;
  font-variant-numeric: tabular-nums;
}
.qty {
  display: inline-flex;
  align-items: center;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}
.qty button {
  width: 34px;
  height: 34px;
  border: 0;
  background: #f9fafb;
  color: #374151;
  cursor: pointer;
  font-size: 16px;
}
.qty button:disabled {
  color: #d1d5db;
  cursor: not-allowed;
}
.qty input {
  width: 42px;
  height: 34px;
  border: 0;
  border-left: 1px solid #e5e7eb;
  border-right: 1px solid #e5e7eb;
  text-align: center;
  outline: none;
  font-size: 14px;
}
/* hide number spinners */
.qty input::-webkit-outer-spin-button,
.qty input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.qty input[type='number'] {
  -moz-appearance: textfield;
  appearance: textfield;
}
.pay-method {
  margin-top: 18px;
}
.method {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 16px;
  border-radius: 10px;
  border: 1.5px solid #3b82f6;
  background: #fff;
  color: #1d4ed8;
  font-weight: 700;
  font-size: 14px;
  cursor: default;
}
.wx-icon {
  display: inline-grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #07c160;
  color: #fff;
  font-size: 10px;
  font-weight: 800;
}
.footer {
  margin-top: 22px;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 16px;
}
.link {
  border: 0;
  background: transparent;
  color: #3b82f6;
  font-size: 14px;
  cursor: pointer;
  padding: 8px 4px;
}
.go {
  min-width: 96px;
  height: 40px;
  border: 0;
  border-radius: 10px;
  background: #3b82f6;
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  padding: 0 18px;
}
.go:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
.go:active {
  transform: scale(0.98);
}
.pay-tip { margin: 8px 0 0; font-size: 12px; color: #9ca3af; line-height: 1.4; }

.sms-row { display:flex; gap:8px; }
.sms-row input { flex:1; }
.sms-btn {
  flex-shrink:0; height:40px; padding:0 10px; border:1px solid #dbeafe;
  background:#eff6ff; color:#1d4ed8; border-radius:10px; font-size:12px; font-weight:700; cursor:pointer;
}
.sms-btn:disabled { opacity:.6; cursor:not-allowed; }

.quote { margin-top: 16px; border-top: 1px dashed #e7e5e4; padding-top: 12px; }
.q-row { display:flex; justify-content:space-between; font-size:13px; color:#57534e; margin:6px 0; }
.q-row.off { color:#c2410c; }
.q-row.pay { font-size:16px; font-weight:800; color:#1c1917; }
.pay-tip.err { color:#b91c1c; font-weight:700; }
</style>
