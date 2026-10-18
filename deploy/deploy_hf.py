"""
deploy_hf.py — publish the Foresight backend and its model files to Hugging Face.

Requires a Hugging Face login on this machine (run `.venv/bin/hf auth login` yourself).
Creates/updates:
  * model repo  <user>/foresight-models  : the 5 model files from backend/models/
  * Docker Space <user>/foresight-api    : backend code + Dockerfile (models download at startup)
and sets the Space variables FORESIGHT_MODEL_REPO and CORS settings.
DATABASE_URL (hosted Postgres) must be added by you as a Space *secret* in the Space settings.

Usage: .venv/bin/python deploy/deploy_hf.py [--frontend-origin https://<app>.vercel.app]
"""
import argparse
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
MODEL_FILES = ["foresight_vit.pt", "foresight_vit_test_metrics.json", "visible_decay_probe.json", "unet_pilot.pt", "shelf_life_proxy.json"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", default="foresight-api")
    ap.add_argument("--models", default="foresight-models")
    ap.add_argument("--frontend-origin", default="")
    ap.add_argument("--skip-models", action="store_true")
    a = ap.parse_args()
    api = HfApi()
    user = api.whoami()["name"]
    model_repo, space_repo = f"{user}/{a.models}", f"{user}/{a.space}"

    api.create_repo(model_repo, repo_type="model", exist_ok=True)
    if not a.skip_models:
        for f in MODEL_FILES:
            print("uploading", f, flush=True)
            api.upload_file(path_or_fileobj=str(ROOT / "backend/models" / f), path_in_repo=f, repo_id=model_repo,
                            commit_message=f"Add {f}")

    api.create_repo(space_repo, repo_type="space", space_sdk="docker", exist_ok=True)
    api.upload_folder(folder_path=str(ROOT / "backend"), repo_id=space_repo, repo_type="space",
                      ignore_patterns=["models/*.pt", "models/*.json", "tests/*", "foresight.db", "__pycache__/*", "*.pyc", ".env"],
                      commit_message="Deploy Foresight backend")
    api.upload_file(path_or_fileobj=str(ROOT / "deploy/hf_space/README.md"), path_in_repo="README.md", repo_id=space_repo, repo_type="space")

    origins = "http://localhost:5173" + (f",{a.frontend_origin.rstrip('/')}" if a.frontend_origin else "")
    for k, v in {"FORESIGHT_MODEL_REPO": model_repo, "FORESIGHT_CORS_ORIGINS": origins,
                 "FORESIGHT_CORS_ORIGIN_REGEX": r"https://.*\.vercel\.app"}.items():
        api.add_space_variable(space_repo, k, v)
    host = f"https://{user.lower()}-{a.space.lower()}.hf.space"
    print("\nSpace:", f"https://huggingface.co/spaces/{space_repo}")
    print("API base URL:", host)


if __name__ == "__main__":
    main()
