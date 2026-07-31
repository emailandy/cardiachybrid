# resus_qc

This system is a robust data pipeline and code generator that safely parses REDCap dictionaries into Python validation code, maintaining strict invariants for clinical research data.

## Quickstart
```bash
bash scripts/build.sh
```

## Reference
- **[AGENTS.md](AGENTS.md)**: Strict rules for the six core invariants that protect data integrity.
- **[docs/BUILD_ORDER.md](docs/BUILD_ORDER.md)**: The exact sequence and dependency graph for bootstrapping the pipeline.
- **[docs/STATE.md](docs/STATE.md)**: Current position and completion status of the project build.
