import axios from 'axios'

const baseURL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')
let accessToken = null
let refreshPromise = null

export const api = axios.create({ baseURL, withCredentials: true })

export function getAccessToken() { return accessToken }
export function setAccessToken(token) { accessToken = token || null }

function readAccessCookie() {
  return document.cookie.split('; ').find(value => value.startsWith('pivot_access='))?.split('=')[1] || null
}

async function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = api.post('/api/auth/refresh', null, { skipAuthRefresh: true }).then(() => {
      const token = readAccessCookie()
      if (!token) throw new Error('The refreshed session did not include an access token.')
      setAccessToken(token)
      return token
    }).finally(() => { refreshPromise = null })
  }
  return refreshPromise
}

api.interceptors.request.use(config => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  return config
})

api.interceptors.response.use(response => response, async error => {
  const request = error.config
  if (error.response?.status !== 401 || request?.skipAuthRefresh || request?._retry) return Promise.reject(error)
  request._retry = true
  try {
    const token = await refreshAccessToken()
    request.headers.Authorization = `Bearer ${token}`
    return api(request)
  } catch (refreshError) {
    setAccessToken(null)
    window.dispatchEvent(new CustomEvent('pivot:session-expired'))
    return Promise.reject(refreshError)
  }
})

export const auth = {
  async restore() {
    await refreshAccessToken()
    return (await api.get('/api/auth/me')).data
  },
  login() { window.location.assign(`${baseURL}/api/auth/google/login`) },
  async logout() {
    try { await api.post('/api/auth/logout', null, { skipAuthRefresh: true }) } finally { setAccessToken(null) }
  },
}

export async function request(path, options = {}) {
  try {
    const response = await api({ url: path, method: options.method || 'GET', data: options.body, headers: options.headers })
    return response.data
  } catch (error) {
    if (!error.response) throw new Error('Cannot reach the Pivot API. Start it with "npm run api".')
    throw new Error(error.response.data?.detail || `Request failed (${error.response.status}).`)
  }
}
