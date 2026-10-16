import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getInspections, getTips } from '../api.js'

function fmtDate(ts) {
  const d = new Date(ts)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) +
    ' · ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

const TIER_LABEL = { good: 'Not spoiled', warn: 'Uncertain', bad: 'Spoiled' }

export default function History() {
  const [inspections, setInspections] = useState([])
  const [tips, setTips] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    (async () => {
      try {
        const [insp, allTips] = await Promise.all([getInspections(), getTips()])
        setInspections(insp)
        setTips([...allTips].sort(() => 0.5 - Math.random()).slice(0, 3))
      } catch {
        setError('Could not reach the backend. Is the FastAPI server running on port 8000?')
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const items = inspections.flatMap(insp => insp.items.map(it => ({ ...it, ts: insp.ts, mock: it.mock || insp.mock })))
  const wasted = items.filter(i => i.tier === 'bad').length
  const total = items.length
  const wastePct = total ? Math.round((wasted / total) * 100) : 0

  return (
    <div className="shell page-body" style={{ paddingTop: 44 }}>
      <div className="section-head" style={{ marginTop: 0 }}>
        <div>
          <h2 style={{ fontSize: '1.9rem' }}>Waste history</h2>
          <p>Every scan you've run, and how much of it was lost.</p>
        </div>
      </div>

      {error && <div className="api-error">{error}</div>}

      <div className="stat-bar">
        <div className="stat-cell"><div className="stat-label">Predicted Spoiled</div><div className="stat-value accent-rust">{wasted}</div></div>
        <div className="stat-cell"><div className="stat-label">Waste Rate</div><div className="stat-value accent-tan">{wastePct}%</div></div>
        <div className="stat-cell"><div className="stat-label">Total Discarded</div><div className="stat-value">{wasted}</div></div>
        <div className="stat-cell"><div className="stat-label">Items Tracked</div><div className="stat-value accent-sage">{total}</div></div>
      </div>

      <div className="section">
        <div className="section-head">
          <div><h2>Tips to reduce it next time</h2><p>Based on common causes of produce waste.</p></div>
        </div>
        <div className="tips-strip">
          {tips.map((t, i) => (
            <div className="tip-card" key={i}>
              <div className="tip-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.3 1 2.5h6c0-1.2.3-1.8 1-2.5A6 6 0 0 0 12 3Z" stroke="#2F4A3D" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
              </div>
              <p>{t}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="section">
        <div className="section-head">
          <div><h2>Scan log</h2><p>Every item detected across all inspections, most recent first.</p></div>
        </div>

        {loading && <p>Loading…</p>}

        {!loading && !items.length && !error && (
          <div className="empty-state">
            <div className="icon-circle">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none"><path d="M4 8h2l1.5-2h9L18 8h2a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z" stroke="#2F4A3D" strokeWidth="1.6" /></svg>
            </div>
            <h3>No scans yet</h3>
            <p style={{ marginTop: 6 }}>Run your first analysis on the Analyze page to start building your history.</p>
            <Link to="/" className="btn btn-primary" style={{ marginTop: 18, display: 'inline-flex' }}>Analyze produce</Link>
          </div>
        )}

        {!loading && items.length > 0 && (
          <table className="log-table">
            <thead><tr><th>Scanned</th><th>Item</th><th>Not-spoiled score</th><th>Shelf-life</th><th>Status</th></tr></thead>
            <tbody>
              {items.map((i, idx) => (
                <tr key={idx}>
                  <td>{fmtDate(i.ts)}</td>
                  <td>{i.name}{i.mock ? ' (DEMO MOCK)' : ''}</td>
                  <td className="mono">{i.freshness}%</td>
                  <td className="mono">{i.days != null ? `${i.days} day${i.days === 1 ? '' : 's'}` : 'n/a'}</td>
                  <td><span className={`tag ${i.tier}`}>{TIER_LABEL[i.tier]}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
