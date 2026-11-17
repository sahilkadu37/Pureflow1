# PureFlow data pipeline

## 1. Upload and inspection

The dataset API accepts CSV, XLSX, XLS, and Parquet uploads, records source filename, type, columns, dtypes, row count, and upload time in the dataset index, and stores uploaded data in `backend/data/raw/`. Uploads are not automatically treated as transformed or database-ready.

## 2. Quality assessment and cleaning

The cleaning service profiles columns, missing values, duplicates, invalid values, and data types. Cleaning preserves missing observations and flags values that cannot be safely repaired. It does not fill missing measurements or convert units without unambiguous metadata. Curated outputs are written separately under `backend/data/curated/`; raw uploads remain intact.

For the loaded source, the quality report records 85 rows before and after cleaning, 569 missing cells across 21 columns, 68.1232% completeness, and no exact duplicates. Cleaning validation did not fully pass: 25 `source_date` values were not parseable and 7 `water_scope` values failed the established numerical check. These source values were preserved and reported.

## 3. Transformation and integration

The transformation service inspects curated datasets, standardises names and types, and writes transformed output plus a report under `backend/data/transformed/`. Integration only uses user-selected keys and join type. Existing validation warnings are retained in reports; a transformed file is not silently described as fully validated when its checks failed.

The loaded file contains 85 standardised rows. Its latest standardisation report has warnings for incomplete country values, non-date `source_date` entries, and `water_scope` validation. Database loading applies its own explicit schema checks: a row must contain a source ID, place label, and at least one supported numeric measure. For this source, all 85 rows met those insertion requirements.

## 4. SQLite loading

The loader searches only standardised outputs in transformed storage for the requested upload dataset ID. It maps known source columns explicitly, retains provenance, uses parameterized batched inserts, and commits the dataset and metrics in a transaction. Exact duplicate rows are counted and skipped. Rows that fail required field checks are counted and written to quality logs. A failed transaction is rolled back and its failed attempt is recorded separately. Existing dataset rows are replaced only through the explicit confirmed reload flow.

The current load inserted 85/85 records, with no rejected or exact duplicate rows. There are 74 distinct location labels; these labels are not asserted to be 74 individual data centres.

## 5. Analytics and reports

The dashboard and analytics APIs query SQLite. Report filters include selected loaded dataset IDs, source period year (via from/to date controls), and a substring search over stored place labels and country codes. Date filtering is year-granular because many source periods are annual or descriptive rather than full dates. Reports include dataset sources, cleaning/transformation summaries, database validation, SQL-derived findings, transparent recommendations, limitations, and export history.

Reports are stored in application-managed UUID directories. Download paths are derived from a validated report ID and one of the fixed formats `pdf`, `csv`, or `json`; clients cannot choose a filesystem path.
