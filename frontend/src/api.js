const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

async function handle(res) {
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`API error ${res.status}: ${text}`)
  }
  return res.json()
}

export async function analyzePhoto(fileOrBlob) {
  const form = new FormData()
  form.append('photo', fileOrBlob, 'photo.jpg')
  const res = await fetch(`${API_BASE}/api/analyze`, { method: 'POST', body: form })
  return handle(res)
}

export async function getInspections() {
  const res = await fetch(`${API_BASE}/api/inspections`)
  return handle(res)
}

export async function clearInspections() {
  const res = await fetch(`${API_BASE}/api/inspections`, { method: 'DELETE' })
  return handle(res)
}

export async function getStats() {
  const res = await fetch(`${API_BASE}/api/stats`)
  return handle(res)
}

export async function getNutrition(name) {
  const res = await fetch(`${API_BASE}/api/nutrition/${encodeURIComponent(name)}`)
  return handle(res)
}

export async function getTips() {
  const res = await fetch(`${API_BASE}/api/tips`)
  return handle(res)
}

export async function getReportText() {
  const res = await fetch(`${API_BASE}/api/report`)
  return handle(res)
}

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
