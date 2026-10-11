<template>
  <div class="layout">
    <button v-if="isMobile && mobileOpen" class="nav-backdrop" aria-label="关闭导航" @click="mobileOpen = false"></button>
    <aside class="aside" :class="{ collapsed, 'mobile-open': mobileOpen }">
      <div class="aside-brand">
        <div class="logo">购</div>
        <div v-show="!collapsed || isMobile" class="brand-text">
          <div class="title">云购商城</div>
          <div class="sub">管理后台</div>
        </div>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="collapsed && !isMobile"
        :collapse-transition="false"
        background-color="transparent"
        text-color="rgba(255,252,247,0.75)"
        active-text-color="#fff"
        router
        class="aside-menu"
      >
        <el-menu-item index="/data_list">
          <el-icon><Odometer /></el-icon><span>经营首页</span>
        </el-menu-item>
        <el-menu-item index="/order_list">
          <el-icon><List /></el-icon><span>订单</span>
        </el-menu-item>
        <el-sub-menu index="goods">
          <template #title>
            <el-icon><Goods /></el-icon><span>商品</span>
          </template>
          <el-menu-item index="/product_list">商品列表</el-menu-item>
          <el-menu-item index="/automation_center">AI 自动上架</el-menu-item>
          <el-menu-item index="/group_list">商品分类</el-menu-item>
          <el-menu-item index="/freight">运费模板</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/customer_service">
          <el-icon><Message /></el-icon><span>客服</span>
        </el-menu-item>
        <el-menu-item index="/knowledge_base">
          <el-icon><Collection /></el-icon><span>知识库</span>
        </el-menu-item>
        <el-menu-item index="/user_list">
          <el-icon><User /></el-icon><span>员工与权限</span>
        </el-menu-item>
        <el-menu-item index="/shop_settings">
          <el-icon><Setting /></el-icon><span>店铺设置</span>
        </el-menu-item>
      </el-menu>
      <div v-show="!collapsed || isMobile" class="aside-foot">
        <div class="pill">{{ tenantName }}</div>
      </div>
    </aside>

    <section class="main">
      <header class="header">
        <div class="header-left">
          <el-button text :aria-label="isMobile ? '打开导航' : '折叠导航'" @click="toggleNav">
            <el-icon :size="18"><Close v-if="isMobile && mobileOpen" /><Menu v-else-if="isMobile" /><Fold v-else-if="!collapsed" /><Expand v-else /></el-icon>
          </el-button>
          <div class="portal-title">{{ pageTitle }}</div>
        </div>
        <div class="header-right">
          <span class="user-entry">{{ userName }}</span>
          <el-button type="danger" link @click="logout">退出</el-button>
        </div>
      </header>
      <main class="content">
        <el-alert
          v-if="securityTips.length"
          class="sec-alert"
          type="error"
          show-icon
          :closable="true"
          :title="`安全提示：${securityTips[0]}`"
          @close="securityTips = []"
        >
          <template #default>
            <span v-if="securityTips.length > 1">{{ securityTips.slice(1).join('；') }}</span>
            <el-button v-if="pwdWarn" type="primary" link @click="$router.push('/shop_settings')">去店铺设置改密</el-button>
          </template>
        </el-alert>
        <router-view />
      </main>
    </section>
  </div>
</template>

<script setup>
import { Close, Collection, Expand, Fold, Goods, List, Menu, Message, Odometer, Setting, User } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { clearAuthStorage } from '@/utils/permission.js'

