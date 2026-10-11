<template>
  <div class="login-page">
    <div class="login-card">
      <div class="head">
        <div class="mark">购</div>
        <div>
          <h2>手机号登录</h2>
          <p class="desc">输入手机号获取验证码，登录后可下单</p>
        </div>
      </div>

      <div class="mode-banner">
        点击「获取验证码」后，若系统处于联调模式，验证码会显示在下方收件区（生产环境将发送至手机短信）。
      </div>

      <label class="field">
        <span>手机号 <em class="req">必填</em></span>
        <input
          v-model="phone"
          type="tel"
          inputmode="numeric"
          maxlength="11"
          placeholder="11 位，如 13800138000"
          autocomplete="tel"
          @input="onPhoneInput"
          @keyup.enter="onSend"
        />
        <p v-if="phone && !phoneValid" class="field-tip warn">请输入正确的 11 位大陆手机号（1 开头第二位 3–9）</p>
        <p v-else class="field-tip">先填手机号，再点右侧「获取验证码」</p>
      </label>

      <label class="field">
        <span>验证码 <em class="req">必填</em></span>
        <div class="code-row">
          <input
            v-model="code"
            type="text"
            inputmode="numeric"
            maxlength="6"
            placeholder="6 位验证码"
            @keyup.enter="onLogin"
          />
          <button
            class="btn ghost"
            type="button"
            :disabled="sending || cooldown > 0"
            :title="sendTitle"
            @click="onSend"
          >
            {{ sendLabel }}
          </button>
        </div>
      </label>

      <label class="field">
        <span>昵称（可选，可先不填）</span>
        <input v-model="nickname" type="text" maxlength="20" placeholder="如：小明" />
      </label>

      <div v-if="mockSms" class="sms-box">
        <div class="sms-title">验证码消息</div>
        <div class="sms-body">{{ mockSms }}</div>
        <div v-if="lastDevCode" class="sms-code">验证码：<strong>{{ lastDevCode }}</strong></div>
        <button class="btn primary mini" type="button" @click="fillFromSms">使用此验证码</button>
      </div>

      <p v-if="hint" class="hint">{{ hint }}</p>
      <p v-if="error" class="error">{{ error }}</p>

      <button class="btn primary block" type="button" :disabled="loading" @click="onLogin">
        {{ loading ? '登录中…' : '登录' }}
      </button>

      <p class="foot">
        未注册手机号将自动创建账号 · 验证码 10 分钟内有效<br />
        昵称可登录时再填，不影响获取验证码
      </p>
    </div>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { sendSmsCode, smsLogin } from '@/api'
import { saveAuth } from '@/utils/session'

const router = useRouter()
const route = useRoute()

const phone = ref('')
const code = ref('')
const nickname = ref('')
const loading = ref(false)
const sending = ref(false)
const error = ref('')
const hint = ref('')
const mockSms = ref('')
const lastDevCode = ref('')
const cooldown = ref(0)
let timer = null

const phoneValid = computed(() => /^1[3-9]\d{9}$/.test(String(phone.value || '').trim()))
const canLogin = computed(
  () => phoneValid.value && String(code.value || '').trim().length >= 4,
)

const sendLabel = computed(() => {
  if (cooldown.value > 0) return `${cooldown.value}s 后重发`
  if (sending.value) return '发送中…'
  return '获取验证码'
})

const sendTitle = computed(() => {
  if (!phoneValid.value) return '请先输入正确的 11 位手机号'
  if (cooldown.value > 0) return '冷却中，请稍后再试'
  return '点击获取验证码'
})

function onPhoneInput(e) {
  // 只保留数字，去掉空格/横线
  const digits = String(e?.target?.value ?? phone.value).replace(/\D/g, '').slice(0, 11)
  phone.value = digits
  if (error.value && phoneValid.value) error.value = ''
}

function startCooldown(sec = 10) {
  cooldown.value = Math.max(1, Number(sec) || 10)
  clearInterval(timer)
  timer = setInterval(() => {
    cooldown.value -= 1
    if (cooldown.value <= 0) clearInterval(timer)
  }, 1000)
}

function fillFromSms() {
  if (lastDevCode.value) {
    code.value = lastDevCode.value
    hint.value = '已填入验证码，可点击登录'
    error.value = ''
  }
}

async function onSend() {
  error.value = ''
  hint.value = ''
  onPhoneInput({ target: { value: phone.value } })
  if (!phoneValid.value) {
    error.value = '请先输入正确的 11 位手机号（示例：13800138000），昵称可先不填'
    return
  }
  sending.value = true
  try {
    const res = await sendSmsCode(String(phone.value).trim())
    if (!res || res.status !== 200) {
      error.value = (res && res.msg) || '发送失败'
      return
    }
    const d = res.data || {}
    const wait = Number(d.cooldown || 10)
    startCooldown(wait)

    if (d.dev_code) {
      lastDevCode.value = String(d.dev_code)
      mockSms.value =
        d.mock_sms || `【云购商城】您的登录验证码是 ${d.dev_code}，10分钟内有效。`
      code.value = String(d.dev_code)
      hint.value = d.reused
        ? `冷却期内复用验证码：${d.dev_code}`
        : `验证码已生成：${d.dev_code}（已自动填入，可直接点登录）`
    } else {
      mockSms.value = ''
      lastDevCode.value = ''
      hint.value = res.msg || '验证码已发送，请查收手机短信'
    }
  } catch (e) {
    error.value =
      e?.message ||
      '发送失败：请确认后端 http://127.0.0.1:5000 已启动，且本页通过 Vite 代理访问'
  } finally {
    sending.value = false
  }
}

