/**
 * 全页粒子海
 */
export function createParticleOcean(options = {}) {
  const prefersReduced = () =>
    window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches

  return function mountParticleOcean(root = document.body, opts = {}) {
    if (prefersReduced()) return () => {}

    const cfg = { ...options, ...opts }
    const canvas = document.createElement('canvas')
    canvas.className = cfg.className || 'fx-particle-ocean'
    canvas.setAttribute('aria-hidden', 'true')
    root.appendChild(canvas)
    const ctx = canvas.getContext('2d', { alpha: true })

    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    let w = 0
    let h = 0
    let raf = 0
    let tick = 0
    let particles = []
    let mouse = { x: -9999, y: -9999, active: false }
    let burst = 0

    const density = cfg.density ?? 0.00014
    const linkDist = cfg.linkDist ?? 130
    const mouseRadius = cfg.mouseRadius ?? 170
    const teal = cfg.color ?? [15, 118, 110]
    const amber = cfg.accent ?? [245, 158, 11]

    const resize = () => {
      w = window.innerWidth
      h = window.innerHeight
      canvas.width = Math.floor(w * dpr)
      canvas.height = Math.floor(h * dpr)
      canvas.style.width = `${w}px`
      canvas.style.height = `${h}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

      const count = Math.max(60, Math.min(220, Math.floor(w * h * density)))
      const old = particles
      particles = Array.from({ length: count }, (_, i) => {
        const prev = old[i]
        return {
          x: prev ? prev.x : Math.random() * w,
          y: prev ? prev.y : Math.random() * h,
          vx: (Math.random() - 0.5) * 0.55,
          vy: (Math.random() - 0.5) * 0.55,
          r: 1.15 + Math.random() * 2.5,
          phase: Math.random() * Math.PI * 2,
          warm: Math.random() > 0.78,
        }
      })
    }

    const onMove = (e) => {
      mouse.x = e.clientX
      mouse.y = e.clientY
      mouse.active = true
    }
    const onLeave = () => {
      mouse.active = false
      mouse.x = -9999
      mouse.y = -9999
    }
    const onDown = (e) => {
      mouse.x = e.clientX
      mouse.y = e.clientY
      burst = 1
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i]
        const dx = p.x - mouse.x
        const dy = p.y - mouse.y
        const d = Math.hypot(dx, dy) || 1
        if (d < mouseRadius * 1.55) {
          const f = (1 - d / (mouseRadius * 1.55)) * 3.8
          p.vx += (dx / d) * f
          p.vy += (dy / d) * f
        }
      }
    }

    const draw = () => {
      tick += 1
      if (burst > 0) burst *= 0.9
      if (burst < 0.01) burst = 0

      ctx.clearRect(0, 0, w, h)

      const veil = ctx.createLinearGradient(0, 0, w, h)
      veil.addColorStop(0, 'rgba(15,118,110,0.03)')
      veil.addColorStop(0.5, 'rgba(245,158,11,0.02)')
      veil.addColorStop(1, 'rgba(15,118,110,0.035)')
      ctx.fillStyle = veil
      ctx.fillRect(0, 0, w, h)

      // integrate
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i]
        p.vx += Math.cos(tick * 0.01 + p.phase) * 0.0024
        p.vy += Math.sin(tick * 0.012 + p.phase + p.x * 0.008) * 0.025

        if (mouse.active) {
          const dx = p.x - mouse.x
          const dy = p.y - mouse.y
          const d2 = dx * dx + dy * dy
          const r = mouseRadius
          if (d2 < r * r) {
            const d = Math.sqrt(d2) || 1
            const f = (1 - d / r) * 0.72
            p.vx += (dx / d) * f
            p.vy += (dy / d) * f
          }
        }

        p.vx *= 0.984
        p.vy *= 0.984
        p.x += p.vx
        p.y += p.vy

        if (p.x < -24) p.x = w + 24
        else if (p.x > w + 24) p.x = -24
        if (p.y < -24) p.y = h + 24
        else if (p.y > h + 24) p.y = -24
      }

      // links
      ctx.lineWidth = 1
      for (let i = 0; i < particles.length; i++) {
        const a = particles[i]
        for (let j = i + 1; j < particles.length; j++) {
          const b = particles[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const dist = Math.hypot(dx, dy)
          if (dist < linkDist) {
            const alpha = (1 - dist / linkDist) * 0.32
            const c = a.warm || b.warm ? amber : teal
            ctx.strokeStyle = `rgba(${c[0]},${c[1]},${c[2]},${alpha})`
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(b.x, b.y)
            ctx.stroke()
          }
        }
      }

      // mouse spokes + aura
      if (mouse.active) {
        for (let i = 0; i < particles.length; i++) {
          const p = particles[i]
          const dist = Math.hypot(p.x - mouse.x, p.y - mouse.y)
          if (dist < mouseRadius) {
            const alpha = (1 - dist / mouseRadius) * 0.55
            ctx.strokeStyle = `rgba(45,212,191,${alpha})`
            ctx.beginPath()
            ctx.moveTo(mouse.x, mouse.y)
            ctx.lineTo(p.x, p.y)
            ctx.stroke()
          }
        }
        const pr = 22 + burst * 50 + Math.sin(tick * 0.12) * 4
        const g = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, pr * 3.4)
        g.addColorStop(0, 'rgba(45,212,191,0.3)')
        g.addColorStop(0.4, 'rgba(15,118,110,0.1)')
        g.addColorStop(1, 'rgba(15,118,110,0)')
        ctx.fillStyle = g
        ctx.beginPath()
        ctx.arc(mouse.x, mouse.y, pr * 3.4, 0, Math.PI * 2)
        ctx.fill()
      }

      // dots
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i]
        const c = p.warm ? amber : teal
        const pulse = 0.55 + Math.sin(tick * 0.045 + p.phase) * 0.45
        const glow = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.r * 5)
        glow.addColorStop(0, `rgba(${c[0]},${c[1]},${c[2]},${0.6 * pulse})`)
        glow.addColorStop(1, `rgba(${c[0]},${c[1]},${c[2]},0)`)
        ctx.fillStyle = glow
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r * 5, 0, Math.PI * 2)
        ctx.fill()

        ctx.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${0.85 * pulse})`
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fill()
      }

      raf = requestAnimationFrame(draw)
    }

    resize()
    draw()
    window.addEventListener('resize', resize)
    window.addEventListener('pointermove', onMove, { passive: true })
    window.addEventListener('pointerleave', onLeave)
    window.addEventListener('pointerdown', onDown)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerleave', onLeave)
      window.removeEventListener('pointerdown', onDown)
      canvas.remove()
    }
  }
}

export const mountParticleOcean = createParticleOcean({ className: 'fx-particle-ocean' })
export const mountAdminParticleOcean = createParticleOcean({ className: 'admin-particle-ocean' })
