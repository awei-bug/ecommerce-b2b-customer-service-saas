/**
 * 商城动效（精简版）：保证业务可用，重特效默认关闭
 */
export function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches
}

export function mountCursorGlow() { return () => {} }
export function mountScrollReveal() { return () => {} }
export function mountParallax() { return () => {} }
export function mountFluidBg() { return () => {} }
export function bindRipple() { return () => {} }
export function bindMagnetic() { return () => {} }

export function burstConfetti(anchor, opts = {}) {
  if (prefersReducedMotion()) return
  const count = opts.count ?? 24
  const colors = opts.colors ?? ['#0f766e', '#14b8a6', '#f59e0b', '#ffffff']
  const host = document.createElement('div')
  host.className = 'fx-confetti-host'
  host.setAttribute('aria-hidden', 'true')
  ;(anchor || document.body).appendChild(host)
  const rect = anchor?.getBoundingClientRect?.()
  const ox = rect ? rect.width / 2 : innerWidth / 2
  const oy = rect ? Math.min(rect.height * 0.3, 100) : 100
  for (let i = 0; i < count; i++) {
    const p = document.createElement('i')
    const ang = (Math.PI * 2 * i) / count
    const dist = 70 + Math.random() * 120
    p.style.cssText = `--dx:${(Math.cos(ang)*dist).toFixed(1)}px;--dy:${(Math.sin(ang)*dist-40).toFixed(1)}px;--rot:${(Math.random()*360).toFixed(0)}deg;--c:${colors[i%colors.length]};width:8px;height:8px;left:${ox}px;top:${oy}px;border-radius:50%;`
    host.appendChild(p)
  }
  setTimeout(() => host.remove(), 1200)
}

export function flashScreen() {
  if (prefersReducedMotion()) return
  const el = document.createElement('div')
  el.className = 'fx-screen-flash'
  document.body.appendChild(el)
  requestAnimationFrame(() => el.classList.add('on'))
  setTimeout(() => el.remove(), 600)
}

export function flyToTarget(fromEl, toSelector = '.brand .mark') {
  // 简化：直接完成，避免卡顿
  return Promise.resolve()
}

export function animateNumber(el, to, opts = {}) {
  if (!el) return
  const prefix = opts.prefix ?? ''
  const decimals = opts.decimals ?? 2
  el.textContent = `${prefix}${Number(to).toFixed(decimals)}`
}

export function bootMallMotion() {
  document.documentElement.classList.remove('fx-turbo')
  // 不挂载粒子海/流体/光标，避免页面卡死、白屏
  return () => {}
}
