export default function About() {
  return (
    <div className="shell page-body" style={{ paddingTop: 44 }}>
      <div className="section-head" style={{ marginTop: 0 }}>
        <div>
          <h2 style={{ fontSize: '1.9rem' }}>About this project</h2>
          <p>Multimodal-ready food spoilage detection &amp; decision system.</p>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 10 }}>
        <h3>The problem</h3>
        <p>Post-harvest food loss is a major issue in Indian agricultural supply chains, especially for export-grade produce. Existing AI tools only answer one question: <i>is this spoiled, yes or no.</i> That's not enough to act on — a retailer, exporter, or household needs to know <b>where</b> the damage is, <b>how long</b> until it's unsellable, and <b>what to do right now</b>. This project targets that gap, built to work from a single, realistic, multi-item photo rather than one clean photo per item.</p>
      </div>

      <div className="section">
        <div className="section-head"><div><h2>Dataset — verified</h2><p>TriModal Ripeness (TR-6), Amrita Vishwa Vidyapeetham, Feb 2026, Figshare (free).</p></div></div>
        <div className="panel">
          <table className="spec-table">
            <tbody>
              <tr><td>Crops covered</td><td>Guava, carrot, tomato, Indian gooseberry, banana, mango</td></tr>
              <tr><td>sRGB images</td><td>~14,000+</td></tr>
              <tr><td>Thermal IR-fusion images</td><td>~14,500</td></tr>
              <tr><td>Methane sensor files</td><td>18 time-series CSVs</td></tr>
              <tr><td>Original labels</td><td>Binary — Spoiled / Not Spoiled</td></tr>
              <tr><td>Collection method</td><td>3× daily, tracked through natural decomposition</td></tr>
              <tr><td>Total size</td><td>~18.99 GB</td></tr>
              <tr><td>Hardware needed by us</td><td>None — RGB images used for training/deployment; thermal + gas data used only to derive richer training labels</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="section">
        <div className="section-head"><div><h2>Models</h2><p>Two members, two complementary models, one shared decision layer.</p></div></div>
        <div className="about-grid">
          <div className="model-card m1">
            <h4>Detection + Freshness</h4>
            <p>YOLOv8 detects every item in a single crate/fridge/shelf photo and crops each one out.</p>
            <ul>
              <li>ViT classifier — fruit type + ripeness stage</li>
              <li>Regression head — shelf-life remaining, in days</li>
            </ul>
          </div>
          <div className="model-card m2">
            <h4>Segmentation + Decision</h4>
            <p>U-Net localises decay/bruising per item, down to the pixel.</p>
            <ul>
              <li>Outputs % of surface affected + location</li>
              <li>LLM layer converts numbers into a plain-language action</li>
            </ul>
          </div>
        </div>
      </div>

      <div className="section">
        <div className="section-head"><div><h2>Novelty</h2></div></div>
        <div className="panel">
          <div className="pill-row">
            <span className="pill">First model on TR-6</span>
            <span className="pill">Pixel-level decay masks</span>
            <span className="pill">Shelf-life regression</span>
            <span className="pill">Multi-item real-scene detection</span>
            <span className="pill">LLM decision layer</span>
          </div>
          <p style={{ marginTop: 16 }}>The dataset is new enough that no baseline model exists yet. Our contribution is upgrading its binary labels into pixel-level segmentation + continuous shelf-life labels, shifting the output from a category to a classification + segmentation + regression pipeline, and — the core usability addition — making it work on one uncontrolled photo containing multiple items, which no public fruit-freshness system we could verify currently does.</p>
        </div>
      </div>

      <div className="section">
        <div className="section-head"><div><h2>Tech stack</h2></div></div>
        <div className="panel">
          <div className="pill-row">
            <span className="pill">React + Vite (frontend)</span>
            <span className="pill">FastAPI (backend)</span>
            <span className="pill">SQLite (storage)</span>
            <span className="pill">PyTorch</span>
            <span className="pill">YOLOv8 (Ultralytics)</span>
            <span className="pill">HuggingFace ViT / U-Net</span>
            <span className="pill">CVAT (annotation)</span>
            <span className="pill">Google Colab (training)</span>
            <span className="pill">Claude / OpenAI API (decision layer)</span>
            <span className="pill">fpdf2 (server-side PDF export)</span>
          </div>
        </div>
      </div>
    </div>
  )
}
