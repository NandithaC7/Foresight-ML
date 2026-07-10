# Foresight — Food Spoilage Detection (React + FastAPI)

Full-stack version: React (Vite) frontend, FastAPI backend, SQLite storage.

```
foresight-fullstack/
├── frontend/     React (Vite) — 4 pages
└── backend/      FastAPI — mock analysis, SQLite, PDF export
```

## 1. Run the backend

```
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API docs auto-generate at http://localhost:8000/docs — useful for poking at
endpoints directly.

A `foresight.db` SQLite file is created automatically on first run, right next
to `main.py`. Delete it any time to wipe all stored inspections.

## 2. Run the frontend

```
cd frontend
npm install
cp .env.example .env      # or set VITE_API_BASE to your backend URL
npm run dev
```

Visit http://localhost:5173.

## What's mocked vs real

| Piece | Status |
|---|---|
| Detection / classification / segmentation models | **Mocked** — `backend/mock_model.py` returns randomized plausible results. Swap `simulate_analysis()` for real inference once your YOLOv8 + ViT + U-Net pipeline exists; keep the same return shape and nothing else needs to change. |
| Database (SQLite) | **Real** — inspections genuinely persist in `backend/foresight.db` across restarts. |
| PDF report generation | **Real** — generated server-side with `fpdf2`, no external service. |
| "AI decision" text in the report | **Template-based**, not a live LLM call yet. See the comment above `_build_report_lines()` in `main.py` for how to wire in a real Claude/OpenAI call server-side later — never call it directly from the frontend, since that would expose your API key. |
| Camera capture | **Real** — uses `capture="environment"` on mobile (opens native camera) and `getUserMedia` on desktop (live preview + capture button). |

## Do you need a database?

Yes — SQLite, which is already wired in. It's a single file, free, and needs
no separate server to install or host. You do not need Postgres/MySQL unless
you're scaling to a real multi-user deployment later, which isn't necessary
for a course project or demo.

## Free hosting

- **Frontend**: `npm run build` produces a `dist/` folder — deploy that to
  Netlify, Vercel, or GitHub Pages, all free for static sites.
- **Backend**: needs an always-running process (unlike the static frontend),
  so it can't go on GitHub Pages. Free options: **Render** (free web service
  tier, sleeps after inactivity), **Railway** (free trial credits), or
  **Fly.io** (free allowance). Set `VITE_API_BASE` in the frontend's `.env`
  to wherever you deploy the backend.
- Note: SQLite's `foresight.db` file lives on the backend's disk — on most
  free hosts, that disk is *ephemeral* (wiped on redeploy/restart). Fine for
  a demo; if you need durable storage, look at your host's persistent volume
  option or move to a small hosted Postgres later.
