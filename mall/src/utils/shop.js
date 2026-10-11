/** 全局店铺信息（去 Demo 化共用） */
import { reactive } from 'vue'
import { getShop } from '@/api'
import { initTheme } from '@/utils/theme'

export const shop = reactive({
  loaded: false,
  error: '',
  name: '云购商城',
  slug: 'demo',
  logo: '',
  open: true,
  payGuide: '',
  contactPhone: '',
  paymentMode: 'manual',
  tagline: '精选好物 · 确认收款后发货',
  shippingNote: '下单后 48 小时内发货（节假日顺延）',
  serviceNote: '支持订单查询与售后登记，问题请联系店主',
  theme: 'retail',
  payQrWechat: '',
  payQrAlipay: '',
  hasPayQr: false,
})

const DEFAULT_PAY = '请微信扫码付款，备注订单号；店主确认后发货。'

export function mediaUrl(path) {
  if (!path) return ''
  const s = String(path)
  if (s.startsWith('http://') || s.startsWith('https://') || s.startsWith('data:')) return s
  if (s.startsWith('/')) return s
  return '/' + s.replace(/^\/+/, '')
}

export async function loadShop() {
  shop.error = ''
  try {
    const res = await getShop()
    if (res.status !== 200 || !res.data) {
      shop.error = res.msg || '店铺信息加载失败'
      shop.open = false
      shop.loaded = true
      return shop
    }
    const d = res.data
    shop.name = d.name || shop.name
    shop.slug = d.slug || shop.slug
    shop.logo = d.logo || ''
    shop.open = d.open_for_business !== false
    shop.payGuide = d.pay_guide || DEFAULT_PAY
    shop.contactPhone = d.contact_phone || ''
    shop.paymentMode = d.payment_mode || 'manual'
    shop.tagline = d.tagline || shop.tagline
    shop.shippingNote = d.shipping_note || shop.shippingNote
    shop.serviceNote = d.service_note || shop.serviceNote
    shop.theme = d.theme || shop.theme || 'retail'
    shop.payQrWechat = d.pay_qr_wechat || ''
    shop.payQrAlipay = d.pay_qr_alipay || ''
    shop.hasPayQr = !!(d.has_pay_qr || d.pay_qr_wechat || d.pay_qr_alipay)
    shop.loaded = true
    document.title = shop.name
    await initTheme(shop.theme)
    return shop
  } catch (e) {
    shop.error = e.message || '无法连接店铺服务'
    shop.open = false
    shop.loaded = true
    return shop
  }
}

export function payGuideText() {
  return shop.payGuide || DEFAULT_PAY
}
