import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '../views/LoginView.vue'
import HomeView from '../views/HomeView.vue'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: LoginView,
  },
  {
    path: '/',
    name: 'home',
    component: HomeView,
    redirect: '/data_list',
    children: [
      { path: 'automation_center', name: 'automation_center', component: () => import('../views/AutomationCenterView.vue'), meta: { title: 'AI 自动上架' } },
      { path: 'data_list', name: 'data_list', component: () => import('../views/DataView.vue'), meta: { title: '经营首页' } },
      { path: 'product_list', name: 'product_list', component: () => import('../views/ProductView.vue'), meta: { title: '商品列表' } },
      { path: 'add_product', name: 'add_product', component: () => import('../views/AddProductView.vue'), meta: { title: '添加商品' } },
      { path: 'group_list', name: 'group_list', component: () => import('../views/GroupView.vue'), meta: { title: '商品分类' } },
      { path: 'attribute_list', name: 'attribute_list', component: () => import('../views/AttributeView.vue'), meta: { title: '分类参数' } },
      { path: 'freight', name: 'freight', component: () => import('../views/FreightView.vue'), meta: { title: '运费模板' } },
      { path: 'order_list', name: 'order_list', component: () => import('../views/OrderView.vue'), meta: { title: '订单管理' } },
      { path: 'customer_service', name: 'customer_service', component: () => import('../views/CustomerServiceView.vue'), meta: { title: '客服工作台' } },
      { path: 'knowledge_base', name: 'knowledge_base', component: () => import('../views/KnowledgeBaseView.vue'), meta: { title: '客服知识库' } },
      { path: 'user_list', name: 'user_list', component: () => import('../views/UserView.vue'), meta: { title: '员工列表' } },
      { path: 'role_list', name: 'role_list', component: () => import('../views/MenuView.vue'), meta: { title: '菜单列表' } },
      { path: 'author_list', name: 'author_list', component: () => import('../views/AuthorView.vue'), meta: { title: '角色菜单' } },
      { path: 'role_actions', name: 'role_actions', component: () => import('../views/RoleActionsView.vue'), meta: { title: '动作权限' } },
      { path: 'shop_settings', name: 'shop_settings', component: () => import('../views/ShopSettingsView.vue'), meta: { title: '店铺设置' } },
      { path: 'agent_ops', name: 'agent_ops', component: () => import('../views/AgentOpsView.vue'), meta: { title: '运营助手' } },
      {
        path: ':pathMatch(.*)*',
        name: 'notfound',
        component: {
          template: `
            <div class="page-card" style="text-align:center;padding:48px 24px">
              <h2 style="margin:0 0 8px">页面不存在或未配置</h2>
              <p style="color:#8a8478">当前路径没有对应模块。请从左侧菜单进入。</p>
              <a href="/data_list" style="color:#0f766e;font-weight:600">返回经营首页</a>
            </div>
          `,
        },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(process.env.BASE_URL),
  routes,
})

router.beforeEach((to, from, next) => {
  if (to.path === '/login') return next()
  const token = sessionStorage.getItem('token')
  if (!token) return next('/login')
  next()
})

export default router
