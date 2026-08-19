# resus_qc

This system is a robust data pipeline and code generator that safely parses REDCap dictionaries into Python validation code, maintaining strict invariants for clinical research data.

## Local Quickstart
Run the local pipeline build and tests:
```bash
bash scripts/build.sh
```

## Cloud Deployment (GCP / Terraform)
To deploy the pipeline and its required infrastructure (BigQuery, Storage, IAM, and Cloud Run Jobs) to a new Google Cloud project:

1. **Authenticate to Google Cloud**
   ```bash
   cd infra
   gcloud auth application-default login
   ```

2. **Provision the Infrastructure**
   ```bash
   terraform init
   terraform apply -var="project_id=YOUR_GCP_PROJECT_ID"
   ```

3. **Build and Deploy the Pipeline**
   From the project root (`resus_qc/`), build and push the Docker container to the Artifact Registry repository created in Step 2:
   ```bash
   gcloud builds submit --tag us-east4-docker.pkg.dev/YOUR_GCP_PROJECT_ID/resus-qc-repo/pipeline:latest
   ```

4. **Execute the Pipeline**
   ```bash
   gcloud run jobs execute resus-qc-pipeline-job --region us-east4
   ```

## Reference
- **[AGENTS.md](AGENTS.md)**: Strict rules for the six core invariants that protect data integrity.
- **[docs/BUILD_ORDER.md](docs/BUILD_ORDER.md)**: The exact sequence and dependency graph for bootstrapping the pipeline.
- **[docs/STATE.md](docs/STATE.md)**: Current position and completion status of the project build.
