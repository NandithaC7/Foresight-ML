import { useEffect, useState } from 'react'
import { getModels } from '../api.js'

const STATUS_LABEL = { loaded: 'Loaded', unavailable: 'Unavailable', disabled: 'Disabled', not_implemented: 'Not implemented', not_in_inference_path: 'Research only' }
const pct = v => (v == null ? '–' : `${(v * 100).toFixed(1)}%`)

export default function About() {
  const [models, setModels] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    getModels().then(setModels).catch(e => setError(e.message))
  }, [])

  const vit = models?.models?.find(m => m.id === 'vit')
  const tm = vit?.test_metrics

  return (
    <div className="shell page-body" style={{ paddingTop: 44 }}>
      <div className="section-head" style={{ marginTop: 0 }}>
        <div>
          <h2 style={{ fontSize: '1.9rem' }}>About this project</h2>
          <p>Research prototype for visual produce-spoilage estimation from a single photo.</p>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 10 }}>
        <h3>The problem</h3>
        <p>Post-harvest food loss is a major issue in Indian agricultural supply chains. Foresight explores whether a phone photo of a single fruit or vegetable can flag <b>visible</b> spoilage cues early. It is an educational research prototype — <b>a visual estimate, not a food-safety guarantee</b>. It cannot see internal decay and does not estimate shelf-life.</p>
      </div>

      <div className="section">
        <div className="section-head"><div><h2>Dataset — audited</h2><p>TriModal Ripeness (TR-6). Counts below were recomputed from the downloaded files.</p></div></div>
        <div className="panel">
          <table className="spec-table">
            <tbody>
              <tr><td>Crops covered</td><td>Banana, carrot, guava, Indian gooseberry, mango, tomato</td></tr>
              <tr><td>Files on disk</td><td>21,653 (≈19.8 GiB): 10,676 sRGB + 10,950 thermal IR-fusion JPEGs, 18 methane logs</td></tr>
              <tr><td>Unique image contents</td><td>10,776 — the <i>Classified</i> folder is a byte-for-byte relabelled copy of <i>Normal</i></td></tr>
              <tr><td>Labels used</td><td>Spoiled / Not_spoiled folder labels (dataset-provided, not independently verified)</td></tr>
              <tr><td>Label conflicts</td><td>170 thermal contents appear under both labels — excluded</td></tr>
              <tr><td>Training data</td><td>5,335 unique sRGB images, split 60/20/20 by capture session (3,177 / 1,087 / 1,071)</td></tr>
              <tr><td>Known limitation</td><td>No specimen IDs; each crop is a few specimens photographed over days, so train and test share specimens</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="section">
        <div className="section-head"><div><h2>Models — live status</h2><p>Read from the backend's <code>/api/models</code> endpoint.</p></div></div>
        {error && <div className="api-error">Could not load model status: {error}</div>}
        <div className="about-grid">
          <div className="model-card m1">
            <h4>ViT classifier — {STATUS_LABEL[vit?.status] || '…'}</h4>
            <p>Pretrained Vision Transformer fine-tuned on TR-6 sRGB images with two heads: produce type (6 classes) and spoilage (Spoiled / Not_spoiled).</p>
            <ul>
              <li>Version: {vit?.version || '–'}</li>
              <li>Backbone: {vit?.backbone || '–'}</li>
              {tm && <li>Held-out test: produce macro-F1 {pct(tm.type?.macro_f1)}, spoilage macro-F1 {pct(tm.spoil?.macro_f1)} (n={tm.spoil?.n})</li>}
              <li>Confidence values are uncalibrated softmax scores</li>
              <li>XAI: attention-rollout heat-map shown with each result</li>
            </ul>
          </div>
          <div className="model-card m2">
            <h4>Planned / gated components</h4>
            <ul>
              {models?.models?.filter(m => m.id !== 'vit').map(m => (
                <li key={m.id}><b>{m.id.toUpperCase()}</b> ({STATUS_LABEL[m.status] || m.status}): {m.reason || m.role}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      <div className="section">
        <div className="section-head"><div><h2>What the results mean</h2></div></div>
        <div className="panel">
          <div className="pill-row">
            <span className="pill">Single item per photo</span>
            <span className="pill">Produce type + spoilage estimate</span>
            <span className="pill">Attention-rollout XAI</span>
            <span className="pill">Shelf-life: not estimated</span>
            <span className="pill">Decay masks: pending annotation</span>
          </div>
          <p style={{ marginTop: 16 }}>The ring on each result is the model's <i>Not_spoiled</i> softmax score. It is not a measured freshness percentage. Test metrics come from a held-out split of the same lab dataset (plain background, same specimens across days), so performance on real-world phone photos is expected to be lower and has not been measured.</p>
        </div>
      </div>

      <div className="section">
        <div className="section-head"><div><h2>Tech stack</h2></div></div>
        <div className="panel">
          <div className="pill-row">
            <span className="pill">React + Vite (frontend)</span>
            <span className="pill">FastAPI (backend)</span>
            <span className="pill">SQLite (scan history)</span>
            <span className="pill">PyTorch + timm (ViT)</span>
            <span className="pill">scikit-learn (metrics, K-means)</span>
            <span className="pill">fpdf2 (server-side PDF export)</span>
          </div>
        </div>
      </div>
    </div>
  )
}
