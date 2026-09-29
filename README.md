# GeoQueryBench Validation Tools

This contribution contains the validation scripts used to audit assigned GeoQueryBench questions. It does not include benchmark files, source datasets, Parquet files, validation outputs, or logs.

## Methodology

The PowerShell runner reads each question's task from the benchmark question CSV, dispatches it to the matching Python validator, and records the exit code, duration, and log path in a summary CSV. The validators execute the supplied reference solution using the local benchmark and frozen datasets, then perform task-specific result, metadata, or visualization checks. The secondary scripts provide focused spatial/data checks for three individual questions.

`PASS_EXECUTION` means a validator completed with exit code 0; it is not by itself a claim that every comparison or diagnostic passed. Review each validator's output and generated result files when interpreting findings.

## Local inputs and use

The scripts expect the benchmark question and gold-result files under `geoquerybench_v0.1/`, and datasets under `database/A_subsurface/` and `database/B_surface/`. Those inputs are intentionally excluded from this repository. Install the Python dependencies used by the validators (including pandas, NumPy, GeoPandas, DuckDB, Matplotlib, and Pillow), then run from PowerShell:

```powershell
.\run_assigned_validation.ps1
```

The runner writes `validation_batch_summary.csv`, per-question logs under `validation_batch_logs/`, and rerun outputs under `validation_results/`; these generated files are not part of this contribution. The secondary checks are run individually with Python, for example `python manual_validation/secondary_validation/validate_NS3_020.py`.

The validators execute benchmark-provided reference code. Run them only with trusted benchmark inputs.