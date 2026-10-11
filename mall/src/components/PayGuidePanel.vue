<template>
  <section class="pay" :class="{ compact }">
    <!-- 金额突出 -->
    <div v-if="hasAmount" class="amount-block">
      <div class="amount-label">应付金额</div>
      <div class="amount-value"><em>¥</em>{{ formatPrice(amount) }}</div>
    </div>

    <!-- 三步 -->
    <ol class="steps">
      <li>
        <span class="n">1</span>
        <div>
          <b>复制订单号</b>
          <div v-if="orderNo" class="order-line">
            <code>{{ orderNo }}</code>
            <button type="button" class="copy-btn" @click="copy(orderNo)">{{ copied ? '已复制' : '复制' }}</button>
          </div>
          <div v-else class="hint">下单后在本页可复制订单号</div>
        </div>
      </li>
      <li>
        <span class="n">2</span>
        <div>
          <b>微信扫码付款</b>
          <div class="hint">打开微信「扫一扫」，扫描下方收款码</div>
        </div>
      </li>
      <li>
        <span class="n">3</span>
        <div>
          <b>备注里粘贴订单号</b>
          <div class="hint">方便店主核对，确认后安排发货</div>
        </div>
      </li>
    </ol>

    <!-- 收款码：尽量像微信原生展示 -->
    <div v-if="wechatSrc || alipaySrc" class="qr-wrap">
      <div v-if="wechatSrc" class="qr-main">
        <img :src="wechatSrc" alt="微信收款码" class="qr-img" />
      </div>
      <div v-if="alipaySrc" class="qr-side">
        <div class="side-label">支付宝也可以</div>
        <img :src="alipaySrc" alt="支付宝收款码" class="qr-img sm" />
      </div>
    </div>
    <div v-else class="qr-missing">
      店主还没设置收款码，请先联系店主完成付款。
      <span v-if="phone">电话：{{ phone }}</span>
    </div>

    <div class="foot-tips">
      <p>付款后请稍等，店主确认到账会更新订单状态。</p>
      <p v-if="phone">客服：<a :href="'tel:' + phone">{{ phone }}</a></p>
      <p class="muted">熟人店收款方式：扫码转账（非自动扣款）</p>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { mediaUrl, shop } from '@/utils/shop'

const props = defineProps({
  orderNo: { type: String, default: '' },
  amount: { type: [String, Number], default: '' },
  title: { type: String, default: '' }, // 保留兼容，不再强依赖
  compact: { type: Boolean, default: false },
  guideOverride: { type: String, default: '' },
})

const copied = ref(false)
const phone = computed(() => shop.contactPhone || '')
const wechatSrc = computed(() => mediaUrl(shop.payQrWechat))
const alipaySrc = computed(() => mediaUrl(shop.payQrAlipay))
const hasAmount = computed(() => props.amount !== '' && props.amount != null && props.amount !== undefined)

function formatPrice(n) {
  return Number(n || 0).toFixed(2)
}
async function copy(text) {
  try {
    await navigator.clipboard.writeText(String(text || ''))
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    window.prompt('请复制订单号，付款时粘贴到备注', String(text || ''))
  }
}
</script>

<style scoped>
.pay {
  text-align: left;
  background: #fff;
  border-radius: 16px;
  border: 1px solid #e8e0d4;
  padding: 18px 16px 14px;
}
.pay.compact { padding: 14px 12px; }

.amount-block {
  text-align: center;
  padding: 8px 0 14px;
  border-bottom: 1px solid #f0ebe3;
  margin-bottom: 14px;
}
.amount-label {
  font-size: 13px;
  color: #8a8278;
  margin-bottom: 4px;
}
.amount-value {
  font-size: 36px;
  font-weight: 800;
  color: #c2410c;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}
.amount-value em {
  font-style: normal;
  font-size: 20px;
  margin-right: 2px;
  font-weight: 700;
}

.steps {
  list-style: none;
  margin: 0 0 16px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.steps li {
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: 10px;
  align-items: start;
}
.steps .n {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #07c160;
  color: #fff;
  font-size: 14px;
  font-weight: 800;
  display: grid;
  place-items: center;
}
.steps b {
  display: block;
  font-size: 14px;
  color: #1c1917;
  margin-bottom: 4px;
}
.hint {
  font-size: 12.5px;
  color: #8a8278;
  line-height: 1.4;
}
.order-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 4px;
}
.order-line code {
  font-size: 12.5px;
  background: #f5f2ec;
  padding: 4px 8px;
  border-radius: 8px;
  word-break: break-all;
  color: #44403c;
}
.copy-btn {
  border: none;
  background: #07c160;
  color: #fff;
  font-size: 12.5px;
  font-weight: 700;
  padding: 6px 12px;
  border-radius: 999px;
  cursor: pointer;
}
.copy-btn:active { transform: scale(0.98); }

.qr-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 8px 0 4px;
}
.qr-main {
  width: min(300px, 100%);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.08);
  background: #07c160;
}
.qr-img {
  display: block;
  width: 100%;
  height: auto;
  vertical-align: top;
}
.qr-img.sm {
  width: 140px;
  margin: 0 auto;
  border-radius: 8px;
  border: 1px solid #eee;
}
.qr-side {
  text-align: center;
}
.side-label {
  font-size: 12px;
  color: #8a8278;
  margin-bottom: 6px;
}
.qr-missing {
  margin: 8px 0;
  padding: 12px;
  border-radius: 12px;
  background: #fff7ed;
  color: #9a3412;
  font-size: 13px;
  line-height: 1.5;
  text-align: center;
}
.foot-tips {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #f0ebe3;
  font-size: 13px;
  color: #57534e;
  line-height: 1.55;
  text-align: center;
}
.foot-tips p { margin: 0 0 4px; }
.foot-tips a { color: #07c160; font-weight: 700; text-decoration: none; }
.muted { color: #a8a29e !important; font-size: 12px !important; }
</style>
