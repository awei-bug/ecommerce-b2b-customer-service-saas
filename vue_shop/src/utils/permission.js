export function clearAuthStorage() {
  sessionStorage.removeItem('token')
  sessionStorage.removeItem('user')
  sessionStorage.removeItem('tenant')
  sessionStorage.removeItem('actions')
  sessionStorage.removeItem('security_tips')
}

export function setAuth(data) {
  if (data.token) sessionStorage.setItem('token', data.token)
  if (data.user) sessionStorage.setItem('user', JSON.stringify(data.user))
  if (data.tenant) sessionStorage.setItem('tenant', JSON.stringify(data.tenant))
  if (data.actions) sessionStorage.setItem('actions', JSON.stringify(data.actions))
  if (data.security_tips) sessionStorage.setItem('security_tips', JSON.stringify(data.security_tips))
}

/** 按钮级动作权限；无缓存时默认放行（超管/未配置） */
export function hasAction(code) {
  try {
    const raw = sessionStorage.getItem('actions')
    if (!raw) return true
    const list = JSON.parse(raw)
    if (!Array.isArray(list) || !list.length) return true
    return list.includes(code)
  } catch (e) {
    return true
  }
}
