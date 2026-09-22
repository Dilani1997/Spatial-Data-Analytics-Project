# Ziyue Xu — Storage and History Review

## Assigned files

- `geoquerybench/storage.py`
- `tests/test_storage.py`

## Required checks

1. Create a clean SQLite database.
2. Save and update the same review.
3. Confirm the current review shows the latest decision.
4. Confirm every version remains in review history.
5. Test assignments, question settings, adjudications and backups.
6. Check reviewer attribution and storage diagnostics.

## Command

```bash
python -m unittest tests.test_storage -v
```

The modular review already corrected deterministic history ordering. Retest that versions appear newest first.

Suggested branch: `review/ziyue-storage-history`

Record the result using `REVIEW_TEMPLATE.md`.