const route = useRoute()
const router = useRouter()
const collapsed = ref(false)
const isMobile = ref(false)
const mobileOpen = ref(false)
const pwdWarn = ref(false)
const securityTips = ref([])
function syncViewport() {
  isMobile.value = window.innerWidth <= 760
  if (!isMobile.value) mobileOpen.value = false
}
onMounted(() => {
  try {
    pwdWarn.value = sessionStorage.getItem('password_is_default') === '1'
    securityTips.value = JSON.parse(sessionStorage.getItem('security_tips') || '[]') || []
    if (pwdWarn.value && !securityTips.value.some((item) => String(item).includes('默认密码'))) {
      securityTips.value.unshift('当前仍在使用默认密码，请尽快修改')
    }
  } catch (_) {}
  syncViewport()
  window.addEventListener('resize', syncViewport)
})
onBeforeUnmount(() => window.removeEventListener('resize', syncViewport))
const user = JSON.parse(sessionStorage.getItem('user') || 'null') || {}
const tenant = JSON.parse(sessionStorage.getItem('tenant') || 'null') || {}
const userName = computed(() => user.nick_name || user.name || '管理员')
const tenantName = computed(() => tenant.name || tenant.slug || 'demo')
const activeMenu = computed(() => route.path)
const TITLE_MAP = {
  '/automation_center': 'AI 自动上架',
  '/data_list': '经营首页',
  '/product_list': '商品列表',
  '/add_product': '添加商品',
  '/group_list': '商品分类',
  '/attribute_list': '分类参数',
  '/freight': '运费模板',
  '/order_list': '订单',
  '/customer_service': '客服',
  '/knowledge_base': '知识库',
  '/user_list': '员工与权限',
  '/author_list': '角色菜单',
  '/role_actions': '动作权限',
  '/role_list': '菜单列表',
  '/shop_settings': '店铺设置',
  '/agent_ops': '运营助手',
}
const pageTitle = computed(() => TITLE_MAP[route.path] || '管理后台')
watch(() => route.path, () => { mobileOpen.value = false })
function toggleNav() {
  if (isMobile.value) mobileOpen.value = !mobileOpen.value
  else collapsed.value = !collapsed.value
}
function logout() {
  clearAuthStorage()
  router.push('/login')
}
</script>

<style scoped>
.layout { display:flex; min-height:100vh; background:#f3f0ea; }
.aside {
  width: 232px; background:#14120f; color:#fff;
  display:flex; flex-direction:column;
}
.aside.collapsed { width:64px; }
.aside-brand { display:flex; gap:10px; align-items:center; padding:16px 14px; }
.logo {
  width:36px; height:36px; border-radius:10px;
  background:linear-gradient(145deg,#14b8a6,#0f766e);
  display:flex; align-items:center; justify-content:center; font-weight:700;
}
.brand-text .title { font-weight:650; font-size:15px; }
.brand-text .sub { font-size:12px; opacity:.55; margin-top:2px; }
.aside-menu { border-right:none; flex:1; overflow:auto; padding:4px 8px; background:transparent !important; }
.aside-menu :deep(.el-menu-item),
.aside-menu :deep(.el-sub-menu__title) { border-radius:8px; margin:2px 0; height:42px; }
.aside-menu :deep(.el-menu-item.is-active) { background:rgba(15,118,110,.35) !important; }
.aside-foot { padding:12px; }
.pill {
  font-size:12px; color:rgba(255,255,255,.7);
  background:rgba(255,255,255,.08); border-radius:999px; padding:8px 10px;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
.main { flex:1; min-width:0; display:flex; flex-direction:column; }
.header {
  height:56px; background:#fff; border-bottom:1px solid #e8e4db;
  display:flex; align-items:center; justify-content:space-between; padding:0 16px;
}
.header-left,.header-right { display:flex; align-items:center; gap:12px; }
.portal-title { font-weight:650; color:#14120f; }
.user-entry { color:#5b564e; }
.content { padding:16px; flex:1; }
.sec-alert{margin-bottom:12px}
.nav-backdrop { display:none; }
@media (max-width:760px) {
  .aside {
    position:fixed; inset:0 auto 0 0; z-index:120; width:232px;
    transform:translateX(-100%); transition:transform .2s ease;
  }
  .aside.collapsed { width:232px; }
  .aside.mobile-open { transform:translateX(0); }
  .nav-backdrop {
    display:block; position:fixed; inset:0; z-index:110; border:0;
    background:rgba(20,18,15,.38); padding:0;
  }
  .header { height:52px; padding:0 10px; }
  .content { padding:10px; }
  .portal-title { font-size:14px; }
  .user-entry { display:none; }
}
</style>
