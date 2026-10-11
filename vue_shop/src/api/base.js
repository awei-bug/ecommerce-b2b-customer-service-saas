/**
 * 电商管理后台 API 地址
 * 开发：走 vue-cli 代理（同域），生产：可配 VUE_APP_API_BASE
 */
const isProd = typeof process !== 'undefined' && process.env && process.env.NODE_ENV === 'production'
const envBase = typeof process !== 'undefined' && process.env ? process.env.VUE_APP_API_BASE : undefined

const base = {
  baseURL: envBase !== undefined ? envBase : (isProd ? '' : ''),
  login: '/user/login/',
  me: '/user/me/',
  users: '/user/users/',
  user: '/user/user/',
  resetPwd: '/user/user/',
  shopSettings: '/user/shop/settings/',
  products: '/products/',
  product: '/product/',
  upload_img: '/upload_img/',
  categorys: '/categorys/',
  attributes: '/attributes/',
  attribute: '/attribute/',
  cate_grup: '/cate_grup/',
  orders: '/orders/',
  order: '/order/',
  expresses: '/expresses/',
  ordersExport: '/orders/export/',
  paymentsExport: '/payments/export/',
  ordersSummary: '/orders/summary/',
  dashboardKpi: '/dashboard/kpi/',
  pay: '/pay',
  menus: '/menu/menus/',
  roles: '/roles/',
  role: '/role/',
  permissions: '/permissions/actions/',
  freight: '/freight/templates/',
  freightPreview: '/freight/preview/',
}

export default base
