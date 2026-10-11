<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="app-header-inner">
        <div class="left">
          <div class="brand" @click="$router.push('/')">
            <div class="mark" v-if="!shop.logo">{{ brandMark }}</div>
            <img v-else class="mark-img" :src="logoSrc" :alt="shop.name" />
            <div>
              <h1>{{ shop.name }}</h1>
              <p class="sub">{{ shop.tagline }}</p>
            </div>
          </div>
          <nav class="nav">
            <router-link to="/">首页</router-link>
            <router-link to="/cart">购物车</router-link>
            <router-link to="/orders">我的订单</router-link>
          </nav>
        </div>
        <div class="right">
          <a v-if="shop.contactPhone" class="link-btn phone" :href="'tel:' + shop.contactPhone">客服 {{ shop.contactPhone }}</a>
          <template v-if="customer">
            <span class="user">{{ displayName }}</span>
            <button class="link-btn" type="button" @click="onLogout">退出</button>
          </template>
          <router-link v-else class="link-btn primary" to="/login">登录</router-link>
        </div>
      </div>
    </header>

    <div class="trust-bar" v-if="shop.loaded && !shop.error">
      <div class="trust-inner">
        <span>正品保障</span>
        <span>{{ shortShip }}</span>
        <span>人工确认收款</span>
        <span>订单可追踪</span>
      </div>
    </div>

    <main class="app-main">
      <div v-if="!shop.open" class="closed-banner">店铺暂停营业，暂不可下单</div>
      <div v-if="shop.error" class="closed-banner danger">{{ shop.error }}</div>
      <router-view />
    </main>

    <footer class="app-footer">
      <div class="foot-inner">
        <div class="foot-brand">
          <strong>{{ shop.name }}</strong>
          <p>{{ shop.serviceNote }}</p>
        </div>
        <div class="foot-meta">
          <p v-if="shop.contactPhone">客服电话：{{ shop.contactPhone }}</p>
          <p>收款方式：商家确认到账后发货（非自动扣款）</p>
          <p class="muted">{{ shop.shippingNote }}</p>
          <div class="skin-switch">
            <span class="skin-label">店铺风格</span>
            <button
              v-for="s in skins"
              :key="s.id"
              type="button"
              class="skin-chip"
              :class="{ active: themeId === s.id }"
              :title="s.desc"
              @click="onSkin(s.id)"
            >{{ s.name }}</button>
          </div>
        </div>
      </div>
    </footer>

    <div v-if="route.path !== '/agent'" class="cs-float">
      <button v-if="!csOpen" type="button" class="cs-fab" @click="csOpen = true">导购客服</button>
      <div v-else class="cs-panel">
        <div class="cs-hd">
          <span>导购客服</span>
          <div class="cs-hd-actions">
            <button type="button" class="cs-expand" @click="goFullAgent">展开</button>
            <button type="button" @click="csOpen = false">×</button>
          </div>
        </div>
        <AgentPanel variant="compact" :show-head="false" @navigate="csOpen = false" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AgentPanel from '@/components/AgentPanel.vue'
import { clearAuth, getCustomer, getTenantSlug, setTenantSlug } from '@/utils/session'
import { trackAttribution } from '@/api'
import { loadShop, mediaUrl, shop } from '@/utils/shop'
import { applyTheme, getTheme, listSkins } from '@/utils/theme'

const router = useRouter()
const route = useRoute()
const customer = ref(getCustomer())
const displayName = computed(() => customer.value?.nickname || customer.value?.phone || '用户')
const brandMark = computed(() => String(shop.name || '店').slice(0, 1))
const logoSrc = computed(() => mediaUrl(shop.logo))
const skins = listSkins()
const themeId = ref(getTheme())
const csOpen = ref(false)

async function onSkin(id) {
  themeId.value = await applyTheme(id)
  shop.theme = themeId.value
}

const shortShip = computed(() => {
  const s = shop.shippingNote || ''
  return s.length > 16 ? '尽快发货' : s || '尽快发货'
})

function refreshAuth() {
  customer.value = getCustomer()
}
function onLogout() {
  clearAuth()
  customer.value = null
  router.push('/')
}
function goFullAgent() {
  csOpen.value = false
  router.push('/agent')
}

onMounted(async () => {
  const q = new URLSearchParams(window.location.search).get('tenant')
  if (q) setTenantSlug(q)
  else if (!getTenantSlug() || getTenantSlug() === 'demo-a') setTenantSlug('demo')
  const search = new URLSearchParams(window.location.search)
  const attribution = Object.fromEntries(['campaign_id', 'content_id', 'product_id', 'source', 'medium', 'visitor_id']
    .map((key) => [key, search.get(key)])
    .filter(([, value]) => value))
  if (attribution.campaign_id) {
    const visitorKey = 'growth_visitor_id'
    let visitorId = attribution.visitor_id || localStorage.getItem(visitorKey)
    if (!visitorId) {
      visitorId = globalThis.crypto?.randomUUID?.() || `visitor_${Date.now()}_${Math.random().toString(16).slice(2)}`
      localStorage.setItem(visitorKey, visitorId)
    }
    attribution.visitor_id = visitorId
    try { await trackAttribution(attribution) } catch (_) {}
  }
  await loadShop()
  window.addEventListener('mall:auth-change', refreshAuth)
})
onUnmounted(() => window.removeEventListener('mall:auth-change', refreshAuth))
</script>

<style>
.cs-float { position: fixed; right: 16px; bottom: 20px; z-index: 1200; }
.cs-fab { border:0; background:#0f766e; color:#fff; border-radius:999px; padding:12px 16px; font-weight:700; box-shadow:0 8px 24px rgba(15,118,110,.35); cursor:pointer; }
.cs-panel { width: min(360px, 92vw); height: 480px; background:#fff; border-radius:16px; box-shadow:0 12px 40px rgba(0,0,0,.18); display:flex; flex-direction:column; overflow:hidden; border:1px solid #e7e5e4; }
.cs-hd { display:flex; justify-content:space-between; align-items:center; padding:10px 12px; background:#0f766e; color:#fff; font-weight:700; flex-shrink:0; }
.cs-hd-actions { display:flex; align-items:center; gap:8px; }
.cs-hd button { border:0; background:transparent; color:#fff; font-size:18px; cursor:pointer; }
.cs-expand { font-size:13px !important; font-weight:700; padding:2px 8px; border:1px solid rgba(255,255,255,.4) !important; border-radius:999px; }
</style>
