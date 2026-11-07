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
      { path: 'automation_center', name: 'automation_center', component: () => import('../views/AutomationCenterView.vue'), meta: { title: '内容中心' } },
      { path: 'operations_center', name: 'operations_center', component: () => import('../views/OperationsCenterView.vue'), meta: { title: '自动化运营中心' } },
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
      { path: 'agent_ops', redirect: { path: '/operations_center', query: { tab: 'assistant' } } },
      {
        path: 'module_content',
        name: 'module_content',
        component: () => import('../views/ModuleHostView.vue'),
        props: {
          title: 'AI 内容平台',
          description: '商品内容生成、素材与商品知识同步',
          src: 'http://127.0.0.1:5174/',
        },
        meta: { title: '内容中心' },
      },
      {
        path: 'module_cross',
        name: 'module_cross',
        component: () => import('../views/ModuleHostView.vue'),
        props: {
          title: '跨境运营',
          description: '多平台店铺商品与运营任务',
          src: 'http://127.0.0.1:5175/',
        },
        meta: { title: '跨境运营' },
      },
      {
        path: 'module_products',
        name: 'module_products',
        component: () => import('../views/ModuleHostView.vue'),
        props: {
          title: '商品协作',
          description: '使用云购商家账号查看已授权的演示店铺商品',
          src: 'http://127.0.0.1:8090/legacy.html?v=2#products',
        },
        meta: { title: '商品协作' },
      },
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
