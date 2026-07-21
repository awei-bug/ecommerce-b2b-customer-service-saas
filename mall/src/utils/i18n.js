/**
 * Lightweight i18n for customer track page (and shared mall labels).
 * Locale stored in localStorage: mall_locale = 'zh' | 'en'
 */

const STORAGE_KEY = 'mall_locale'

const messages = {
  zh: {
    trackTitle: '运单查询',
    trackHint: '输入运单号查看运输状态与轨迹（无需登录）',
    placeholder: '例如 SH1DEMO0001',
    search: '查询',
    searching: '查询中…',
    needNo: '请输入运单号',
    notFound: '未查到运单，请核对运单号与店铺标识',
    queryFail: '查询失败',
    origin: '起运',
    destination: '目的',
    mode: '运输方式',
    incoterm: '贸易条款',
    blNo: '提单号',
    cargoStats: '件/毛/体',
    cargoDesc: '货描',
    customer: '客户',
    timeline: '运输轨迹',
    noEvents: '暂无轨迹节点',
    documents: '相关附件',
    langZh: '中文',
    langEn: 'EN',
    mode_sea: '海运',
    mode_air: '空运',
    mode_rail: '铁路',
    mode_truck: '卡航',
    type_bl: '提单',
    type_packing: '箱单',
    type_invoice: '发票',
    type_customs: '报关',
    type_other: '其他',
    status_inquiry: '询价中',
    status_quoted: '已报价',
    status_booked: '已订舱',
    status_in_transit: '运输中',
    status_arrived: '已到港',
    status_delivered: '已签收',
    status_closed: '已完结',
    status_cancelled: '已取消',
    navHome: '首页',
    navTrack: '运单查询',
    navOrders: '我的订单',
    navLogin: '登录',
    navLogout: '退出',
    shopClosed: '店铺暂停营业，暂不可下单',
    contact: '咨询',
    footerDemo: '演示商城（电脑浏览器使用）',
  },
  en: {
    trackTitle: 'Shipment Tracking',
    trackHint: 'Enter shipment number to view status and timeline (no login required)',
    placeholder: 'e.g. SH1DEMO0001',
    search: 'Track',
    searching: 'Searching…',
    needNo: 'Please enter a shipment number',
    notFound: 'Shipment not found. Check the number and store tenant.',
    queryFail: 'Query failed',
    origin: 'Origin',
    destination: 'Destination',
    mode: 'Mode',
    incoterm: 'Incoterm',
    blNo: 'B/L No.',
    cargoStats: 'Pkgs / G.W. / CBM',
    cargoDesc: 'Cargo',
    customer: 'Customer',
    timeline: 'Tracking Timeline',
    noEvents: 'No tracking events yet',
    documents: 'Documents',
    langZh: '中文',
    langEn: 'EN',
    mode_sea: 'Sea',
    mode_air: 'Air',
    mode_rail: 'Rail',
    mode_truck: 'Truck',
    type_bl: 'B/L',
    type_packing: 'Packing list',
    type_invoice: 'Invoice',
    type_customs: 'Customs',
    type_other: 'Other',
    status_inquiry: 'Inquiry',
    status_quoted: 'Quoted',
    status_booked: 'Booked',
    status_in_transit: 'In transit',
    status_arrived: 'Arrived',
    status_delivered: 'Delivered',
    status_closed: 'Closed',
    status_cancelled: 'Cancelled',
    navHome: 'Home',
    navTrack: 'Tracking',
    navOrders: 'Orders',
    navLogin: 'Login',
    navLogout: 'Log out',
    shopClosed: 'Store is closed for orders',
    contact: 'Contact',
    footerDemo: 'Demo storefront (desktop browser)',
  },
}

export function getLocale() {
  const v = localStorage.getItem(STORAGE_KEY)
  return v === 'en' ? 'en' : 'zh'
}

export function setLocale(locale) {
  const loc = locale === 'en' ? 'en' : 'zh'
  localStorage.setItem(STORAGE_KEY, loc)
  window.dispatchEvent(new CustomEvent('mall:locale-change', { detail: loc }))
  return loc
}

export function t(key, locale) {
  const loc = locale || getLocale()
  const table = messages[loc] || messages.zh
  return table[key] || messages.zh[key] || key
}

export function statusLabel(status, locale) {
  const key = `status_${status || ''}`
  const label = t(key, locale)
  return label === key ? status || '—' : label
}

export function modeLabel(mode, locale) {
  const key = `mode_${mode || ''}`
  const label = t(key, locale)
  return label === key ? mode || '—' : label
}

export function docTypeLabel(docType, locale) {
  const key = `type_${docType || 'other'}`
  return t(key, locale)
}

export default { getLocale, setLocale, t, statusLabel, modeLabel, docTypeLabel, messages }
