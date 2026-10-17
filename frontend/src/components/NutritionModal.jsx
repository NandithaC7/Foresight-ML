export default function NutritionModal({ open, name, data, loading, onClose }) {
  if (!open) return null
  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modal-head">
          <h3>{name}</h3>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M6 6l12 12M18 6 6 18" stroke="#2F4A3D" strokeWidth="2" strokeLinecap="round" /></svg>
          </button>
        </div>
        <p style={{ fontSize: '0.82rem', textTransform: 'uppercase', letterSpacing: '.04em', color: 'var(--ink-soft)' }}>
          Nutrition facts · per 100g
        </p>
        {loading && <p style={{ marginTop: 16 }}>Loading…</p>}
        {!loading && data && (
          <>
            <div className="nutri-grid">
              <div className="nutri-cell"><div className="n-label">Calories</div><div className="n-value">{data.calories} kcal</div></div>
              <div className="nutri-cell"><div className="n-label">Carbs</div><div className="n-value">{data.carbs}</div></div>
              <div className="nutri-cell"><div className="n-label">Fiber</div><div className="n-value">{data.fiber}</div></div>
              <div className="nutri-cell"><div className="n-label">Vitamin C</div><div className="n-value">{data.vitaminC}</div></div>
              <div className="nutri-cell"><div className="n-label">Potassium</div><div className="n-value">{data.potassium}</div></div>
            </div>
            <div className="fun-fact">{data.fact}</div>
          </>
        )}
      </div>
    </div>
  )
}
