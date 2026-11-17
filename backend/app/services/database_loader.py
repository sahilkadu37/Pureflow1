"""Load only standardised files from transformed storage into the analytics schema."""
from datetime import datetime, timezone
from contextlib import contextmanager
import json
from pathlib import Path
import re

import pandas as pd

from app.database.connection import database_path, initialize_database, transaction

MAPPINGS = {
    "id": "source_record_id", "publisher": "publisher", "metric": "metric_type",
    "scope": "scope", "facility_or_region": "place_name", "country": "country",
    "period": "measurement_period", "wue_l_per_kwh": "wue_l_per_kwh",
    "withdrawal_million_gal": "withdrawal_million_gal",
    "discharge_million_gal": "discharge_million_gal",
    "consumption_million_gal": "consumption_million_gal",
    "consumption_million_litres": "consumption_million_litres",
    "energy_wh_per_prompt": "energy_wh_per_prompt", "water_ml_per_prompt": "water_ml_per_prompt",
    "water_million_litres": "water_million_litres", "water_scope": "water_scope",
}
MEASURES = (
    "wue_l_per_kwh", "withdrawal_million_gal", "discharge_million_gal",
    "consumption_million_gal", "consumption_million_litres",
    "energy_wh_per_prompt", "water_ml_per_prompt", "water_million_litres",
)


class LoadError(ValueError):
    def __init__(self, message, status_code=422, report=None):
        super().__init__(message)
        self.status_code = status_code
        self.report = report


@contextmanager
def _audited_transaction(path, dataset_id, source_name, transformed_name, read_count, rejected_count, duplicate_count, loaded_at):
    try:
        with transaction(path) as conn:
            yield conn
    except Exception as error:
        # The data transaction has rolled back; write the failed attempt separately.
        with transaction(path) as conn:
            conn.execute("INSERT INTO load_history(dataset_id,source_filename,transformed_filename,records_read,records_inserted,records_rejected,duplicate_records,loaded_at,load_status,message) VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (dataset_id, source_name, transformed_name, read_count, 0, rejected_count, duplicate_count,
                          loaded_at, "failed", f"Transaction rolled back ({type(error).__name__})."))
        raise


def _read_transformed(path):
    ext = path.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(path)
    if ext in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if ext == ".parquet":
        return pd.read_parquet(path)
    raise LoadError("Only transformed CSV, Excel, and Parquet files can be loaded.", 415)


def _year(value):
    match = re.fullmatch(r"\s*(\d{4})\s*", str(value or ""))
    return int(match.group(1)) if match else None


def _month(value):
    parsed = pd.to_datetime(str(value or ""), format="%B %Y", errors="coerce")
    if pd.isna(parsed):
        parsed = pd.to_datetime(str(value or ""), format="%b %Y", errors="coerce")
    if pd.isna(parsed):
        parsed = pd.to_datetime(str(value or ""), format="%Y-%m", errors="coerce")
    return parsed.strftime("%Y-%m") if not pd.isna(parsed) else None


