import FreshnessRing from './FreshnessRing.jsx'

const TIER_LABEL = { good: 'Looking fresh', warn: 'Use soon', bad: 'Spoiled' }

export default function ItemCard({ item, onNutritionClick }) {
  return (
    <div className={`item-card tier-${item.tier}`}>
      <div className="item-card-top">
        <div>
          <div className="item-name">{item.name}</div>
          <div className="item-sub">{TIER_LABEL[item.tier]}</div>
        </div>
        <FreshnessRing freshness={item.freshness} tier={item.tier} />
      </div>
      <div className="item-meta"><span>Decay coverage</span><b>{item.decayPct}%</b></div>
      <div className="item-meta"><span>Shelf-life left</span><b>{item.days} day{item.days === 1 ? '' : 's'}</b></div>
      <div className={`action-line ${item.tier}`}>{item.action}</div>
      <div className="card-actions">
        <button className="btn btn-secondary" onClick={() => onNutritionClick(item.name)}>Nutrition facts</button>
      </div>
    </div>
  )
}
