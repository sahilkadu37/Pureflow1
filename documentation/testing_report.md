# PureFlow Testing Report

**Run date:** 2026-11-14  
**Backend command:** `PYTHONPATH=backend python -m unittest discover -s backend\tests -v`  
**Frontend commands:** `npm.cmd run build`, `npm.cmd run lint` (from `frontend/`).

## Results

| Check | Result | Evidence |
|---|---|---|
| Backend unit/integration suite | PASS | 20 tests, 3.341 seconds |
| Actual-source E2E pipeline | PASS | Included in suite; actual 85-row CSV, isolated temporary outputs |
| Frontend production build | PASS with advisory | Vite 8.3.8; 2,962 modules; JS 963.14 kB (285.90 kB gzip), CSS 64.23 kB |
| Frontend lint | Exit 0, warnings | 16 warnings: React effect/state and component declaration patterns plus one unused variable |
| Real DB integrity/FK/key checks | PASS | `integrity_check=['ok']`; no FK violations, duplicate keys, null required keys, or count mismatches |
| Real-source preservation | PASS | Original CSV SHA-256 matched before/after the E2E workflow |
| Live HTTP smoke | PASS, limited | Flask health/dashboard/report overview and Vite root/module responses returned 200 in the earlier phase smoke check; servers stopped afterward |

## Automated coverage

The actual-source E2E test covers upload, listing, detail, preview, quality check/report, cleaning, cleaned preview/history, transformation compatibility and standardisation, transformation history/report, database loading/status/tables/schema/load-history/transformed-datasets/validation, dashboard, all SQL analytics paths, safe custom SELECT, report overview/insights/recommendations/sustainability/history, and PDF/CSV/JSON download. It also checks upload errors (missing file, unsupported extension, malformed workbook, oversized request), missing dataset and transformation parameters, filename path sanitisation, and CORS allowlisting. Dataset deletion is intentionally not invoked in the real-source workflow.

Other backend tests cover normalized schema and FK enforcement, duplicate load prevention/reload confirmation, transaction rollback, data validation/aggregates, read-only custom SQL rejection, report filtering/export/error cases, and standardisation/integration behavior with curated examples.

## Real data pipeline outcome

- Source: `backend/data/raw/1cced4863e37452db38f10683ed66961_data-center-water.csv`.
- Input size: 33,794 bytes; 85 rows.
- E2E: upload and source-hash preservation passed; quality profile reported 85 rows; cleaning and standardisation wrote only under the temporary test workspace; SQLite load inserted 85 records; report generation/download succeeded in all three formats.
- Integration returned the expected 400 because the isolated run has only one source dataset.
- Dataset-specific runtime climate and water-stress observations were unavailable; those API paths returned successfully with empty-data responses.

## Database snapshot

The checked-in SQLite database contains `datasets`, `locations`, `water_metrics`, `load_history`, and `data_quality_logs`. Validation confirmed one dataset with `source_record_count=85`, `record_count=85`, and `actual_records=85`; latest successful load read 85, rejected 0, duplicate 0. `PRAGMA integrity_check` returned `ok`; `PRAGMA foreign_key_check` returned no rows. Primary-key groups, required key null checks, and uniqueness checks all passed.

## Not covered

- No browser automation, accessibility audit, or cross-browser/device testing.
- No large-file or concurrent-user stress/load benchmark.
- No production deployment, TLS, authentication, or authorization test.
- No successful multi-source integration run, because the available project data does not provide a second compatible curated source.
- No destructive source deletion against the actual workspace database or source files.
