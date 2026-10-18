import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup, waitFor } from '@testing-library/react'
import ItemCard from '../components/ItemCard.jsx'
import About from '../pages/About.jsx'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

// Shape of a real /api/analyze item (see backend/inference.py compose_item)
const realItem = {
  name: 'Banana', produce_class: 'Banana', produce_confidence: 0.9991, spoilage_label: 'Spoiled', spoilage_confidence: 0.998,
  p_spoiled: 0.998, freshness: 0, tier: 'bad', days: null, decayPct: null, decay_mask_available: false,
  action: 'Visible spoilage cues detected — inspect closely and discard if decay is confirmed.',
  xai_overlay: 'data:image/png;base64,iVBORw0KGgo=', xai_method: 'attention_rollout',
  visible_decay_probability: 0.91, visible_decay_label: 'Visible decay', visible_decay_status: 'model',
}

describe('ItemCard', () => {
  it('renders real model fields and never invents shelf-life or decay values', () => {
    render(<ItemCard item={realItem} onNutritionClick={() => {}} />)
    expect(screen.getByText('Banana')).toBeTruthy()
    expect(screen.getByText('Spoiled (100%)')).toBeTruthy()
    expect(screen.getByText('Not available')).toBeTruthy()
    expect(screen.getByText('Pending annotation')).toBeTruthy()
    expect(screen.getByText('Visible decay (91%)')).toBeTruthy()
    expect(screen.getByAltText(/Attention rollout heat-map for Banana/)).toBeTruthy()
    expect(screen.queryByText(/day/)).toBeNull()
  })

  it('labels simulated items as DEMO MOCK DATA', () => {
    render(<ItemCard item={{ name: 'Mango', freshness: 70, tier: 'warn', days: 2, decayPct: 30, action: 'DEMO MOCK DATA — x', mock: true }} onNutritionClick={() => {}} />)
    expect(screen.getByText('DEMO MOCK DATA')).toBeTruthy()
  })
})

describe('About page', () => {
  it('shows the live model status and held-out metrics from /api/models', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true, status: 200,
      json: async () => ({ models: [
        { id: 'vit', status: 'loaded', version: 'vit_b16_primary@epoch9', backbone: 'vit_base_patch16_224', test_metrics: { type: { macro_f1: 1 }, spoil: { macro_f1: 0.9536, n: 1071 } } },
        { id: 'unet', status: 'unavailable', reason: 'No human-reviewed decay masks exist yet.' },
      ] }),
    })
    render(<About />)
    await waitFor(() => expect(screen.getByText(/ViT classifier — Loaded/)).toBeTruthy())
    expect(screen.getByText(/spoilage macro-F1 95.4% \(n=1071\)/)).toBeTruthy()
    expect(screen.getByText(/No human-reviewed decay masks exist yet/)).toBeTruthy()
  })
})
