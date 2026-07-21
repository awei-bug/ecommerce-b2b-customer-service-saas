import axios from 'axios'
import { getTenantSlug, getToken, clearAuth } from '@/utils/session'

const instance = axios.create({
  baseURL: '/api/c',
  timeout: 10000,
})

instance.interceptors.request.use((config) => {
  config.headers['X-Tenant-Slug'] = getTenantSlug()
  const token = getToken()
  if (token) {
    config.headers.token = token
  }
  return config
})

instance.interceptors.response.use(
  (response) => {
    const data = response.data
    if (data && data.status === 401) {
      clearAuth()
      // 避免与 router 循环依赖：用 hash/path 跳转
      if (!window.location.pathname.endsWith('/login')) {
        const redirect = encodeURIComponent(window.location.pathname + window.location.search)
        window.location.assign(`/login?redirect=${redirect}`)
      }
    }
    return data
  },
  (error) => {
    const msg = error.response?.data?.msg || error.message || '网络错误'
    return Promise.reject(new Error(msg))
  },
)

export default instance
