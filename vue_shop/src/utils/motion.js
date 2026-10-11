import { mountAdminParticleOcean } from './particleOcean.js'

export function prefersReducedMotion() {
  return true // 默认关闭重特效，保证业务可用
}

export function mountAdminCursor() { return () => {} }
export function mountAdminReveal() { return () => {} }
export function mountAdminFluid() { return () => {} }

export function bootAdminMotion() {
  // 业务优先：暂不挂载粒子海/光标特效
  document.documentElement.classList.remove('admin-turbo')
  return () => {}
}
