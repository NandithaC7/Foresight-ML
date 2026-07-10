export default function StatBar({ stats, labels }) {
  // labels: array of { key, label, accent } in display order
  return (
    <div className="stat-bar">
      {labels.map(l => (
        <div className="stat-cell" key={l.key}>
          <div className="stat-label">{l.label}</div>
          <div className={`stat-value ${l.accent ? 'accent-' + l.accent : ''}`}>
            {stats ? stats[l.key] : '—'}{l.suffix || ''}
          </div>
        </div>
      ))}
    </div>
  )
}
