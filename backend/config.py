"""Runtime settings, read from environment variables (see .env.example)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _path(name: str, default: str) -> Path:
    p = Path(os.getenv(name, default))
    return p if p.is_absolute() else BASE_DIR / p  # relative paths are relative to backend/


MODEL_PATH = _path("FORESIGHT_MODEL_PATH", "models/foresight_vit.pt")
# Optional JSON with held-out test metrics for the checkpoint (shown in /api/models).
MODEL_METRICS_PATH = _path("FORESIGHT_MODEL_METRICS_PATH", "models/foresight_vit_test_metrics.json")
DB_PATH = _path("FORESIGHT_DB_PATH", "foresight.db")
DEVICE = os.getenv("FORESIGHT_DEVICE", "auto")  # auto | cpu | mps | cuda
MAX_UPLOAD_MB = float(os.getenv("FORESIGHT_MAX_UPLOAD_MB", "15"))
MAX_IMAGE_PIXELS = int(os.getenv("FORESIGHT_MAX_IMAGE_PIXELS", str(60_000_000)))
MIN_IMAGE_SIDE = int(os.getenv("FORESIGHT_MIN_IMAGE_SIDE", "32"))
# Mock mode is for UI development only. It is OFF by default and every mock
# response is labelled "DEMO MOCK DATA".
MOCK_MODE = _bool("FORESIGHT_MOCK_MODE", False)
CORS_ORIGINS = [o.strip() for o in os.getenv(
    "FORESIGHT_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
).split(",") if o.strip()]
INFERENCE_TIMEOUT_S = float(os.getenv("FORESIGHT_INFERENCE_TIMEOUT_S", "30"))
