import http from '@/utils/request'

export function getShop() {
  return http.get('/shop/')
}

export function getProducts(params) {
  return http.get('/products/', { params })
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
  return http.post('/orders/', data)
}

export function getOrders() {
  return http.get('/orders/')
}

export function getOrder(id) {
  return http.get(`/order/${id}/`)
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

/** 客户运单轨迹查询（无需登录） */
export function trackShipment(no) {
  return http.get('/shipment/track/', { params: { no } })
}

/** 下单并可选立即模拟支付（需已登录） */
export async function buyAndMaybePay({ pid, number = 1, address, addressId, autoPay = true }) {
  const payload = {
    items: [{ pid, number }],
  }
  if (addressId) payload.address_id = addressId
  else payload.address = address

  const orderRes = await createOrder(payload)
  if (orderRes.status !== 200) {
    throw new Error(orderRes.msg || '下单失败')
  }
  const order = orderRes.data
  if (!autoPay) {
    return { order, paid: false }
  }
  const payCreate = await createPayment({ order_id: order.id, channel: 'mock' })
  if (payCreate.status !== 200) {
    throw new Error(payCreate.msg || '创建支付单失败')
  }
  const outTradeNo = payCreate.data.payment.out_trade_no
  const payRes = await mockPay({ out_trade_no: outTradeNo })
  if (payRes.status !== 200) {
    throw new Error(payRes.msg || '支付失败')
  }
  return { order: payRes.data.order || order, paid: true, payment: payRes.data.payment }
}

export async function payExistingOrder(orderId) {
  const payCreate = await createPayment({ order_id: orderId, channel: 'mock' })
  if (payCreate.status !== 200) {
    throw new Error(payCreate.msg || '创建支付单失败')
  }
  const outTradeNo = payCreate.data.payment.out_trade_no
  const payRes = await mockPay({ out_trade_no: outTradeNo })
  if (payRes.status !== 200) {
    throw new Error(payRes.msg || '支付失败')
  }
  return payRes.data
}
