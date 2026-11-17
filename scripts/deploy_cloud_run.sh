#!/usr/bin/env bash
# scripts/deploy_cloud_run.sh — Package & deploy the CardiacHybrid / AI-CARES Control Center to Google Cloud Run.
#
# Usage examples:
#   # Dry-run preflight & print exact gcloud command:
#   bash scripts/deploy_cloud_run.sh --project my-gcp-project --dry-run
#
#   # IAM-authenticated deployment (recommended for clinical/customer demos):
#   bash scripts/deploy_cloud_run.sh --project my-gcp-project --region us-east4
#
#   # Public sandbox deployment with a mounted GCS video bucket:
#   bash scripts/deploy_cloud_run.sh --project my-gcp-project --region us-central1 \
#     --gcs-bucket my-demo-video-bucket --allow-unauthenticated
set -euo pipefail

cd "$(dirname "$0")/.."

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-}"
REGION="${CLOUD_RUN_REGION:-us-east4}"
SERVICE_NAME="${CLOUD_RUN_SERVICE:-cardiachybrid-control-center}"
GCS_BUCKET="${AICARES_GCS_BUCKET:-}"
SERVICE_ACCOUNT=""
MIN_INSTANCES="0"
ALLOW_UNAUTH="false"
DRY_RUN="false"

usage() {
  cat <<'EOF'
Usage: bash scripts/deploy_cloud_run.sh [options]

Options:
  --project <ID>             GCP Project ID (defaults to $GOOGLE_CLOUD_PROJECT or gcloud config)
  --region <REGION>          Cloud Run region (default: us-east4)
  --service <NAME>           Cloud Run service name (default: cardiachybrid-control-center)
  --gcs-bucket <BUCKET>      Optional GCS bucket for video staging + Gen2 /mnt/videos FUSE mount
  --service-account <EMAIL>  Optional dedicated runtime service account email
  --min-instances <N>        Minimum warm instances (default: 0; use 1 for live demos)
  --allow-unauthenticated    Allow public unauthenticated access (default: IAM-authenticated only)
  --dry-run                  Run local preflight checks and print the deploy command without executing
  -h, --help                 Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project) PROJECT_ID="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --service) SERVICE_NAME="$2"; shift 2 ;;
    --gcs-bucket) GCS_BUCKET="${2#gs://}"; shift 2 ;;
    --service-account) SERVICE_ACCOUNT="$2"; shift 2 ;;
    --min-instances) MIN_INSTANCES="$2"; shift 2 ;;
    --allow-unauthenticated) ALLOW_UNAUTH="true"; shift ;;
    --dry-run) DRY_RUN="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$PROJECT_ID" ]] && command -v gcloud >/dev/null 2>&1; then
  PROJECT_ID="$(gcloud config get-value project --quiet 2>/dev/null || true)"
  [[ "$PROJECT_ID" == "(unset)" ]] && PROJECT_ID=""
fi

if [[ -z "$PROJECT_ID" ]]; then
  echo "ERROR: No GCP project specified. Pass --project <PROJECT_ID> or set GOOGLE_CLOUD_PROJECT." >&2
  exit 1
fi

echo "=== [1/3] Running repository invariant gate ==="
bash scripts/check_invariants.sh

echo ""
echo "=== [2/3] Verifying Cloud Run packaging files ==="
for req in Dockerfile .dockerignore .gcloudignore pyproject.toml ui/server.py ui/package.json; do
  if [[ ! -f "$req" ]]; then
    echo "ERROR: Required file missing: $req" >&2
    exit 1
  fi
done
if grep -q "\.uplink\.goog" ui/package-lock.json 2>/dev/null; then
  echo "ERROR: ui/package-lock.json still contains internal proxy URLs." >&2
  exit 1
fi
echo "✓ Packaging manifests verified (Dockerfile, .dockerignore, .gcloudignore, ui/package-lock.json)"

ENV_VARS="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_API_USE_CLIENT_CERTIFICATE=false"
VOLUME_FLAGS=()
if [[ -n "$GCS_BUCKET" ]]; then
  ENV_VARS="${ENV_VARS},AICARES_GCS_BUCKET=${GCS_BUCKET},AICARES_VIDEO_DIR=/mnt/videos"
  VOLUME_FLAGS=(
    "--add-volume=name=clinical-videos,type=cloud-storage,bucket=${GCS_BUCKET}"
    "--add-volume-mount=volume=clinical-videos,mount-path=/mnt/videos"
  )
fi

AUTH_FLAG="--no-allow-unauthenticated"
if [[ "$ALLOW_UNAUTH" == "true" ]]; then
  AUTH_FLAG="--allow-unauthenticated"
fi

SA_FLAGS=()
if [[ -n "$SERVICE_ACCOUNT" ]]; then
  SA_FLAGS=("--service-account=${SERVICE_ACCOUNT}")
fi

DEPLOY_CMD=(
  gcloud run deploy "$SERVICE_NAME"
  "--project=${PROJECT_ID}"
  "--region=${REGION}"
  "--source=."
  "--execution-environment=gen2"
  "--cpu=4"
  "--memory=8Gi"
  "--no-cpu-throttling"
  "--cpu-boost"
  "--timeout=3600"
  "--min-instances=${MIN_INSTANCES}"
  "--max-instances=1"
  "--session-affinity"
  "$AUTH_FLAG"
  "--set-env-vars=${ENV_VARS}"
  "${SA_FLAGS[@]}"
  "${VOLUME_FLAGS[@]}"
)

echo ""
echo "=== [3/3] Cloud Run Deployment Command ==="
printf 'CLOUDSDK_CORE_INTERACTIVE_UX_STYLE=OFF'
for arg in "${DEPLOY_CMD[@]}"; do
  if [[ "$arg" == *[[:space:]]* ]]; then
    printf ' "%s"' "$arg"
  else
    printf ' %s' "$arg"
  fi
done
printf '\n\n'

if [[ "$DRY_RUN" == "true" ]]; then
  echo "✓ Dry-run complete. Re-run without --dry-run after authenticating gcloud to deploy."
  exit 0
fi

CLOUDSDK_CORE_INTERACTIVE_UX_STYLE=OFF "${DEPLOY_CMD[@]}"
