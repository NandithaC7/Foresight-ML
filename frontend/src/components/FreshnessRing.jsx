const RING_COLORS = { good: '#8FA99C', warn: '#CBBE95', bad: '#C1622E' }

export default function FreshnessRing({ freshness, tier }) {
  const r = 26
  const c = 2 * Math.PI * r
  const offset = c * (1 - freshness / 100)
  const color = RING_COLORS[tier]

  return (
    <div className="ring-wrap">
      <svg width="64" height="64" viewBox="0 0 64 64">
        <circle cx="32" cy="32" r={r} fill="none" stroke="#E7E2D6" strokeWidth="7" />
        <circle
          cx="32" cy="32" r={r} fill="none" stroke={color} strokeWidth="7"
          strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
        />
      </svg>
      <div className="ring-pct">{freshness}%</div>
    </div>
  )
}
