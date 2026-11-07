const TENANT_KEY = 'mall_tenant_slug'
const TOKEN_KEY = 'mall_customer_token'
const CUSTOMER_KEY = 'mall_customer'
let authVersion = 0

function notifyAuthChange() {
  authVersion += 1
  window.dispatchEvent(new Event('mall:auth-change'))
}

export function getAuthVersion() {
  return authVersion
}

window.addEventListener('storage', (event) => {
  if (!event.key || [TENANT_KEY, TOKEN_KEY, CUSTOMER_KEY, 'agent_session_id'].includes(event.key)) {
    notifyAuthChange()
  }
})

export function getTenantSlug() {
  return localStorage.getItem(TENANT_KEY) || 'demo'
}

export function setTenantSlug(slug) {
  const nextSlug = slug || 'demo'
  if (getTenantSlug() === nextSlug) return
  clearAuth()
  localStorage.setItem(TENANT_KEY, nextSlug)
  notifyAuthChange()
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
  localStorage.removeItem('agent_session_id')
  notifyAuthChange()
}

export function saveAuth({ token, customer }) {
  const previousCustomer = getCustomer()
  if (previousCustomer?.id && String(previousCustomer.id) !== String(customer?.id || '')) {
    localStorage.removeItem('agent_session_id')
  }
  setToken(token)
  setCustomer(customer || null)
  notifyAuthChange()
}
