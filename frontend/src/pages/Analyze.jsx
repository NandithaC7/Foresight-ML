import { useState, useEffect, useRef } from 'react'
import StatBar from '../components/StatBar.jsx'
import ItemCard from '../components/ItemCard.jsx'
import NutritionModal from '../components/NutritionModal.jsx'
import CameraModal from '../components/CameraModal.jsx'
import { analyzePhoto, getStats, getNutrition, getHealth, downloadReportPdf } from '../api.js'

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
  const [activeStep, setActiveStep] = useState(0) // Default to step 1 active (Capture Photo)
  const [fileName, setFileName] = useState(null) // Tracks uploaded file name
  const [fileSize, setFileSize] = useState(null)
  const [scan, setScan] = useState(null) // full API response (warnings, model version, mock flag)
  const [health, setHealth] = useState(null)
  const [healthError, setHealthError] = useState(false)

  const fileInputRef = useRef(null)
  const cameraInputRef = useRef(null)

  useEffect(() => {
    refreshStats()
    getHealth().then(h => { setHealth(h); setHealthError(false) }).catch(() => setHealthError(true))
  }, [])

  async function refreshStats() {
    try { setStats(await getStats()) } catch { /* backend may not be running yet */ }
  }

  async function handleFile(file) {
    if (!file) return
    setFileName(file.name || 'camera-capture.jpg')
    setFileSize(file.size)
    setLoading(true)
    setError(null)
    setActiveStep(1) // Transition to Detect Items step
    try {
      const result = await analyzePhoto(file)
      setItems(result.items)
      setScan(result)
      await refreshStats()
      setActiveStep(2) // Transition to Get Decision step
    } catch (err) {
      setError(err?.message || 'Analysis failed.')
      setFileName(null)
      setFileSize(null)
      setActiveStep(0)
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
      <div className="hero-banner" style={{ backgroundImage: "linear-gradient(rgba(0, 0, 0, 0.45), rgba(0, 0, 0, 0.45)), url('/hero-bg.jpg')" }}>
        <div className="hero-banner-content">
          <h1 className="hero-banner-title">Read Every Fruit
            Before It Spoils.</h1>
          <p className="hero-banner-text">
            Upload or capture a photo of a single fruit or vegetable. Foresight identifies the produce type and estimates whether it shows visible spoilage cues.
          </p>
          <button className="btn btn-primary" onClick={() => fileInputRef.current?.click()} disabled={loading}>
            {loading ? <span className="spinner" /> : null} Select Photo to Analyze
          </button>
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
        <p> JPG, PNG, WEBP</p>
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
          <span>
            {healthError && 'Backend unreachable — start the FastAPI server to analyze photos. '}
            {health && health.mock_mode && <b>DEMO MOCK DATA mode is ON — results are randomly simulated, not model predictions. </b>}
            {health && !health.mock_mode && health.model_loaded && <>Live model: <b>{health.model_version}</b> (ViT, trained on TR-6). Supports Banana, Carrot, Guava, Indian Gooseberry, Mango, Tomato — one item per photo. </>}
            {health && !health.mock_mode && !health.model_loaded && <><b>Model unavailable:</b> {health.model_error} </>}
            {!health && !healthError && 'Checking model status… '}
            Visual estimate — not a food-safety guarantee.
          </span>
        </div>
        {error && <div className="api-error">{error}</div>}
      </div>

      <div className="section">
        <StatBar stats={stats} labels={STAT_LABELS} />
      </div>

      {items && (
        <div className="section" id="latest-scan-section">
          <div className="section-head">
            <div>
              <h2>Latest scan</h2>
              <p>Tap any card's nutrition button to see facts for that item.</p>
            </div>
            <button className="btn btn-ghost" onClick={() => { setItems(null); setScan(null); setFileName(null); setFileSize(null); setActiveStep(0); }}>Clear</button>
          </div>
          {scan && (
            <div className={scan.mock ? 'api-error' : 'demo-notice'} style={{ marginBottom: 16 }}>
              <span>
                {scan.mock ? <b>DEMO MOCK DATA — not a model prediction. </b> : <>Model <b>{scan.model_version}</b> · {scan.timing_ms?.inference ?? '–'} ms inference. </>}
                {scan.disclaimer}
                {scan.warnings?.length > 0 && (
                  <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                    {scan.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                )}
              </span>
            </div>
          )}
          <div className="results-grid">
            {items.map((item, i) => (
              <ItemCard key={i} item={item} onNutritionClick={openNutrition} />
            ))}
          </div>
        </div>
      )}

      <div className="section">
        <div className="section-head" style={{ marginBottom: '8px' }}>
          <div>
            <h2>How Foresight works</h2>
          </div>
        </div>

        <div className="stepper-container">
          <div className="stepper-timeline">
            <div className="stepper-progress-bg" />
            <div
              className="stepper-progress-fill"
              style={{ width: `${activeStep * 50}%` }}
            />

            {/* Step 1 Node */}
            <div
              className={`stepper-node ${activeStep === 0 ? 'active' : activeStep > 0 ? 'completed' : 'upcoming'}`}
              onClick={() => setActiveStep(0)}
            >
              <div className="stepper-circle-wrap">
                {activeStep > 0 ? (
                  <div className="stepper-circle">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </div>
                ) : (
                  <div className="stepper-circle-outer">
                    <div className="stepper-circle">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                        <circle cx="12" cy="13" r="4" />
                      </svg>
                    </div>
                  </div>
                )}
              </div>
              <span className="stepper-label">Capture Photo</span>
            </div>

            {/* Step 2 Node */}
            <div
              className={`stepper-node ${activeStep === 1 ? 'active' : activeStep > 1 ? 'completed' : 'upcoming'}`}
              onClick={() => setActiveStep(1)}
            >
              <div className="stepper-circle-wrap">
                {activeStep > 1 ? (
                  <div className="stepper-circle">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </div>
                ) : activeStep === 1 ? (
                  <div className="stepper-circle-outer">
                    <div className="stepper-circle">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="11" cy="11" r="8" />
                        <line x1="21" y1="21" x2="16.65" y2="16.65" />
                      </svg>
                    </div>
                  </div>
                ) : (
                  <div className="stepper-circle">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="11" cy="11" r="8" />
                      <line x1="21" y1="21" x2="16.65" y2="16.65" />
                    </svg>
                  </div>
                )}
              </div>
              <span className="stepper-label">Detect Items</span>
            </div>

            {/* Step 3 Node */}
            <div
              className={`stepper-node ${activeStep === 2 ? 'active' : activeStep > 2 ? 'completed' : 'upcoming'}`}
              onClick={() => setActiveStep(2)}
            >
              <div className="stepper-circle-wrap">
                {activeStep === 2 ? (
                  <div className="stepper-circle-outer">
                    <div className="stepper-circle">
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                        <polyline points="22 4 12 14.01 9 11.01" />
                      </svg>
                    </div>
                  </div>
                ) : (
                  <div className="stepper-circle">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                      <polyline points="22 4 12 14.01 9 11.01" />
                    </svg>
                  </div>
                )}
              </div>
              <span className="stepper-label">Get Decision</span>
            </div>
          </div>

          <div className="stepper-cards-wrapper">
            <div className="stepper-cards-grid">
              {/* Card 1 */}
              <div
                className={`stepper-card-container ${activeStep === 0 ? 'active-state' : activeStep > 0 ? 'completed-state' : 'upcoming-state'}`}
                onClick={() => setActiveStep(0)}
              >
                <div className="stepper-card-body">
                  <h4>Capture the scene</h4>
                  <p>Take one clear photo of a single fruit or vegetable.</p>

                  <div className="stepper-card-visual">
                    <div className="photo-upload-visual">
                      <div className="photo-thumbnail-placeholder">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--forest)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                          <circle cx="8.5" cy="8.5" r="1.5" />
                          <polyline points="21 15 16 10 5 21" />
                        </svg>
                      </div>
                      <div className="photo-meta-info">
                        <span className="photo-filename">{fileName || 'no_file_selected.jpg'}</span>
                        <span className="photo-status-badge" style={{ color: fileName ? '#10B981' : 'var(--ink-soft)' }}>
                          {fileName ? (
                            <>
                              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: '4px' }}>
                                <polyline points="20 6 9 17 4 12" />
                              </svg>
                              Uploaded ({fileSize != null ? (fileSize / (1024 * 1024)).toFixed(1) : '?'} MB)
                            </>
                          ) : 'Awaiting upload...'}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="stepper-card-action">
                  <button
                    className="btn-stepper-pill"
                    onClick={(e) => {
                      e.stopPropagation();
                      fileInputRef.current?.click();
                    }}
                  >
                    {fileName ? 'Change Photo' : 'Upload Photo'}
                  </button>
                </div>
              </div>

              {/* Card 2 */}
              <div
                className={`stepper-card-container ${activeStep === 1 ? 'active-state' : activeStep > 1 ? 'completed-state' : 'upcoming-state'}`}
                onClick={() => setActiveStep(1)}
              >
                <div className="stepper-card-body">
                  <h4>Identify the item</h4>
                  <p>A Vision Transformer classifies the produce type (single-item mode — no multi-item detection yet).</p>

                  <div className="stepper-card-visual">
                    <div className="detection-list-visual">
                      {items ? (
                        items.slice(0, 2).map((item, index) => (
                          <div className="detection-item-row" key={index}>
                            <span className="detection-item-name">{item.name} #{index + 1}</span>
                            <span className="detection-item-conf">{item.produce_confidence != null ? Math.round(item.produce_confidence * 100) + '%' : '–'}</span>
                          </div>
                        ))
                      ) : (
                        <div className="decision-skeleton-visual">
                          <div className="skeleton-line medium" />
                          <div className="skeleton-line short" />
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                <div className="stepper-card-action">
                  <button
                    className="btn-stepper-pill"
                    disabled={!items}
                    onClick={(e) => {
                      e.stopPropagation();
                      document.getElementById('latest-scan-section')?.scrollIntoView({ behavior: 'smooth' });
                    }}
                  >
                    {items ? 'Review Result' : 'Pending Scan'}
                  </button>
                </div>
              </div>

              {/* Card 3 */}
              <div
                className={`stepper-card-container ${activeStep === 2 ? 'active-state' : activeStep > 2 ? 'completed-state' : 'upcoming-state'}`}
                onClick={() => setActiveStep(2)}
              >
                <div className="stepper-card-body">
                  <h4>Get a decision</h4>
                  <p>Each item gets a spoilage estimate, a model confidence score and a plain-language action.</p>

                  <div className="stepper-card-visual">
                    {items ? (
                      <div className="photo-upload-visual" style={{ background: 'rgba(16,185,129,0.06)', borderColor: 'rgba(16,185,129,0.2)' }}>
                        <div className="photo-thumbnail-placeholder" style={{ background: '#10B981', color: 'white' }}>
                          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        </div>
                        <div className="photo-meta-info">
                          <span className="photo-filename" style={{ color: 'var(--forest-dark)' }}>{items[0]?.spoilage_label || 'Result'}: {items[0]?.spoilage_confidence != null ? Math.round(items[0].spoilage_confidence * 100) + '% confidence' : ''}</span>
                          <span className="photo-status-badge" style={{ color: 'var(--ink-soft)' }}>
                            {items.length} items evaluated
                          </span>
                        </div>
                      </div>
                    ) : (
                      <div className="decision-skeleton-visual">
                        <div className="skeleton-circle-line">
                          <div className="skeleton-circle" />
                          <div className="skeleton-line short" />
                        </div>
                        <div className="skeleton-line medium" />
                      </div>
                    )}
                  </div>
                </div>
                <div className="stepper-card-action">
                  <button
                    className="btn-stepper-pill"
                    disabled={!items}
                    onClick={(e) => {
                      e.stopPropagation();
                      downloadReportPdf().catch(() => setError('Could not generate the PDF report.'));
                    }}
                  >
                    Generate Report
                  </button>
                </div>
              </div>
            </div>
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
