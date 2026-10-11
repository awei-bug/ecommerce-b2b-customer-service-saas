/** 行业皮肤：retail | tea | fashion | digital */
const SKINS = ['retail', 'tea', 'fashion', 'digital']
const KEY = 'mall_theme'

const LINKS = {
  retail: () => import('../styles/skin-retail.css'),
  tea: () => import('../styles/skin-tea.css'),
  fashion: () => import('../styles/skin-fashion.css'),
  digital: () => import('../styles/skin-digital.css'),
}

let current = 'retail'
let loading = null

export function listSkins() {
  return [
    { id: 'retail', name: '综合零售', desc: '苔绿暖纸' },
    { id: 'tea', name: '茶饮滋补', desc: '竹青米白' },
    { id: 'fashion', name: '服饰穿搭', desc: '玫瑰灰' },
    { id: 'digital', name: '数码电器', desc: '深青科技' },
  ]
}

export function getTheme() {
  return current
}

export async function applyTheme(name, { persist = true } = {}) {
  const id = SKINS.includes(name) ? name : 'retail'
  current = id
  document.documentElement.dataset.theme = id
  if (persist) {
    try { localStorage.setItem(KEY, id) } catch (_) {}
  }
  // 动态加载对应皮肤（retail 已在 main 静态引入，再 load 一次无害）
  loading = LINKS[id] ? LINKS[id]() : LINKS.retail()
  await loading
  return id
}

export function initTheme(preferred) {
  const q = new URLSearchParams(window.location.search).get('theme')
  let t = preferred || q
  if (!t) {
    try { t = localStorage.getItem(KEY) } catch (_) { t = null }
  }
  return applyTheme(t || 'retail', { persist: !q })
}
