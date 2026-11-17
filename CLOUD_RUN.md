# Hosting CardiacHybrid / AI-CARES on Google Cloud Run

This repository is packaged to build and run the **Interactive Resuscitation Command Center, 3D Video Study Console, Visual Learning Lab, and Live Vertex AI Extraction Engine** (`ui/server.py`) as a containerized **Google Cloud Run Gen2 Service**.

---

## 1. Architecture & Cloud Run Runtime Requirements

Because `ui/server.py` runs both synchronous HTTP/206 video range streaming and asynchronous background extraction threads (`LiveEngineJob` invoking `ffmpeg`, deterministic sensors `S1–S7`, and multi-pass Vertex AI inference), the Cloud Run service uses four key settings:

| Setting | Value | Why It Is Required |
|---|---|---|
| **Execution Environment** | `gen2` | Full Linux syscall compatibility for `ffmpeg`/`ffprobe`/`opencv` and native Cloud Storage FUSE volume mounts. |
| **CPU Allocation** | `--no-cpu-throttling` (`cpu_idle = false`) | Keeps vCPUs active after `POST /api/jobs/live` returns HTTP 200 so background `ffmpeg`, sensor, and Vertex AI passes do not stall between status polls. |
| **Scaling** | `--max-instances=1` + `--session-affinity` | `WORKSPACE` and `LIVE_JOBS` maintain active job state in-process; pinning `max-instances=1` guarantees status polls (`GET /api/jobs/live/status`) hit the same instance. |
| **Resources & Timeout** | `4 vCPU`, `8Gi RAM`, `3600s` | Container writable disk (`/app/.video_cache`, `/tmp`) shares memory in Cloud Run; `8Gi` accommodates H.264 review transcodes, audio extraction, and OpenCV optical flow. |

---

## 2. Quick Deploy (`gcloud run deploy --source .`)

### Step 1: Authenticate & Enable Required APIs
```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-east4"   # or us-central1

gcloud auth login
gcloud config set project "${PROJECT_ID}"

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  storage.googleapis.com \
  bigquery.googleapis.com
```

### Step 2: Grant Runtime Service Account Permissions
Grant Vertex AI (`roles/aiplatform.user`) and optional GCS bucket access (`roles/storage.objectUser`) to the Cloud Run runtime service account (either a dedicated SA from `infra/app_run_service.tf` or the default Compute service account):
```bash
PROJECT_NUM="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUM}-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/aiplatform.user"
```

### Step 3: Deploy Using the Helper Script
Preview the preflight checks and exact command first with `--dry-run`:
```bash
bash scripts/deploy_cloud_run.sh --project "${PROJECT_ID}" --region "${REGION}" --dry-run
```

Deploy **IAM-authenticated** (recommended when sharing via Cloud Run IAM / Identity-Aware Proxy):
```bash
bash scripts/deploy_cloud_run.sh \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --min-instances 1
```

Or deploy with a **mounted GCS video bucket** (for large `.mp4`/`.mov` files without baking 600 MB of videos into the container image) and optional public sandbox access:
```bash
bash scripts/deploy_cloud_run.sh \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --gcs-bucket "your-clinical-demo-videos" \
  --min-instances 1 \
  --allow-unauthenticated
```

---

## 3. Sharing Access Safely with External Customers

1. **Public Sandbox URL (Synthetic / De-identified Demo Only):**
   Pass `--allow-unauthenticated` (never use with real PHI). Cloud Run issues an external HTTPS URL (`https://cardiachybrid-control-center-<hash>-uk.a.run.app`).
2. **Authenticated Customer Preview (Recommended):**
   Keep `--no-allow-unauthenticated` (default) and either:
   - Front the Cloud Run service with **Identity-Aware Proxy (IAP)** / External Load Balancer and grant `roles/iap.httpsResourceAccessor` to specific customer Google/Workspace identities, or
   - Have an authenticated operator run `gcloud run services proxy cardiachybrid-control-center --project="${PROJECT_ID}" --region="${REGION}" --port=8094`.

> **Note on Large Video Uploads (>32 MiB):** Cloud Run's HTTP/1.1 frontend enforces a **32 MiB** maximum request body on direct browser `POST /api/video/upload-local` uploads. For full-length resuscitation recordings (>32 MiB) on Cloud Run, stage the video to GCS (`gs://your-bucket/video.mp4`) and paste the `gs://` URI into Step 1 of the **New Video Review** wizard (or mount the bucket via `--gcs-bucket`).

---

## 4. Declarative Terraform Deployment (`infra/`)

If you manage infrastructure via Terraform, `infra/app_run_service.tf` provisions:
- Least-privilege service account `sa-ui-control-center` (`roles/aiplatform.user`, `roles/storage.objectUser` on `clinical_video`, `roles/bigquery.dataViewer` on `resus_curated`)
- `google_cloud_run_v2_service.control_center` with Gen2 execution, `cpu_idle = false`, `max_instance_count = 1`, `/mnt/videos` GCS volume mount, and `/healthz` startup/liveness probes

Build and push the image to Artifact Registry, then apply Terraform:
```bash
gcloud builds submit \
  --project "${PROJECT_ID}" \
  --tag "${REGION}-docker.pkg.dev/${PROJECT_ID}/resus-qc-repo/control-center:latest" .

cd infra
terraform init
terraform apply \
  -var="project_id=${PROJECT_ID}" \
  -var="region=${REGION}" \
  -var="ui_min_instances=1"
```
