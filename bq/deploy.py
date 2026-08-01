"""
bq/deploy.py — Idempotent BigQuery deployer enforcing dictionary checksums, dataset parameterization, and scratch refusal.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def check_dictionary_drift(
    instrument_path: Path = Path("dictionary/instrument.csv"),
    dict_ver_path: Path = Path("dictionary/dict_version.txt"),
) -> None:
    """I1 check: sha256(instrument.csv) must match dict_version.txt."""
    if not instrument_path.exists() or not dict_ver_path.exists():
        raise FileNotFoundError(
            f"Missing dictionary files: {instrument_path} or {dict_ver_path}"
        )

    expected = dict_ver_path.read_text().strip()
    actual = hashlib.sha256(instrument_path.read_bytes()).hexdigest()[: len(expected)]
    if actual != expected and hashlib.sha256(instrument_path.read_bytes()).hexdigest() != expected:
        raise ValueError(
            f"Dictionary drift detected: sha256({instrument_path}) ({actual}) "
            f"does not match {dict_ver_path} ({expected}). Re-run hash_dict.sh."
        )


def verify_wide_view_checksum(sql_path: Path = Path("generated/v_redcap_wide.sql")) -> str:
    """Verify SHA-256 header comment in v_redcap_wide.sql against body."""
    if not sql_path.exists():
        raise FileNotFoundError(f"Missing {sql_path}. Run codegen/emit_sql.py first.")

    content = sql_path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    checksum = None
    body_lines = []
    for line in lines:
        if line.startswith("-- CHECKSUM:"):
            checksum = line.split("-- CHECKSUM:")[1].strip()
        elif line.startswith("-- Generated"):
            continue
        else:
            body_lines.append(line)

    if not checksum:
        raise ValueError(f"{sql_path} missing CHECKSUM header comment.")

    body_text = "".join(body_lines)
    actual = hashlib.sha256(body_text.encode("utf-8")).hexdigest()
    if actual != checksum:
        raise ValueError(
            f"v_redcap_wide.sql checksum mismatch: file has been hand-edited! "
            f"(expected {checksum}, got {actual})"
        )
    return content


def resolve_datasets(dataset_arg: str) -> tuple[str, str]:
    """Resolve raw and curated dataset names and forbid deploying to scratch."""
    raw = dataset_arg if dataset_arg.endswith("_raw") else f"{dataset_arg}_raw"
    if dataset_arg == "resus_raw":
        raw = "resus_raw"
    elif dataset_arg == "resus_curated":
        raise ValueError("Cannot deploy raw tables directly to resus_curated.")

    if raw.endswith("_scratch") or "scratch" in raw or "scratch" in dataset_arg:
        raise ValueError(
            f"resus_scratch NEVER receives a table from generated/bq_ddl.sql. "
            f"It exists solely as a --dataset-prefix target for ephemeral CI deployments "
            f"(attempted dataset: {dataset_arg})."
        )

    base = raw[:-4] if raw.endswith("_raw") else raw
    curated = f"{base}_curated"
    return raw, curated


def deploy_sql_artifact(
    sql_text: str,
    raw_ds: str,
    curated_ds: str,
    project_id: str | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Format dataset placeholders and execute or print SQL statements."""
    formatted_sql = sql_text.format(
        raw_dataset=raw_ds,
        curated_dataset=curated_ds,
        scratch_dataset=f"{raw_ds[:-4]}_scratch" if raw_ds.endswith("_raw") else "resus_scratch",
    )

    statements = [s.strip() for s in formatted_sql.split(";") if s.strip()]

    if dry_run:
        print(f"--- [DRY RUN] Would execute {len(statements)} BigQuery SQL statements ---")
        for idx, stmt in enumerate(statements, 1):
            print(f"-- Statement {idx}:")
            print(stmt + ";\n")
        return statements

    cmd = ["bq", "query", "--use_legacy_sql=false"]
    if project_id:
        cmd.extend(["--project_id", project_id])

    for stmt in statements:
        subprocess.run(cmd + [stmt], check=True)
    return statements


def deploy_seed_jsonl(
    seed_path: Path,
    raw_ds: str,
    project_id: str | None = None,
    dry_run: bool = False,
) -> None:
    """Load dim_redcap_field_seed.jsonl idempotently (replace/truncate)."""
    if not seed_path.exists():
        raise FileNotFoundError(f"Missing seed artifact: {seed_path}")

    target_table = f"{raw_ds}.dim_redcap_field"
    if dry_run:
        print(f"--- [DRY RUN] Would load seed JSONL {seed_path} into {target_table} (WRITE_TRUNCATE) ---")
        return

    cmd = [
        "bq",
        "load",
        "--replace",
        "--source_format=NEWLINE_DELIMITED_JSON",
    ]
    if project_id:
        cmd.extend(["--project_id", project_id])
    cmd.extend([target_table, str(seed_path)])
    subprocess.run(cmd, check=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Idempotent BigQuery deployer for resus_qc DDL and views."
    )
    parser.add_argument(
        "--dataset",
        required=True,
        help="Base dataset name or prefix (e.g., 'resus' -> resus_raw/resus_curated). REQUIRED, no default.",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="GCP Project ID (default: gcloud config default).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print SQL statements and schema plan without mutating BigQuery.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    raw_ds, curated_ds = resolve_datasets(args.dataset)

    # Invariant checks
    check_dictionary_drift()
    wide_sql = verify_wide_view_checksum()

    print(f"Deploying resus_qc artifacts to raw='{raw_ds}', curated='{curated_ds}'...")
    ddl_sql = Path("generated/bq_ddl.sql").read_text(encoding="utf-8")
    audit_sql = Path("generated/audit_views.sql").read_text(encoding="utf-8")

    deploy_sql_artifact(ddl_sql, raw_ds, curated_ds, args.project, args.dry_run)
    deploy_seed_jsonl(
        Path("generated/dim_redcap_field_seed.jsonl"), raw_ds, args.project, args.dry_run
    )
    deploy_sql_artifact(wide_sql, raw_ds, curated_ds, args.project, args.dry_run)
    deploy_sql_artifact(audit_sql, raw_ds, curated_ds, args.project, args.dry_run)
    print("Deployment completed successfully.")


if __name__ == "__main__":
    main()
