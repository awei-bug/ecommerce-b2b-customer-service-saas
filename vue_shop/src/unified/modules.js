/**
 * 宿主承载模块的唯一注册表。
 *
 * 路由 props、postMessage origin 白名单、登录回跳白名单、侧栏菜单与标题映射
 * 都从这一份读取。此前端口与标题分别写在 router、ModuleHostView、
 * LoginView、HomeView 四处，改一个端口要同步改四个文件。
 */
const RAW_MODULES = [
  {
    key: 'content',
    path: '/module_content',
    title: 'AI 内容平台',
    description: '商品内容生成、素材与商品知识同步',
    src: 'http://127.0.0.1:5174/',
  },
  {
    key: 'products',
    path: '/module_products',
    title: '商品协作',
    description: '使用云购商家账号查看已授权的演示店铺商品',
    src: 'http://127.0.0.1:8090/legacy.html?v=2#products',
  },
  {
    key: 'cross',
    path: '/module_cross',
    title: '跨境运营',
    description: '多平台店铺商品与运营任务',
    src: 'http://127.0.0.1:5175/',
  },
]

export const MODULES = RAW_MODULES.map((item) => ({
  ...item,
  origin: new URL(item.src).origin,
}))

/** 允许接收子应用 postMessage、以及登录后携带令牌回跳的来源。 */
export const HANDOFF_ORIGINS = [...new Set(MODULES.map((item) => item.origin))]

export function isHandoffOrigin(origin) {
  return HANDOFF_ORIGINS.includes(String(origin || ''))
}

export function moduleByPath(path) {
  return MODULES.find((item) => item.path === path) || null
}

/** 登录后的默认落点：统一经营看板，而不是某个单系统首页。 */
export const DEFAULT_HOME = '/unified'
