import { useState, useEffect } from 'react'
import { getStats, getInspections, getReportText, downloadReportPdf } from '../api.js'


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

  // Calculate stats breakdown dynamically
  const total = items.length || 1
  const goodCount = items.filter(i => i.tier === 'good').length
  const warnCount = items.filter(i => i.tier === 'warn').length
  const badCount = items.filter(i => i.tier === 'bad').length
  const goodPct = Math.round((goodCount / total) * 100)
  const warnPct = Math.round((warnCount / total) * 100)
  const badPct = Math.round((badCount / total) * 100)

  const flaggedItems = items.filter(i => i.tier === 'warn' || i.tier === 'bad').slice(0, 5)

  // Circular progress ring calculations
  const shelfPct = stats?.shelfReadyPct || 0
  const circumference = 2 * Math.PI * 34
  const strokeDashoffset = circumference - (shelfPct / 100) * circumference

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

      <div className="bento-grid">
        {/* Card 1: Total Inspections */}
        <div className="bento-card">
          <div>
            <h3>Total Inspections</h3>
            <div className="bento-value">{stats?.totalInspections || 0}</div>
            <div className="bento-subtitle">Scans completed to date</div>
          </div>
          <span className="bento-badge success">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: '2px' }}>
              <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
              <polyline points="17 6 23 6 23 12" />
            </svg>
            Active monitoring
          </span>
        </div>

        {/* Card 2: Items Analysed */}
        <div className="bento-card">
          <div>
            <h3>Items Analysed</h3>
            <div className="bento-value">{stats?.totalItems || 0}</div>
            <div className="bento-subtitle">Total crops scanned</div>
          </div>
          <span className="bento-badge info">Scan database</span>
        </div>

        {/* Card 3: Shelf-Ready Ring */}
        <div className="bento-card">
          <div>
            <h3>Shelf-Ready Rate</h3>
            <div className="bento-subtitle">Predicted not spoiled (model estimate)</div>
          </div>
          <div className="bento-ring-container">
            <svg width="88" height="88" viewBox="0 0 88 88">
              <circle cx="44" cy="44" r="34" fill="none" stroke="rgba(16, 185, 129, 0.08)" strokeWidth="8" />
              <circle
                cx="44"
                cy="44"
                r="34"
                fill="none"
                stroke="#10B981"
                strokeWidth="8"
                strokeDasharray={circumference}
                strokeDashoffset={strokeDashoffset}
                strokeLinecap="round"
                transform="rotate(-90 44 44)"
                style={{ transition: 'stroke-dashoffset 0.8s ease' }}
              />
            </svg>
            <span className="bento-ring-text">{shelfPct}%</span>
          </div>
        </div>

        {/* Card 4: Freshness distribution chart */}
        <div className="bento-card col-span-2">
          <div>
            <h3>Freshness distribution</h3>
            <p style={{ fontSize: '0.82rem', color: 'var(--ink-soft)', margin: '4px 0 0' }}>Not-spoiled score per item (uncalibrated model score), last 10 items.</p>
          </div>
          <div className="bar-chart" style={{ marginTop: '20px' }}>
            {last10.length === 0 && <p style={{ fontSize: '0.85rem' }}>No scans yet.</p>}
            {last10.map((i, idx) => (
              <div key={idx} className={`bar ${i.tier}`} style={{ height: `${i.freshness}%` }}>
                <span>{i.freshness}%</span>
              </div>
            ))}
          </div>
        </div>

        {/* Card 5: Loss breakdown bars */}
        <div className="bento-card">
          <div>
            <h3>Loss breakdown</h3>
            <div className="bento-subtitle">Average crop breakdown</div>
          </div>
          <div className="bento-progress-breakdown">
            <div className="bento-progress-item">
              <div className="bento-progress-labels">
                <span>Not spoiled</span>
                <span>{goodPct}%</span>
              </div>
              <div className="bento-progress-track">
                <div className="bento-progress-bar good" style={{ width: `${goodPct}%` }} />
              </div>
            </div>
            <div className="bento-progress-item">
              <div className="bento-progress-labels">
                <span>Uncertain</span>
                <span>{warnPct}%</span>
              </div>
              <div className="bento-progress-track">
                <div className="bento-progress-bar warn" style={{ width: `${warnPct}%` }} />
              </div>
            </div>
            <div className="bento-progress-item">
              <div className="bento-progress-labels">
                <span>Spoiled</span>
                <span>{badPct}%</span>
              </div>
              <div className="bento-progress-track">
                <div className="bento-progress-bar bad" style={{ width: `${badPct}%` }} />
              </div>
            </div>
          </div>
        </div>

        {/* Card 6: Report preview */}
        <div className="bento-card col-span-2">
          <div>
            <h3>Report Preview</h3>
            <div className="bento-subtitle">Summary exported inside the PDF report</div>
          </div>
          <div className="report-preview" style={{ maxHeight: '144px', marginTop: '16px', border: '1px solid rgba(47, 74, 61, 0.08)' }}>
            {reportLines.join('\n') || 'No data yet — run a scan on the Analyze page.'}
          </div>
        </div>

        {/* Card 7: Flagged items list */}
        <div className="bento-card">
          <div>
            <h3>Needs Attention</h3>
            <div className="bento-subtitle">Items predicted spoiled or uncertain</div>
          </div>
          <div className="bento-list">
            {flaggedItems.length === 0 ? (
              <div className="bento-subtitle" style={{ padding: '10px 0', textAlign: 'center' }}>No items flagged.</div>
            ) : (
              flaggedItems.map((item, index) => (
                <div className={`bento-list-item ${item.tier}`} key={index}>
                  <span className="bento-list-item-name">{item.name}</span>
                  <span className={`bento-list-item-value ${item.tier}`}>{item.freshness}%</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
