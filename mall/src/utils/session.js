const TENANT_KEY = 'mall_tenant_slug'
const TOKEN_KEY = 'mall_customer_token'
const CUSTOMER_KEY = 'mall_customer'

export function getTenantSlug() {
  return localStorage.getItem(TENANT_KEY) || 'demo'
}

export function setTenantSlug(slug) {
  localStorage.setItem(TENANT_KEY, slug || 'demo')
  // 切换店铺时清登录（不同租户买家不互通）
  clearAuth()
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function getCustomer() {
  try {
    const raw = localStorage.getItem(CUSTOMER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setCustomer(customer) {
  if (customer) localStorage.setItem(CUSTOMER_KEY, JSON.stringify(customer))
  else localStorage.removeItem(CUSTOMER_KEY)
}

export function isLoggedIn() {
  return Boolean(getToken())
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(CUSTOMER_KEY)
}

export function saveAuth({ token, customer }) {
  setToken(token)
  setCustomer(customer || null)
}
