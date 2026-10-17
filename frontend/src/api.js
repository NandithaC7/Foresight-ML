const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function handle(res) {
  if (!res.ok) {
    let code = 'http_error'
    let message = `Request failed (HTTP ${res.status}).`
    try {
      const body = await res.json()
      const d = body?.detail
      if (d && typeof d === 'object') { code = d.code || code; message = d.message || message }
      else if (typeof d === 'string') { message = d }
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, code, message)
  }
  return res.json()
}

async function request(path, options) {
  let res
  try {
    res = await fetch(`${API_BASE}${path}`, options)
  } catch {
    throw new ApiError(0, 'network_error', `Could not reach the analysis backend at ${API_BASE}. Is the FastAPI server running?`)
  }
  return handle(res)
}

export async function analyzePhoto(fileOrBlob, { xai = true } = {}) {
  const form = new FormData()
  form.append('photo', fileOrBlob, fileOrBlob.name || 'photo.jpg')
  return request(`/api/analyze${xai ? '?xai=true' : ''}`, { method: 'POST', body: form })
}

export const getHealth = () => request('/health')
export const getModels = () => request('/api/models')
export const getHistory = (limit = 100) => request(`/api/history?limit=${limit}`)
export const getScan = (scanId) => request(`/api/history/${encodeURIComponent(scanId)}`)
export const getInspections = () => request('/api/inspections')
export const clearInspections = () => request('/api/inspections', { method: 'DELETE' })
export const getStats = () => request('/api/stats')
export const getNutrition = (name) => request(`/api/nutrition/${encodeURIComponent(name)}`)
export const getTips = () => request('/api/tips')
export const getReportText = () => request('/api/report')

export function reportPdfUrl() {
  return `${API_BASE}/api/report/pdf`
}

export async function downloadReportPdf() {
  const res = await fetch(reportPdfUrl())
  if (!res.ok) throw new Error('Could not generate report')
  const blob = await res.blob()
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'foresight-report.pdf'
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}
