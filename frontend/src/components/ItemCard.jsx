import FreshnessRing from './FreshnessRing.jsx'

const TIER_LABEL = { good: 'No spoilage cues', warn: 'Uncertain — check manually', bad: 'Spoiled' }

const pct = v => (v == null ? '–' : `${Math.round(v * 100)}%`)

export default function ItemCard({ item, onNutritionClick }) {
  return (
    <div className={`item-card tier-${item.tier}`}>
      <div className="item-card-top">
        <div>
          <div className="item-name">{item.name}</div>
          <div className="item-sub">{item.mock ? 'DEMO MOCK DATA' : TIER_LABEL[item.tier]}</div>
        </div>
        <FreshnessRing freshness={item.freshness} tier={item.tier} />
      </div>
      {item.produce_confidence != null && (
        <div className="item-meta"><span>Produce type confidence</span><b>{pct(item.produce_confidence)}</b></div>
      )}
      {item.spoilage_label && (
        <div className="item-meta"><span>Spoilage prediction</span><b>{item.spoilage_label} ({pct(item.spoilage_confidence)})</b></div>
      )}
      <div className="item-meta"><span>Not-spoiled score (ring)</span><b>{item.freshness}%</b></div>
      <div className="item-meta"><span>Decay coverage</span><b>{item.decayPct != null ? `${item.decayPct}%` : 'Pending annotation'}</b></div>
      <div className="item-meta"><span>Shelf-life left</span><b>{item.days != null ? `${item.days} day${item.days === 1 ? '' : 's'}` : 'Not available'}</b></div>
      <div className={`action-line ${item.tier}`}>{item.action}</div>
      {item.xai_overlay && (
        <figure style={{ margin: '12px 0 0' }}>
          <img src={item.xai_overlay} alt={`Attention rollout heat-map for ${item.name}`}
            style={{ width: '100%', borderRadius: 8, display: 'block' }} />
          <figcaption style={{ fontSize: '0.75rem', color: 'var(--ink-soft)', marginTop: 4 }}>
            Attention rollout (XAI): brighter = image regions the model attended to. Diagnostic only, not proof of correctness.
          </figcaption>
        </figure>
      )}
      <div className="card-actions">
        <button className="btn btn-secondary" onClick={() => onNutritionClick(item.name)}>Nutrition facts</button>
      </div>
    </div>
  )
}