async function onLogin() {
  error.value = ''
  onPhoneInput({ target: { value: phone.value } })
  if (!phoneValid.value) {
    error.value = '请输入正确的 11 位手机号'
    return
  }
  if (!String(code.value || '').trim()) {
    error.value = '请先点击「获取验证码」，并把验证码填入（开发模式会显示在模拟短信里）'
    return
  }
  loading.value = true
  try {
    const res = await smsLogin({
      phone: String(phone.value).trim(),
      code: String(code.value).trim(),
      nickname: String(nickname.value || '').trim() || undefined,
    })
    if (!res || res.status !== 200) {
      error.value = (res && res.msg) || '登录失败'
      return
    }
    const d = res.data || {}
    saveAuth({ token: d.token, customer: d.customer })
    window.dispatchEvent(new Event('mall:auth-change'))
    const redirect = route.query.redirect ? String(route.query.redirect) : '/'
    router.replace(redirect)
  } catch (e) {
    error.value = e?.message || '登录失败'
  } finally {
    loading.value = false
  }
}

onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.login-page {
  min-height: calc(100vh - 140px);
  display: grid;
  place-items: center;
  padding: 24px 16px 48px;
}
.login-card {
  width: min(440px, 100%);
  background: #fffdf8;
  border: 1px solid #e8e0d4;
  border-radius: 20px;
  padding: 28px 24px 22px;
  box-shadow: 0 18px 50px rgba(40, 30, 20, 0.08);
}
.head {
  display: flex;
  gap: 14px;
  align-items: center;
  margin-bottom: 16px;
}
.mark {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background: linear-gradient(145deg, #0f766e, #115e59);
  color: #ecfdf5;
  font-weight: 800;
  font-size: 20px;
}
.head h2 {
  margin: 0 0 4px;
  font-size: 22px;
  color: #1a1714;
}
.desc {
  margin: 0;
  color: #8a8278;
  font-size: 13px;
}
.mode-banner {
  margin-bottom: 16px;
  padding: 10px 12px;
  border-radius: 12px;
  background: #fff7ed;
  border: 1px solid #fed7aa;
  color: #9a3412;
  font-size: 12.5px;
  line-height: 1.5;
}
.field {
  display: block;
  margin-bottom: 12px;
}
.field > span {
  display: block;
  font-size: 12.5px;
  color: #5c564e;
  margin-bottom: 6px;
  font-weight: 600;
}
.req {
  color: #b45309;
  font-style: normal;
  font-weight: 700;
  margin-left: 4px;
}
.field input {
  width: 100%;
  height: 44px;
  border-radius: 12px;
  border: 1px solid #e4ddd1;
  padding: 0 14px;
  background: #fff;
  outline: none;
  font-weight: 400;
  color: #1a1714;
  box-sizing: border-box;
}
.field input:focus {
  border-color: #0f766e;
  box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.12);
}
.field-tip {
  margin: 6px 0 0;
  font-size: 12px;
  color: #8a8278;
}
.field-tip.warn {
  color: #b45309;
}
.code-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
}
.sms-box {
  margin: 4px 0 14px;
  border-radius: 14px;
  border: 1px dashed #0f766e;
  background: #f0fdfa;
  padding: 12px 14px;
}
.sms-title {
  font-size: 12px;
  font-weight: 700;
  color: #0f766e;
  margin-bottom: 6px;
}
.sms-body {
  font-size: 14px;
  color: #134e4a;
  line-height: 1.55;
  margin-bottom: 8px;
  word-break: break-all;
}
.sms-code {
  margin-bottom: 10px;
  font-size: 15px;
  color: #0f766e;
}
.btn.mini {
  padding: 8px 12px;
  font-size: 13px;
  width: auto;
}
.hint {
  margin: 0 0 8px;
  color: #0f766e;
  font-size: 12.5px;
  background: #ecfdf5;
  padding: 8px 10px;
  border-radius: 10px;
}
.error {
  margin: 0 0 8px;
  color: #b91c1c;
  font-size: 13px;
  background: #fef2f2;
  padding: 8px 10px;
  border-radius: 10px;
}
.foot {
  margin: 14px 0 0;
  text-align: center;
  color: #8a8278;
  font-size: 12px;
  line-height: 1.55;
}
.btn.block {
  width: 100%;
  margin-top: 4px;
}
.btn.ghost:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
</style>
