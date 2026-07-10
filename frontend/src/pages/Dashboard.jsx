import { useState, useEffect } from 'react'
import StatBar from '../components/StatBar.jsx'
import { getStats, getInspections, getReportText, downloadReportPdf } from '../api.js'

const STAT_LABELS = [
  { key: 'totalInspections', label: 'Total Inspections' },
  { key: 'totalItems', label: 'Items Analysed' },
  { key: 'shelfReadyPct', label: 'Shelf-Ready', accent: 'sage', suffix: '%' },
  { key: 'avgLossPct', label: 'Avg Loss', accent: 'rust', suffix: '%' },
]

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [items, setItems] = useState([])
  const [reportLines, setReportLines] = useState([])
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    (async () => {
      try {
        const [s, insp, report] = await Promise.all([getStats(), getInspections(), getReportText()])
        setStats(s)
        setItems(insp.flatMap(i => i.items))
        setReportLines(report.lines)
      } catch {
        setError('Could not reach the backend. Is the FastAPI server running on port 8000?')
      }
    })()
  }, [])

  async function handleDownload() {
    setDownloading(true)
    try {
      await downloadReportPdf()
    } catch {
      setError('Could not generate the PDF report.')
    } finally {
      setDownloading(false)
    }
  }

  const last10 = items.slice(0, 10).reverse()

  return (
    <div className="shell page-body" style={{ paddingTop: 44 }}>
      <div className="section-head" style={{ marginTop: 0 }}>
        <div>
          <h2 style={{ fontSize: '1.9rem' }}>Dashboard</h2>
          <p>An overview of all inspections, plus a downloadable report.</p>
        </div>
        <button className="btn btn-primary" onClick={handleDownload} disabled={downloading}>
          {downloading ? <span className="spinner" /> : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 16V4m0 0-4 4m4-4 4 4" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /><path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" /></svg>
          )}
          Download PDF report
        </button>
      </div>

      {error && <div className="api-error">{error}</div>}

      <StatBar stats={stats} labels={STAT_LABELS} />

      <div className="dash-grid">
        <div className="panel">
          <h3>Freshness distribution</h3>
          <p style={{ fontSize: '0.85rem' }}>Item count by outcome, most recent inspections first.</p>
          <div className="bar-chart">
            {last10.length === 0 && <p style={{ fontSize: '0.85rem' }}>No scans yet.</p>}
            {last10.map((i, idx) => (
              <div key={idx} className={`bar ${i.tier}`} style={{ height: `${i.freshness}%` }}>
                <span>{i.freshness}%</span>
              </div>
            ))}
          </div>
        </div>
        <div className="panel">
          <h3>Report preview</h3>
          <p style={{ fontSize: '0.85rem', marginBottom: 10 }}>This is what gets bundled into the PDF export.</p>
          <div className="report-preview">{reportLines.join('\n') || 'No data yet — run a scan on the Analyze page.'}</div>
        </div>
      </div>
    </div>
  )
}