def _index_record(dataset_id, index_path):
    try:
        records = json.loads(Path(index_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        records = []
    return next((r for r in records if r.get("dataset_id") == dataset_id), None)


def find_transformed(dataset_id, transformed_dir):
    directory = Path(transformed_dir).resolve()
    matches = sorted(
        (p for p in directory.glob(f"*_{dataset_id}_standardised.*")
         if p.suffix.lower() in {".csv", ".xlsx", ".xls", ".parquet"} and p.is_file()),
        key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True,
    )
    if not matches:
        raise LoadError("No standardised transformed file exists for this dataset. Run the transformation workflow first.", 404)
    return matches[0]


def inspect_dataset(dataset_id, transformed_dir, index_path):
    record = _index_record(dataset_id, index_path)
    if not record:
        raise LoadError("Dataset metadata was not found.", 404)
    path = find_transformed(dataset_id, transformed_dir)
    frame = _read_transformed(path)
    return {
        "dataset_id": dataset_id, "source_filename": record.get("original_filename", dataset_id),
        "transformed_filename": path.name, "records_read": int(len(frame)),
        "columns": [{"name": str(c), "dtype": str(frame[c].dtype), "mapped_to": MAPPINGS.get(str(c))} for c in frame.columns],
        "has_required_fields": {name: name in frame.columns for name in ("id", "facility_or_region")},
    }


def load_dataset(dataset_id, transformed_dir, index_path, *, path=None, reload=False, batch_size=1000):
    initialize_database(path)
    record = _index_record(dataset_id, index_path)
    if not record:
        raise LoadError("Dataset metadata was not found.", 404)
    source = find_transformed(dataset_id, transformed_dir)
    frame = _read_transformed(source)
    required = {"id", "facility_or_region"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise LoadError("Transformed file is missing required mapped fields.", report={"missing_columns": missing})
    mapped = {source_name: target for source_name, target in MAPPINGS.items() if source_name in frame.columns}
    if not set(MEASURES).intersection(mapped.values()):
        raise LoadError("No supported water or efficiency measurement columns are present.")
    # Convert only declared numeric measures; invalid values become visible rejections.
    work = frame.rename(columns=mapped).copy()
    for column in MEASURES:
        if column in work:
            work[column] = pd.to_numeric(work[column], errors="coerce")
    for column in ("publisher", "metric_type", "scope", "measurement_period", "water_scope", "place_name", "country", "source_record_id"):
        if column in work:
            work[column] = work[column].astype("string").str.strip().replace("", pd.NA)
    exact_duplicates = int(work.duplicated(keep="first").sum())
    work = work.drop_duplicates(keep="first")
    valid = work["source_record_id"].notna() & work["place_name"].notna()
    measure_columns = [c for c in MEASURES if c in work]
    valid &= work[measure_columns].notna().any(axis=1)
    rejected = work.loc[~valid]
    accepted = work.loc[valid]
    loaded_at = datetime.now(timezone.utc).isoformat()
    source_name = record.get("original_filename", source.name)
    reload = bool(reload)
    with _audited_transaction(path, dataset_id, source_name, source.name, len(frame), len(rejected), exact_duplicates, loaded_at) as conn:
        exists = conn.execute("SELECT 1 FROM datasets WHERE dataset_id=?", (dataset_id,)).fetchone()
        if exists and not reload:
            prior = conn.execute("SELECT record_count FROM datasets WHERE dataset_id=?", (dataset_id,)).fetchone()
            report = {"dataset_id": dataset_id, "records_read": len(frame), "records_inserted": 0,
                      "records_rejected": 0, "duplicate_records": len(frame), "loaded_at": loaded_at,
                      "status": "skipped_duplicate", "message": "Dataset is already loaded. Set reload=true with explicit confirmation to replace it.",
                      "existing_records": prior[0]}
            conn.execute("INSERT INTO load_history(dataset_id,source_filename,transformed_filename,records_read,records_inserted,records_rejected,duplicate_records,loaded_at,load_status,message) VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (dataset_id, source_name, source.name, len(frame), 0, 0, len(frame), loaded_at, report["status"], report["message"]))
            return report
        if exists:
            conn.execute("DELETE FROM datasets WHERE dataset_id=?", (dataset_id,))
        conn.execute("INSERT INTO datasets(dataset_id,dataset_name,source_filename,transformed_filename,source_type,source_record_count,record_count,upload_date,loaded_at,processing_status) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (dataset_id, Path(source_name).stem, source_name, source.name, record.get("file_format", source.suffix[1:]), len(frame), len(accepted), record.get("upload_timestamp"), loaded_at, "loaded_with_rejections" if len(rejected) or exact_duplicates else "loaded"))
        sql = """INSERT INTO water_metrics(dataset_id,location_id,source_record_id,publisher,metric_type,scope,measurement_period,measurement_month,reporting_year,wue_l_per_kwh,withdrawal_million_gal,discharge_million_gal,consumption_million_gal,consumption_million_litres,energy_wh_per_prompt,water_ml_per_prompt,water_million_litres,water_scope) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
        for start in range(0, len(accepted), max(1, int(batch_size))):
            batch = accepted.iloc[start:start + max(1, int(batch_size))]
            records = batch.to_dict("records")
            location_keys = set()
            for row in records:
                place = str(row["place_name"])
                country = row.get("country")
                location_keys.add((place, None if pd.isna(country) else str(country)))
            conn.executemany("INSERT OR IGNORE INTO locations(place_name,country) VALUES(?,?)", sorted(location_keys))
            location_ids = {(place, country): conn.execute(
                "SELECT location_id FROM locations WHERE lower(trim(place_name))=lower(trim(?)) AND country IS ?", (place, country)
            ).fetchone()[0] for place, country in location_keys}
            metric_rows = []
            for row in records:
                place = str(row["place_name"])
                country = row.get("country")
                country = None if pd.isna(country) else str(country)
                location_id = location_ids[(place, country)]
                values = [row.get(c) for c in MEASURES]
                values = [None if pd.isna(v) else float(v) for v in values]
                metric_rows.append((dataset_id, location_id, str(row["source_record_id"]),
                    None if pd.isna(row.get("publisher")) else str(row.get("publisher")),
                    None if pd.isna(row.get("metric_type")) else str(row.get("metric_type")),
                    None if pd.isna(row.get("scope")) else str(row.get("scope")),
                    None if pd.isna(row.get("measurement_period")) else str(row.get("measurement_period")),
                    _month(row.get("measurement_period")),
                    _year(row.get("measurement_period")), *values,
                    None if pd.isna(row.get("water_scope")) else str(row.get("water_scope"))))
            conn.executemany(sql, metric_rows)
        if len(rejected):
            conn.execute("INSERT INTO data_quality_logs(dataset_id,quality_metric,issue_count,report_date,details) VALUES(?,?,?,?,?)",
                         (dataset_id, "records_rejected", len(rejected), loaded_at, "Missing source record ID, place name, or all supported water measurements."))
        if exact_duplicates:
            conn.execute("INSERT INTO data_quality_logs(dataset_id,quality_metric,issue_count,report_date,details) VALUES(?,?,?,?,?)",
                         (dataset_id, "exact_duplicate_records", exact_duplicates, loaded_at, "Exact duplicate transformed rows skipped."))
        status = "loaded_with_rejections" if len(rejected) or exact_duplicates else "loaded"
        report = {"dataset_id": dataset_id, "source_filename": source_name, "transformed_filename": source.name,
                  "records_read": int(len(frame)), "records_inserted": int(len(accepted)),
                  "records_rejected": int(len(rejected)), "duplicate_records": exact_duplicates,
                  "loaded_at": loaded_at, "status": status, "message": "Load completed transactionally."}
        conn.execute("INSERT INTO load_history(dataset_id,source_filename,transformed_filename,records_read,records_inserted,records_rejected,duplicate_records,loaded_at,load_status,message) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (dataset_id, source_name, source.name, len(frame), len(accepted), len(rejected), exact_duplicates, loaded_at, status, report["message"]))
    return report
