#!/usr/bin/env bash
# Start the local Label Studio used for Foresight annotation (http://localhost:8080).
# Uses this workspace's data dir (account + projects) and enables local-file serving
# rooted at the repository so tasks can reference Foresight-TR6-plus/unet-annotation/images/.
cd "$(dirname "$0")"
set -a; source .labelstudio-data/.env; set +a
export LABEL_STUDIO_BASE_DATA_DIR="$PWD/.labelstudio-data"
# Both old and new variable names, so any Label Studio version enables local files
export LOCAL_FILES_SERVING_ENABLED=true LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true
export LOCAL_FILES_DOCUMENT_ROOT="$(cd .. && pwd)" LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT="$(cd .. && pwd)"
exec .label-studio-venv/bin/label-studio start --no-browser --port 8080
