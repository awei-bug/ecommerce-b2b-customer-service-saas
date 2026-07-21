<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="app-header-inner">
        <div class="left">
          <div class="brand" @click="$router.push('/')">
            <div class="mark">店</div>
            <div>
              <h1>{{ shopName }}</h1>
              <p class="sub">电脑端商城 · 选购下单</p>
            </div>
          </div>
          <nav class="nav">
            <router-link to="/">{{ t('navHome') }}</router-link>
            <router-link to="/track">{{ t('navTrack') }}</router-link>
            <router-link to="/orders">{{ t('navOrders') }}</router-link>
          </nav>
        </div>
        <div class="right">
          <div class="lang-switch" role="group">
            <button
              type="button"
              class="lang-btn"
              :class="{ active: locale === 'zh' }"
              @click="switchLang('zh')"
            >中文</button>
            <button
              type="button"
              class="lang-btn"
              :class="{ active: locale === 'en' }"
              @click="switchLang('en')"
            >EN</button>
          </div>
          <template v-if="customer">
            <span class="user">{{ displayName }}</span>
            <button class="link-btn" type="button" @click="onLogout">{{ t('navLogout') }}</button>
          </template>
          <template v-else>
            <router-link class="link-btn primary" to="/login">{{ t('navLogin') }}</router-link>
          </template>
        </div>
      </div>
    </header>

    <main class="app-main">
      <div v-if="!shopOpen" class="closed-banner">
        {{ t('shopClosed') }}
        <span v-if="contactPhone"> · {{ t('contact') }} {{ contactPhone }}</span>
      </div>
      <router-view />
    </main>

    <footer class="app-footer">
      {{ shopName }}
      <span v-if="contactPhone"> · {{ contactPhone }}</span>
      · {{ t('footerDemo') }}
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getShop } from '@/api'
import { clearAuth, getCustomer, getTenantSlug } from '@/utils/session'
import { getLocale, setLocale, t as tr } from '@/utils/i18n'

const router = useRouter()
const shopName = ref('商城')
const shopOpen = ref(true)
const contactPhone = ref('')
const customer = ref(getCustomer())
const locale = ref(getLocale())
const t = (key) => tr(key, locale.value)

const displayName = computed(() => {
  const c = customer.value
  if (!c) return ''
  return c.nickname || c.phone || 'OK'
})

function switchLang(loc) {
  locale.value = setLocale(loc)
  document.documentElement.lang = loc === 'en' ? 'en' : 'zh-CN'
}

function onLocaleEvent(e) {
  locale.value = e.detail === 'en' ? 'en' : 'zh'
}

async function loadShop() {
  try {
    const res = await getShop()
    if (res.status === 200 && res.data) {
      shopName.value = res.data.name || '商城'
      shopOpen.value = res.data.open_for_business !== false
      contactPhone.value = res.data.contact_phone || ''
      document.title = `${shopName.value} - 商城`
    } else {
      shopName.value = '店铺不可用'
      shopOpen.value = false
    }
  } catch {
    shopName.value = '无法连接服务'
    shopOpen.value = false
  }
}

function refreshAuth() {
  customer.value = getCustomer()
}

function onLogout() {
  clearAuth()
  customer.value = null
  window.dispatchEvent(new CustomEvent('mall:auth-change'))
  router.push('/')
}

onMounted(() => {
  const q = new URLSearchParams(window.location.search).get('tenant')
  if (q) localStorage.setItem('mall_tenant_slug', q)
  if (!getTenantSlug()) localStorage.setItem('mall_tenant_slug', 'demo-a')
  const lang = new URLSearchParams(window.location.search).get('lang')
  if (lang === 'en' || lang === 'zh') switchLang(lang)
  else document.documentElement.lang = locale.value === 'en' ? 'en' : 'zh-CN'
  loadShop()
  refreshAuth()
  window.addEventListener('mall:auth-change', refreshAuth)
  window.addEventListener('mall:locale-change', onLocaleEvent)
})
onUnmounted(() => {
  window.removeEventListener('mall:auth-change', refreshAuth)
  window.removeEventListener('mall:locale-change', onLocaleEvent)
})
</script>

<style scoped>
.left {
  display: flex;
  align-items: center;
  gap: 32px;
  min-width: 0;
}
.brand {
  display: flex;
  gap: 10px;
  align-items: center;
  cursor: pointer;
  flex-shrink: 0;
}
.mark {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: linear-gradient(135deg, #1677ff, #69b1ff);
  color: #fff;
  display: grid;
  place-items: center;
  font-weight: 700;
}
.nav {
  display: flex;
  gap: 8px;
}
.nav a {
  text-decoration: none;
  color: #4e5969;
  font-size: 14px;
  padding: 8px 14px;
  border-radius: 8px;
}
.nav a.router-link-active {
  color: var(--primary);
  background: #e6f4ff;
  font-weight: 600;
}
.right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}
.lang-switch {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
.lang-btn {
  border: none;
  background: #fff;
  padding: 6px 10px;
  font-size: 12px;
  cursor: pointer;
  color: #4e5969;
}
.lang-btn.active {
  background: var(--primary);
  color: #fff;
}
.user {
  font-size: 14px;
  color: #4e5969;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.link-btn {
  border: 1px solid var(--border);
  background: #fff;
  color: #4e5969;
  border-radius: 8px;
  padding: 7px 14px;
  font-size: 13px;
  text-decoration: none;
  cursor: pointer;
}
.link-btn.primary {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
}
.closed-banner {
  margin-bottom: 12px;
  padding: 10px 14px;
  border-radius: 8px;
  background: #fff7e6;
  border: 1px solid #ffd591;
  color: #ad6800;
  font-size: 13px;
}
</style>
