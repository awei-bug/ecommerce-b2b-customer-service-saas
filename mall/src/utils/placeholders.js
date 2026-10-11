/** 无主图时的分类占位（SVG data URI，不依赖外网） */
const svg = (bg1, bg2, iconPath, label) => {
  const s = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="${bg1}"/>
      <stop offset="100%" stop-color="${bg2}"/>
    </linearGradient>
  </defs>
  <rect width="400" height="400" fill="url(#g)"/>
  <g fill="none" stroke="rgba(255,255,255,0.85)" stroke-width="10" stroke-linecap="round" stroke-linejoin="round" transform="translate(120 110) scale(1.1)">
    ${iconPath}
  </g>
  <rect x="70" y="300" width="260" height="44" rx="22" fill="rgba(255,255,255,0.22)"/>
  <text x="200" y="329" text-anchor="middle" font-family="system-ui,sans-serif" font-size="20" fill="rgba(255,255,255,0.95)" font-weight="600">${label}</text>
</svg>`
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(s)}`
}

const ICONS = {
  digital: '<rect x="20" y="30" width="120" height="80" rx="12"/><circle cx="80" cy="70" r="18"/><path d="M50 130h60"/>',
  fashion: '<path d="M40 40 L80 20 L120 40 L110 140 H50 Z"/><path d="M55 60h50"/>',
  food: '<path d="M30 90h100"/><path d="M50 90 V40"/><path d="M80 90 V30"/><path d="M110 90 V45"/><ellipse cx="80" cy="110" rx="55" ry="18"/>',
  home: '<path d="M20 80 L80 30 L140 80"/><path d="M40 75 V140 H120 V75"/>',
  default: '<rect x="35" y="40" width="90" height="90" rx="16"/><path d="M55 90h50M80 65v50"/>',
}

const THEMES = {
  digital: ['#0f766e', '#164e63', ICONS.digital, '数码精选'],
  fashion: ['#9d174d', '#be123c', ICONS.fashion, '穿搭上新'],
  food: ['#b45309', '#c2410c', ICONS.food, '美味优选'],
  home: ['#0f766e', '#365314', ICONS.home, '家居好物'],
  default: ['#0f766e', '#334155', ICONS.default, '精选好物'],
}

export function placeholderForProduct(p) {
  const name = `${p?.name || ''}${p?.introduce || ''}`.toLowerCase()
  let key = 'default'
  if (/耳机|键盘|手环|手机|数码|电脑|充电|蓝牙/.test(name)) key = 'digital'
  else if (/衣|裤|鞋|包|帽|服|棉|皮/.test(name)) key = 'fashion'
  else if (/咖啡|茶|食|饮|粮|酒|糖/.test(name)) key = 'food'
  else if (/灯|枕|家|桌|椅|杯|收纳/.test(name)) key = 'home'
  const [a, b, icon, label] = THEMES[key]
  return svg(a, b, icon, label)
}

export function hasProductImage(p) {
  return Boolean(p?.big_img || p?.small_img)
}
