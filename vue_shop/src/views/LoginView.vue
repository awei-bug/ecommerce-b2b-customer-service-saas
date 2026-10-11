<template>
  <div class="login-page">
    <div class="glow a"></div>
    <div class="glow b"></div>
    <div class="login-shell">
      <section class="login-left">
        <div class="brand">
          <div class="logo">购</div>
          <div>
            <div class="kicker">YUNGOU MERCHANT</div>
            <h1>云购商城</h1>
            <p>把上架、接单、发货、对账放在一个安静好用的工作台里。</p>
          </div>
        </div>
        <ul class="features">
          <li>
            <span class="dot"></span>
            <div>
              <strong>经营首页</strong>
              <p>今日成交、待发货、售后一目了然</p>
            </div>
          </li>
          <li>
            <span class="dot"></span>
            <div>
              <strong>商品与 SKU</strong>
              <p>分类、库存、运费模板统一管理</p>
            </div>
          </li>
          <li>
            <span class="dot"></span>
            <div>
              <strong>订单履约</strong>
              <p>确认收款、发货轨迹、售后闭环</p>
            </div>
          </li>
        </ul>
        <p class="hint">演示账号 · 团队 demo / admin / 123456</p>
      </section>

      <section class="login-right">
        <div class="login-panel">
          <h2>登录后台</h2>
          <p class="panel-sub">使用店铺员工账号进入管理台</p>
          <el-form :model="form" size="large" label-position="top" @keyup.enter="onLogin">
            <el-form-item label="团队标识">
              <el-input v-model="form.tenant_slug" placeholder="demo" clearable />
            </el-form-item>
            <el-form-item label="账号">
              <el-input v-model="form.name" placeholder="admin" clearable />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="form.pwd" type="password" show-password placeholder="密码" />
            </el-form-item>
            <el-button type="primary" class="submit" :loading="loading" @click="onLogin">进入工作台</el-button>
          </el-form>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/api/index.js'
import { setAuth } from '@/utils/permission.js'

const router = useRouter()
const loading = ref(false)
const form = reactive({ tenant_slug: 'demo', name: 'admin', pwd: '123456' })

async function onLogin() {
  if (!form.name || !form.pwd) {
    ElMessage.warning('请输入账号密码')
    return
  }
  loading.value = true
  try {
    const res = await api.login(form)
    const body = res.data
    if (body.status !== 200) {
      ElMessage.error(body.msg || '登录失败')
      return
    }
    setAuth(body.data)
    try {
      if (body.data?.password_is_default) sessionStorage.setItem('password_is_default', '1')
      else sessionStorage.removeItem('password_is_default')
    } catch (_) {}
    if (body.data?.password_is_default) {
      ElMessage.warning('当前为默认密码，请尽快到店铺设置修改')
    } else {
      ElMessage.success('登录成功')
    }
    router.push('/data_list')
  } catch (e) {
    ElMessage.error('网络错误')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 32px 20px;
  background:
    radial-gradient(900px 500px at 10% 0%, rgba(15, 118, 110, 0.22), transparent 55%),
    radial-gradient(700px 420px at 90% 100%, rgba(194, 65, 12, 0.12), transparent 50%),
    linear-gradient(165deg, #0f0e0c 0%, #1a1714 48%, #12100e 100%);
  position: relative;
  overflow: hidden;
  font-family: var(--font);
}
.glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(40px);
  opacity: 0.45;
  pointer-events: none;
}
.glow.a {
  width: 280px; height: 280px; left: -40px; top: 18%;
  background: #0f766e;
  animation: admin-float 8s ease-in-out infinite, admin-glow 5s ease-in-out infinite;
}
.glow.b {
  width: 220px; height: 220px; right: 8%; bottom: 12%;
  background: #b45309;
  animation: admin-float 10s ease-in-out infinite reverse, admin-glow 6s ease-in-out infinite;
}
.login-shell {
  animation: admin-rise .55s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.logo {
  animation: admin-float 5.5s ease-in-out infinite;
}
.login-shell {
  width: min(1040px, 100%);
  display: grid;
  grid-template-columns: 1.15fr 0.95fr;
  gap: 0;
  border-radius: 24px;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,252,247,0.03);
  box-shadow: 0 30px 80px rgba(0,0,0,0.35);
  position: relative;
  z-index: 1;
}
.login-left {
  color: #fffcf7;
  padding: 48px 44px;
  background:
    linear-gradient(160deg, rgba(15,118,110,0.18), transparent 42%),
    rgba(0,0,0,0.18);
}
.brand {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 36px;
}
.logo {
  width: 52px;
  height: 52px;
  border-radius: 16px;
  background: linear-gradient(145deg, #2dd4bf, #0f766e);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 20px;
  color: #042f2e;
  flex-shrink: 0;
}
.kicker {
  font-size: 11px;
  letter-spacing: 0.14em;
  color: rgba(255,252,247,0.5);
  margin-bottom: 8px;
}
.brand h1 {
  margin: 0;
  font-size: 34px;
  letter-spacing: -0.03em;
  font-weight: 700;
}
.brand p {
  margin: 10px 0 0;
  color: rgba(255,252,247,0.72);
  line-height: 1.6;
  max-width: 34ch;
  font-size: 14px;
}
.features {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 16px;
}
.features li {
  display: grid;
  grid-template-columns: 12px 1fr;
  gap: 12px;
  align-items: start;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 7px;
  background: #2dd4bf;
  box-shadow: 0 0 0 4px rgba(45, 212, 191, 0.15);
}
.features strong {
  display: block;
  font-size: 14px;
  margin-bottom: 4px;
}
.features p {
  margin: 0;
  color: rgba(255,252,247,0.55);
  font-size: 13px;
  line-height: 1.5;
}
.hint {
  margin-top: 36px;
  font-size: 12px;
  color: rgba(255,252,247,0.42);
}
.login-right {
  background: #fffcf7;
  padding: 40px 36px;
  display: flex;
  align-items: center;
}
.login-panel { width: 100%; }
.login-panel h2 {
  margin: 0;
  font-size: 24px;
  letter-spacing: -0.02em;
  color: #14120f;
}
.panel-sub {
  margin: 8px 0 24px;
  color: #8a8478;
  font-size: 13px;
}
.submit {
  width: 100%;
  height: 44px;
  margin-top: 8px;
  font-weight: 600;
  border-radius: 12px !important;
}
@media (max-width: 900px) {
  .login-shell { grid-template-columns: 1fr; }
  .login-left { padding: 32px 28px 24px; }
  .login-right { padding: 28px 24px 32px; }
}

@keyframes admin-float {
  0%, 100% { transform: translate3d(0,0,0); }
  50% { transform: translate3d(0,-12px,0); }
}
@keyframes admin-glow {
  0%, 100% { opacity: .4; }
  50% { opacity: .75; }
}
@keyframes admin-rise {
  from { opacity: 0; transform: translateY(16px) scale(.985); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
</style>

