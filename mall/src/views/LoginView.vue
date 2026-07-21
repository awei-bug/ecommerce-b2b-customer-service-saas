<template>
  <div class="page login-page">
    <div class="login-card page-card">
      <h2>登录商城</h2>
      <p class="desc">电脑端购物前请先登录（开发验证码默认 123456）</p>

      <label class="field">
        <span>手机号</span>
        <input v-model="phone" type="tel" maxlength="11" placeholder="11 位手机号" />
      </label>

      <label class="field">
        <span>验证码</span>
        <div class="code-row">
          <input v-model="code" type="text" maxlength="6" placeholder="验证码" />
          <button class="btn ghost" type="button" :disabled="sending || cooldown > 0" @click="onSend">
            {{ cooldown > 0 ? `${cooldown}s` : sending ? '发送中' : '获取验证码' }}
          </button>
        </div>
      </label>

      <label class="field">
        <span>昵称（可选）</span>
        <input v-model="nickname" type="text" maxlength="20" placeholder="如：小明" />
      </label>

      <p v-if="hint" class="hint">{{ hint }}</p>
      <p v-if="error" class="error">{{ error }}</p>

      <button class="btn primary block" type="button" :disabled="loading" @click="onLogin">
        {{ loading ? '登录中…' : '登 录' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { sendSmsCode, smsLogin } from '@/api'
import { saveAuth } from '@/utils/session'

const router = useRouter()
const route = useRoute()

const phone = ref('13900001111')
const code = ref('123456')
const nickname = ref('')
const loading = ref(false)
const sending = ref(false)
const error = ref('')
const hint = ref('')
const cooldown = ref(0)
let timer = null

function startCooldown(sec = 60) {
  cooldown.value = sec
  clearInterval(timer)
  timer = setInterval(() => {
    cooldown.value -= 1
    if (cooldown.value <= 0) clearInterval(timer)
  }, 1000)
}

async function onSend() {
  error.value = ''
  hint.value = ''
  sending.value = true
  try {
    const res = await sendSmsCode(phone.value)
    if (res.status !== 200) {
      error.value = res.msg || '发送失败'
      return
    }
    if (res.data?.dev_code) {
      code.value = res.data.dev_code
      hint.value = `开发模式验证码：${res.data.dev_code}`
    } else {
      hint.value = '验证码已发送'
    }
    startCooldown(60)
  } catch (e) {
    error.value = e.message || '发送失败'
  } finally {
    sending.value = false
  }
}

async function onLogin() {
  error.value = ''
  loading.value = true
  try {
    const res = await smsLogin({
      phone: phone.value,
      code: code.value,
      nickname: nickname.value || undefined,
    })
    if (res.status !== 200) {
      error.value = res.msg || '登录失败'
      return
    }
    saveAuth({
      token: res.data.token,
      customer: res.data.customer,
    })
    window.dispatchEvent(new CustomEvent('mall:auth-change'))
    const redirect = route.query.redirect || '/'
    router.replace(String(redirect))
  } catch (e) {
    error.value = e.message || '登录失败'
  } finally {
    loading.value = false
  }
}

onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.login-page {
  display: flex;
  justify-content: center;
  padding-top: 48px;
}
.login-card {
  width: 100%;
  max-width: 420px;
}
.login-card h2 {
  margin: 0 0 6px;
  font-size: 22px;
}
.desc {
  margin: 0 0 20px;
  color: var(--muted);
  font-size: 13px;
}
.field {
  display: grid;
  gap: 6px;
  margin-top: 14px;
  font-size: 13px;
  color: var(--muted);
}
.field input {
  border: 1px solid #e5e6eb;
  border-radius: 8px;
  padding: 11px 12px;
  font-size: 14px;
  color: var(--text);
}
.code-row {
  display: flex;
  gap: 8px;
}
.code-row input {
  flex: 1;
}
.btn.block {
  width: 100%;
  margin-top: 20px;
  padding: 12px;
  font-size: 15px;
}
.hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--primary);
}
.error {
  margin: 10px 0 0;
  font-size: 13px;
  color: var(--danger);
}
</style>
