import http from '@/utils/request'

export function getShop() {
  return http.get('/shop/')
}

export function trackAttribution(data) {
  return http.get('/attribution/track/', { params: data })
}

export function createGrowthLead(data) {
  return http.post('/leads/', data)
}

export function getProducts(params) {
  return http.get('/products/', { params })
}

export function getCategories() {
  return http.get('/categories/')
}

export function getProduct(id) {
  return http.get(`/product/${id}/`)
}

export function sendSmsCode(phone) {
  return http.post('/auth/sms/send/', { phone })
}

export function smsLogin({ phone, code, nickname }) {
  return http.post('/auth/sms/login/', { phone, code, nickname })
}

export function getMe() {
  return http.get('/auth/me/')
}

export function getAddresses() {
  return http.get('/addresses/')
}

export function createAddress(data) {
  return http.post('/addresses/', data)
}

export function createOrder(data) {
  const payload = { ...(data || {}) }
  try {
    const sessionId = localStorage.getItem('agent_session_id') || ''
    if (sessionId && !payload.consultation_session_id) payload.consultation_session_id = sessionId
  } catch (_) {}
  return http.post('/orders/', payload)
}

export function getOrders() {
  return http.get('/orders/')
}

export function getOrder(id) {
  return http.get(`/order/${id}/`)
}

export function claimPaid(id, data) {
  return http.post(`/order/${id}/claim-paid/`, data)
}

export function createPayment(data) {
  return http.post('/pay/create/', data)
}

export function mockPay(data) {
  return http.post('/pay/mock/', data)
}

export function previewFreight(data) {
  return http.post('/freight/preview/', data)
}

export function getCoupons() {
  return http.get('/coupons/')
}

/** 下单（人工确认收款，不自动 mock 支付） */
export async function buyAndMaybePay({ pid, number = 1, address, addressId, autoPay = false }) {
  const payload = { items: [{ pid, number }] }
  if (addressId) payload.address_id = addressId
  else payload.address = address

  const orderRes = await createOrder(payload)
  if (orderRes.status !== 200) {
    throw new Error(orderRes.msg || '下单失败')
  }
  return { order: orderRes.data, paid: false }
}

/** 人工确认模式：不自动 mock */
export async function payExistingOrder() {
  throw new Error('本店为人工确认收款，请按付款说明转账并等待店长确认')
}

/** 多智能体导购（/api/agents，不在 /api/c 下） */
export async function agentChat(text, extra = {}) {
  const { getTenantSlug, getToken } = await import('@/utils/session')
  const headers = {
    'Content-Type': 'application/json',
    'X-Tenant-Slug': getTenantSlug(),
  }
  const token = getToken()
  if (token) headers.token = token
  let session_id = extra.session_id
  try {
    if (!session_id) session_id = localStorage.getItem('agent_session_id') || ''
  } catch (_) {}
  const res = await fetch('/api/agents/chat/', {
    method: 'POST',
    headers,
    body: JSON.stringify({ text, session_id, ...extra }),
  })
  const data = await res.json()
  try {
    const sid = data?.data?.session_id
    if (sid) localStorage.setItem('agent_session_id', sid)
  } catch (_) {}
  return data
}

async function supportRequest(path, options = {}) {
  const { getTenantSlug, getToken } = await import('@/utils/session')
  const headers = {
    'Content-Type': 'application/json',
    'X-Tenant-Slug': getTenantSlug(),
    ...(options.headers || {}),
  }
  const token = getToken()
  if (token) headers.token = token
  const response = await fetch(`/api/agents${path}`, { ...options, headers })
  const data = await response.json()
  if (!response.ok) throw new Error(data?.msg || '客服服务暂不可用')
  return data
}

export function getSupportMessages(sessionId, afterId = 0) {
  const sid = encodeURIComponent(sessionId)
  return supportRequest(`/support/session/${sid}/messages/?after_id=${Number(afterId) || 0}`)
}

export function rateSupportSession(sessionId, score, note = '') {
  const sid = encodeURIComponent(sessionId)
  return supportRequest(`/support/session/${sid}/satisfaction/`, {
    method: 'POST',
    body: JSON.stringify({ score, note }),
  })
}

export function getCart() { return http.get('/cart/') }
export function addCart(data) { return http.post('/cart/', data) }
export function updateCartItem(id, data) { return http.put(`/cart/${id}/`, data) }
export function removeCartItem(id) { return http.delete(`/cart/${id}/`) }
export function checkoutPreview(data) { return http.post('/checkout/preview/', data) }
