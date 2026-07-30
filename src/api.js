import axios from 'axios'

// A relative URL keeps the packaged app on the same origin as the API. Vite
// proxies it locally; VITE_API_URL is only needed for a separately hosted API.
const baseURL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
let accessToken = null
let refreshPromise = null

export const api = axios.create({ baseURL, withCredentials: true })

export function getAccessToken() { return accessToken }
export function setAccessToken(token) { accessToken = token || null }

async function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = api.post('/api/auth/refresh', null, { skipAuthRefresh: true }).then(() => null).finally(() => { refreshPromise = null })
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
    await refreshAccessToken()
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

export async function downloadFile(path) {
  try {
    const response = await api.get(path, { responseType: 'blob' })
    const disposition = response.headers['content-disposition'] || ''
    const match = disposition.match(/filename="?([^";]+)"?/i)
    const link = document.createElement('a')
    link.href = URL.createObjectURL(response.data)
    link.download = match?.[1] || 'pivot-download'
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(link.href)
  } catch (error) {
    if (!error.response) throw new Error('Cannot reach the Pivot API. Start it with "npm run api".')
    throw new Error(error.response.data?.detail || `Download failed (${error.response.status}).`)
  }
}
