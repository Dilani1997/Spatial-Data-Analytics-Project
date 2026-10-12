# Known issues and future work

Status of the GeoQueryBench review workspace at the end of the CITS5206 capstone (Group 7), at commit `586c0ca`. Commit this file as `docs/KNOWN_ISSUES.md`. Move each row into a GitHub issue if work continues.

**What this repository is.** The client does not allow data to be shared because the database holds sensitive information. This repository is application code, tests and documentation only: no database, question CSV, result files, evidence or credentials. The natural-language-to-SQL code is included (PR #33) but ranks the client's validated queries, which are not shared, so it returns nothing without the data. A fresh clone launches the interface and shows a missing-data message; it cannot run the backend. The full system runs only in the passcode-protected hosted instance.

## Open issues

| ID | Type | Issue | Where | Proposed action | Status |
| --- | --- | --- | --- | --- | --- |
| KI-01 | Feature | No sample data, so a fresh clone cannot demonstrate any review flow. | `data/README.md`, `app.py` | Add a small synthetic sample dataset, manifest and result file, clearly marked as not client data. | Open |
| KI-02 | Bug | Seven interface strings contain corrupted characters from a text-encoding error (for example `Agreement sample (2â€“3 reviewers)`). | `geoquerybench/visuals.py` (six strings), `geoquerybench/config.py` (one) | Re-save as UTF-8 and restore the intended characters. | Open |
| KI-03 | Docs | The README structure lists `ASSIGNED_REVIEW.md`, `DEPENDENCY_NOTICE.md` and `REVIEW_TEMPLATE.md` under `docs/`, but they sit in the repository root. Setup commands are PowerShell only. | `README.md` | Move the files or correct the README. Add macOS and Linux commands. | Open |
| KI-04 | Gap | Some hosted features (JSON export, database backup download, adjudication and agreement pages) are not exposed in this repository's `app.py`, although adjudication, agreement, backup and bulk-export functions exist in `storage.py` and `navigation_reporting.py`. The deployed commit has not been confirmed. | `app.py` | Confirm the hosted commit and document any difference. | Open |
| KI-05 | Docs | The hosted Protocol page still refers to 233 questions while 824 are loaded. | Hosted build | Update the page text. | Open |
| KI-06 | Security | One shared passcode protects the app and the reviewer is chosen from a list in `TEAM_MEMBERS`, so identity is not authenticated per person. | `geoquerybench/security.py`, `geoquerybench/config.py` | Add per-reviewer accounts before wider deployment. | Open |
| KI-07 | Testing | The two tests in `tests/test_user_features.py` are pytest-style functions, so the `unittest` runner used by CI collects none of them (CI reports 37 tests before and after PR #33). Both pass when run directly. There are no automated interface tests or coverage measurement. | `tests/`, `.github/workflows/tests.yml` | Convert them to `unittest` (or add pytest to CI); add Streamlit `AppTest` flows and coverage. | Open |
| KI-08 | Data | 36 of 39 formal query error entries in the combined validation workbook are open, for example CD4-047 (fault length assigned by centroid, 513.33 km overstatement). | Combined error report | Client adjudication, agreed correction, independent retest before closing each entry. | Open |
| KI-09 | QA | Agreement evidence is thin: 11 questions had more than one reviewer and Cohen's kappa has not been computed. | Hosted Progress page | Run a planned agreement sample and compute kappa. | Open |
| KI-10 | Tooling | The GeoPandas validator exits with code 0 when the gold code crashes, so a batch summary can report PASS for a failed query (NS3-026, `NameError: name 'con' is not defined`). | Validation harness | Return a failing exit code and regenerate the batch summary. | Open |
| KI-11 | Data | No handling plan for the Chinese-language notes column in the gold dataset (acknowledged as open by the client). | Gold dataset | Agree a plan with the client. | Open |
| KI-12 | QA | Manual review of the four tabs added in PR #33 (Query accuracy, Natural language to SQL, Result accuracy, Model comparison) is outstanding. | `app.py` | Complete a manual walkthrough with approved test data. | Open |

## Future work

- Run queries inside the tool in a container sandbox with time, memory and file-access limits.
- Use DuckDB and Parquet for in-application querying, as the proposal planned.
- Add per-reviewer accounts, map overlays and side-by-side result comparison.
- Add a model leaderboard and an error-type dashboard.
- Evaluate the natural-language lookup with real, independently collected user questions.
- Extend to the subsurface domain if the client widens the scope.
