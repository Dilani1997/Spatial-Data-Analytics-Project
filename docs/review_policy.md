# Expanded review policy

The review-policy helpers are defined in
`geoquerybench/review_workflow.py`.

## Decision requirements

| Decision            | Official output required | Reviewer confirmation required | Evidence upload required | Explanation required |
| ------------------- | ------------------------ | ------------------------------ | ------------------------ | -------------------- |
| Not assessed        | No                       | No                             | No                       | No                   |
| Pass                | Yes                      | Yes                            | No                       | No                   |
| Fail                | Yes                      | No                             | Yes                      | Yes                  |
| Needs clarification | No                       | No                             | Optional                 | Yes                  |

Reviewer confirmation for Pass means the reviewer independently
executed the query and compared its output with the official result.

Empty, whitespace-only and None explanations are rejected when
an explanation is required.

## Helper functions

- `review_errors(...)` returns validation messages.
  An empty list means the supplied decision satisfies these rules.
- `verdict_is_complete(...)` identifies Pass and Fail labels.
  It does not check whether their evidence requirements are satisfied.
- `evidence_required(...)` returns True for Fail.
- `upload_visible(...)` returns True for Fail and Needs clarification.

## Integration requirements

The application's save handler must call `review_errors(...)`
before saving and block saving if any errors are returned.

Only count a review as completed when validation succeeds and
`verdict_is_complete(...)` returns True.

Not assessed and Needs clarification remain pending.

The interface must use `upload_visible(...)` to control uploader
visibility. Upload size, file type and durable storage must be
validated separately; these helpers only receive an upload-presence flag.

These helpers validate review metadata. They do not execute queries
or automatically compare result files.

## Tests

Run from the repository root with the project dependencies installed:

```powershell
python -m unittest tests.test_expanded_review_workflow -v
```

The current suite contains 10 test methods covering verdicts,
completion status, upload rules and decision validation.
