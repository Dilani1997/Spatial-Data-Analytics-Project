# Spatial Data Analytics Project — GeoQueryBench

This is the organised modular version of the Group 7 GeoQueryBench review application.

## Team module ownership

- **Sarwesh Kattel** — `geoquerybench/data_loader.py`
- **Dilani Gunathilaka Mapitigamage** — `geoquerybench/review_workflow.py`
- **Thomas Ouyang** — `geoquerybench/navigation_reporting.py`, `geoquerybench/visuals.py`
- **Ziyue Xu** — `geoquerybench/storage.py`
- **Chaitanya Neerukattu** — `app.py`, shared integration/configuration/security, repository structure, CI and final assembly

The app integrates the expanded 824-question review features: bilingual dataset validation, official-result lookup, Pass/Fail/Needs clarification policy, conditional evidence upload, reviewer-specific Save & Next / Resume, persistent review storage, safe result previews, assignments, progress and CSV exports.

## Correct structure

```text
Spatial-Data-Analytics-Project/
├── app.py
├── requirements.txt
├── smoke_test.py
├── .github/workflows/tests.yml
├── data/README.md
├── docs/
│   ├── ASSIGNED_REVIEW.md
│   ├── DEPENDENCY_NOTICE.md
│   ├── REVIEW_TEMPLATE.md
│   └── review_policy.md
├── geoquerybench/
│   ├── __init__.py
│   ├── config.py
│   ├── data_loader.py
│   ├── navigation_reporting.py
│   ├── review_visuals.py
│   ├── review_workflow.py
│   ├── security.py
│   ├── storage.py
│   └── visuals.py
├── runtime/.gitkeep
└── tests/
```

## Setup

Python 3.12 is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Data

By default expanded mode expects:

```text
data/geoquerybench_questions.csv
data/_manifest.csv
```

and the official result files referenced by `_manifest.csv` in the same data directory.

Alternatively set:

```powershell
$env:GQB_EXPANDED_QUESTIONS="C:\path\to\geoquerybench_questions.csv"
$env:GQB_GOLD_DIR="C:\path\to\official_results"
```

The review database defaults to `runtime/expanded_reviews.sqlite3`. Override with `GQB_EXPANDED_DB` if required.

## Optional passcode

```powershell
$env:GQB_APP_PASSWORD="your-private-passcode"
```

Without it, the current security helper runs in local demo mode. Use a private passcode for deployed/shared environments.

## Run

```powershell
streamlit run app.py
```

## Test

```powershell
python -m unittest discover -s tests -v
python smoke_test.py
```

## Important safety rule

The web application displays and compares supplied query/result artifacts. It does **not** execute uploaded SQL or Python code.
