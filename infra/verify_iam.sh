#!/usr/bin/env bash
# infra/verify_iam.sh
# Repeatable IAM negative proof script for D07a.
# Creates temporary fixtures in resus_raw and resus_curated, runs queries as
# impersonated sa-analyst and sa-reviewer, asserts 2 successes (curated views)
# and 2 403 PERMISSION DENIED errors (base PHI tables), and tears down on exit.

set -euo pipefail

PROJECT="${1:-nodepeel}"
RAW_DS="resus_raw"
CURATED_DS="resus_curated"

echo "=== Resus QC IAM Verification Script (Project: ${PROJECT}) ==="

PY_CMD="python3"
if [[ -x ".venv/bin/python3" ]]; then
  PY_CMD=".venv/bin/python3"
fi

if ! bq show "${PROJECT}:${RAW_DS}.fact_event" >/dev/null 2>&1; then
  cleanup() {
    echo "Tearing down verification fixtures..."
    bq rm -f --table "${PROJECT}:${CURATED_DS}.v_redcap_wide" 2>/dev/null || true
    bq rm -f --table "${PROJECT}:${CURATED_DS}.v_exemplar_store" 2>/dev/null || true
    bq rm -f --table "${PROJECT}:${RAW_DS}.fact_utterance" 2>/dev/null || true
    bq rm -f --table "${PROJECT}:${RAW_DS}.fact_event" 2>/dev/null || true
    echo "Fixtures removed."
  }

  trap cleanup EXIT
  cleanup

  echo "Creating test fixtures in ${RAW_DS} and ${CURATED_DS}..."
  bq mk --table --project_id="${PROJECT}" "${RAW_DS}.fact_utterance" utterance_id:STRING,text:STRING,timestamp_s:FLOAT >/dev/null
  bq mk --table --project_id="${PROJECT}" "${RAW_DS}.fact_event" event_id:STRING,event_type:STRING,timestamp_s:FLOAT,evidence:JSON >/dev/null
  bq mk --use_legacy_sql=false --view="SELECT event_id, event_type, timestamp_s FROM \`${PROJECT}.${RAW_DS}.fact_event\`" --project_id="${PROJECT}" "${CURATED_DS}.v_redcap_wide" >/dev/null
  bq mk --use_legacy_sql=false --view="SELECT event_id, event_type, timestamp_s FROM \`${PROJECT}.${RAW_DS}.fact_event\`" --project_id="${PROJECT}" "${CURATED_DS}.v_exemplar_store" >/dev/null
else
  echo "Real tables exist in ${RAW_DS} and ${CURATED_DS}; testing against actual schema without temporary fixtures..."
fi

echo "Executing negative proof queries against BigQuery..."
"${PY_CMD}" - "${PROJECT}" <<'EOF'
import sys
import subprocess
import google.oauth2.credentials
from google.cloud import bigquery

project = sys.argv[1]

def get_token(sa_email):
    out = subprocess.run(
        ["gcloud", "auth", "print-access-token", f"--impersonate-service-account={sa_email}"],
        capture_output=True, text=True, check=True
    )
    return out.stdout.strip()

all_ok = True

for sa_name in ["sa-analyst", "sa-reviewer"]:
    sa_email = f"{sa_name}@{project}.iam.gserviceaccount.com"
    print(f"\n--- Testing Service Account: {sa_email} ---")
    try:
        token = get_token(sa_email)
    except subprocess.CalledProcessError as e:
        print(f"FAILED to acquire impersonated access token for {sa_email}: {e.stderr}")
        sys.exit(1)

    creds = google.oauth2.credentials.Credentials(token=token)
    client = bigquery.Client(project=project, credentials=creds)

    queries = [
        ("v_redcap_wide (curated view)", f"SELECT * FROM `{project}.resus_curated.v_redcap_wide`", True),
        ("v_exemplar_store (curated view)", f"SELECT * FROM `{project}.resus_curated.v_exemplar_store`", True),
        ("fact_utterance (base PHI table)", f"SELECT * FROM `{project}.resus_raw.fact_utterance`", False),
        ("fact_event.evidence (base PHI column)", f"SELECT evidence FROM `{project}.resus_raw.fact_event`", False),
    ]

    for label, q, expect_success in queries:
        try:
            results = list(client.query_and_wait(q))
            if expect_success:
                print(f"  [SUCCESS - EXPECTED]   {label} -> {len(results)} rows returned")
            else:
                print(f"  [SUCCESS - UNEXPECTED] {label} -> FAILED NEGATIVE PROOF! Expected 403 denial but query succeeded!")
                all_ok = False
        except Exception as e:
            msg = str(e).split('\n')[0]
            is_403 = "403" in str(e) or "Access Denied" in str(e) or "does not have permission" in str(e)
            if not expect_success and is_403:
                print(f"  [DENIED - EXPECTED]    {label} -> {msg}")
            else:
                print(f"  [ERROR - UNEXPECTED]   {label} -> {msg}")
                all_ok = False

if not all_ok:
    print("\n✗ IAM verification failed.")
    sys.exit(1)
print("\n✓ IAM NEGATIVE PROOF VERIFIED (2 successes + 2 403 denials per SA).")
EOF
