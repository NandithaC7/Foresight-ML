import { useState, useEffect, useRef } from 'react'
import StatBar from '../components/StatBar.jsx'
import ItemCard from '../components/ItemCard.jsx'
import NutritionModal from '../components/NutritionModal.jsx'
import CameraModal from '../components/CameraModal.jsx'
import { analyzePhoto, getStats, getNutrition } from '../api.js'

const STAT_LABELS = [
  { key: 'totalInspections', label: 'Total Inspections' },
  { key: 'totalItems', label: 'Items Analysed' },
  { key: 'shelfReadyPct', label: 'Shelf-Ready', accent: 'sage', suffix: '%' },
  { key: 'avgLossPct', label: 'Avg Loss', accent: 'rust', suffix: '%' },
]

export default function Analyze() {
  const [stats, setStats] = useState(null)
  const [items, setItems] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const [cameraOpen, setCameraOpen] = useState(false)
  const [nutriOpen, setNutriOpen] = useState(false)
  const [nutriName, setNutriName] = useState(null)
  const [nutriData, setNutriData] = useState(null)
  const [nutriLoading, setNutriLoading] = useState(false)

  const fileInputRef = useRef(null)
  const cameraInputRef = useRef(null)

  useEffect(() => { refreshStats() }, [])

  async function refreshStats() {
    try { setStats(await getStats()) } catch { /* backend may not be running yet */ }
  }

  async function handleFile(file) {
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      const result = await analyzePhoto(file)
      setItems(result.items)
      await refreshStats()
    } catch (err) {
      setError('Could not reach the analysis backend. Is the FastAPI server running on port 8000?')
    } finally {
      setLoading(false)
    }
  }

  function handleCameraClick() {
    const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
    if (isMobile) { cameraInputRef.current?.click(); return }
    setCameraOpen(true)
  }

  async function openNutrition(name) {
    setNutriOpen(true)
    setNutriName(name)
    setNutriLoading(true)
    setNutriData(null)
    try {
      const data = await getNutrition(name)
      setNutriData(data)
    } catch {
      setNutriData(null)
    } finally {
      setNutriLoading(false)
    }
  }

  return (
    <div className="shell page-body">
      <div className="hero">
        <h1>See what's actually going on with your produce.</h1>
      </div>

      <div className="fruits-banner">
        <div className="fruits-banner-content">
          <h2 className="fruits-banner-title">Freshness & Quality Detection</h2>
          <p className="fruits-banner-text">
            Upload or capture a photo of a crate, shelf, or fridge. Foresight finds every item in the frame and tells you what to do with each one.
          </p>
          <button className="btn btn-primary" onClick={() => fileInputRef.current?.click()} disabled={loading}>
            {loading ? <span className="spinner" /> : null} Select Photo to Analyze
          </button>
        </div>
        <div className="fruits-banner-image-wrap">
          <img src="/fruits-banner.png" alt="Fresh Produce Showcase" className="fruits-banner-image" />
        </div>
      </div>

      <div
        className={`dropzone ${dragOver ? 'drag-over' : ''}`}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={e => { e.preventDefault(); setDragOver(false) }}
        onDrop={e => {
          e.preventDefault(); setDragOver(false)
          const f = e.dataTransfer.files[0]
          if (f) handleFile(f)
        }}
      >
        <div className="icon-circle">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none"><path d="M12 16V4m0 0-4 4m4-4 4 4" stroke="#2F4A3D" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /><path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" stroke="#2F4A3D" strokeWidth="1.8" strokeLinecap="round" /></svg>
        </div>
        <h3>Drop a produce photo here</h3>
        <p>Works with crates, shelves, fridges, baskets — JPG, PNG, WEBP</p>
        <div className="dropzone-actions">
          <button className="btn btn-primary" onClick={() => fileInputRef.current?.click()} disabled={loading}>
            {loading ? <span className="spinner" /> : null} Upload photo
          </button>
          <button className="btn btn-secondary" onClick={handleCameraClick} disabled={loading}>Use camera</button>
        </div>
        <input ref={fileInputRef} type="file" accept="image/*" style={{ display: 'none' }}
          onChange={e => handleFile(e.target.files[0])} />
        <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" style={{ display: 'none' }}
          onChange={e => handleFile(e.target.files[0])} />

        <div className="demo-notice">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0, marginTop: 2 }}><circle cx="12" cy="12" r="9" stroke="#4B584C" strokeWidth="1.5" /><path d="M12 8v.01M12 11v5" stroke="#4B584C" strokeWidth="1.5" strokeLinecap="round" /></svg>
          <span>Prototype mode: the FastAPI backend returns simulated placeholder results for reviewing the UI/UX — not a live model prediction yet. See the About page for the real model plan.</span>
        </div>
        {error && <div className="api-error">{error}</div>}
      </div>

      <div className="section">
        <StatBar stats={stats} labels={STAT_LABELS} />
      </div>

      {items && (
        <div className="section">
          <div className="section-head">
            <div>
              <h2>Latest scan</h2>
              <p>Tap any card's nutrition button to see facts for that item.</p>
            </div>
            <button className="btn btn-ghost" onClick={() => setItems(null)}>Clear</button>
          </div>
          <div className="results-grid">
            {items.map((item, i) => (
              <ItemCard key={i} item={item} onNutritionClick={openNutrition} />
            ))}
          </div>
        </div>
      )}

      <div className="section">
        <div className="section-head">
          <div>
            <h2>How Foresight works</h2>
            <p>Three steps, one photo.</p>
          </div>
        </div>
        <div className="steps-grid">
          <div className="step-card">
            <div className="icon-box"><svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M4 8h2l1.5-2h9L18 8h2a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z" stroke="#2F4A3D" strokeWidth="1.6" /><circle cx="12" cy="13" r="3.4" stroke="#2F4A3D" strokeWidth="1.6" /></svg></div>
            <h4>1. Capture the scene</h4>
            <p>Take one photo of a crate, shelf, or fridge — no need to isolate items.</p>
          </div>
          <div className="step-card">
            <div className="icon-box"><svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="7" stroke="#2F4A3D" strokeWidth="1.6" /><path d="m20 20-3.5-3.5" stroke="#2F4A3D" strokeWidth="1.6" strokeLinecap="round" /></svg></div>
            <h4>2. Detect every item</h4>
            <p>A detection model locates each individual fruit or vegetable in frame.</p>
          </div>
          <div className="step-card">
            <div className="icon-box"><svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M9 12l2 2 4-4" stroke="#2F4A3D" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /><circle cx="12" cy="12" r="9" stroke="#2F4A3D" strokeWidth="1.6" /></svg></div>
            <h4>3. Get a decision</h4>
            <p>Each item gets a freshness score, days remaining, and a plain-language action.</p>
          </div>
        </div>
      </div>

      <NutritionModal
        open={nutriOpen}
        name={nutriName}
        data={nutriData}
        loading={nutriLoading}
        onClose={() => setNutriOpen(false)}
      />
      <CameraModal open={cameraOpen} onClose={() => setCameraOpen(false)} onCapture={handleFile} />
    </div>
  )
}
