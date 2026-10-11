import { createRouter, createWebHistory } from 'vue-router'
import { isLoggedIn } from '@/utils/session'

const routes = [
  { path: '/', name: 'home', component: () => import('@/views/ProductList.vue'), meta: { title: '首页' } },
  { path: '/product/:id', name: 'product', component: () => import('@/views/ProductDetail.vue'), meta: { title: '商品详情' } },
  {
    path: '/checkout',
    name: 'checkout',
    component: () => import('@/views/CheckoutView.vue'),
    meta: { title: '确认订单', requireAuth: true },
  },
  {
    path: '/pay-result',
    name: 'pay-result',
    component: () => import('@/views/PayResult.vue'),
    meta: { title: '支付结果', requireAuth: true },
  },
  {
    path: '/orders',
    name: 'orders',
    component: () => import('@/views/OrderList.vue'),
    meta: { title: '我的订单', requireAuth: true },
  },
  {
    path: '/order/:id',
    name: 'order-detail',
    component: () => import('@/views/OrderDetail.vue'),
    meta: { title: '订单详情', requireAuth: true },
  },
  { path: '/pay', name: 'pay', component: () => import('@/views/PayView.vue'), meta: { title: '扫码支付', requireAuth: true } },
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { title: '登录' } },
  { path: '/cart', name: 'cart', component: () => import('@/views/CartView.vue'), meta: { title: '购物车', requireAuth: true } },
  { path: '/agent', name: 'agent', component: () => import('@/views/AgentChat.vue'), meta: { title: '导购客服' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

router.beforeEach((to, from, next) => {
  if (to.meta.requireAuth && !isLoggedIn()) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }
  if (to.path === '/login' && isLoggedIn()) {
    next(to.query.redirect ? String(to.query.redirect) : '/')
    return
  }
  next()
})

router.afterEach((to) => {
  document.title = `${to.meta.title || '商城'}`
})

export default router
