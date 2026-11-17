import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from flask import Blueprint, current_app, jsonify, request, send_file
from werkzeug.utils import secure_filename
from app.database.connection import initialize_database, transaction
from app.services.cleaning import (
    clean_csv_file,
    clean_dataset,
    generate_quality_report,
    profile_file,
    profile_dataset,
    read_dataset,
    validate_cleaned_dataset,
    write_json,
)

datasets_bp = Blueprint("datasets", __name__)
ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls", "parquet"}
MAX_FILE_SIZE = 100 * 1024 * 1024


def __dataset_id_is_valid(dataset_id):
    return bool(re.fullmatch(r"[a-f0-9]{32}", dataset_id or ""))


def _raw_directory():
    path = Path(current_app.config["DATASET_UPLOAD_DIR"])
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_path():
    path = Path(current_app.config["DATASET_INDEX_PATH"])
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _quality_directory():
    path = Path(current_app.config["DATASET_QUALITY_REPORT_DIR"])
    path.mkdir(parents=True, exist_ok=True)
    return path


def _curated_directory():
    path = Path(current_app.config["DATASET_CURATED_DIR"])
    path.mkdir(parents=True, exist_ok=True)
    return path


def _dataset_record(dataset_id):
    return next((item for item in _read_index() if item.get("dataset_id") == dataset_id), None)


def _quality_report_path(dataset_id):
    return _quality_directory() / f"{dataset_id}_quality.json"


def _load_report(dataset_id):
    path = _quality_report_path(dataset_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        current_app.logger.exception("Unable to read quality report for %s", dataset_id)
        return None


def _read_index():
    path = _index_path()
    if not path.exists():
        return []
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
        return records if isinstance(records, list) else []
    except (OSError, json.JSONDecodeError):
        current_app.logger.exception("Unable to read dataset metadata index")
        return []


def _write_index(records):
    path = _index_path()
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(records, indent=2), encoding="utf-8")
    temporary.replace(path)


def _read_frame(path, extension, nrows=None):
    if extension == "csv":
        return pd.read_csv(path, nrows=nrows)
    if extension in {"xlsx", "xls"}:
        return pd.read_excel(path, nrows=nrows)
    if nrows is None:
        return pd.read_parquet(path)
    try:
        import pyarrow.parquet as parquet
        parquet_file = parquet.ParquetFile(path)
        batch = next(parquet_file.iter_batches(batch_size=nrows), None)
        return batch.to_pandas() if batch is not None else pd.DataFrame(columns=parquet_file.schema_arrow.names)
    except ImportError:
        return pd.read_parquet(path).head(nrows)


def _inspect_file(path, extension):
    if extension == "parquet":
        try:
            import pyarrow.parquet as parquet
            parquet_file = parquet.ParquetFile(path)
            metadata = parquet_file.metadata
            schema = parquet_file.schema_arrow
            columns = schema.names
            dtypes = {field.name: str(field.type) for field in schema}
            row_count = metadata.num_rows
            batch = next(parquet_file.iter_batches(batch_size=10), None)
            frame = batch.to_pandas() if batch is not None else pd.DataFrame(columns=columns)
        except ImportError:
            frame = pd.read_parquet(path).head(10)
            columns = list(frame.columns)
            dtypes = {name: str(dtype) for name, dtype in frame.dtypes.items()}
            row_count = len(pd.read_parquet(path))
        return row_count, columns, dtypes, frame

    if extension == "csv":
        sample = pd.read_csv(path, nrows=1000)
        columns = list(sample.columns)
        dtypes = {name: str(dtype) for name, dtype in sample.dtypes.items()}
        row_count = 0
        for chunk in pd.read_csv(path, usecols=columns, chunksize=100_000):
            row_count += len(chunk)
        return row_count, columns, dtypes, sample.head(10)

    frame = pd.read_excel(path)
    return len(frame), list(frame.columns), {name: str(dtype) for name, dtype in frame.dtypes.items()}, frame.head(10)


@datasets_bp.get("/datasets")
def list_datasets():
    records = [item for item in _read_index() if (_raw_directory() / item.get("stored_filename", "")).is_file()]
    return jsonify({"status": "success", "datasets": records, "count": len(records), "message": "Datasets loaded." if records else "No datasets are available."})


@datasets_bp.post("/datasets/upload")
def upload_dataset():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "Multipart form field 'file' is required."}), 400

    upload = request.files["file"]
    original_filename = Path(upload.filename or "").name
    if not original_filename:
        return jsonify({"status": "error", "message": "Choose a file to upload."}), 400

    safe_original = secure_filename(original_filename)
    extension = Path(safe_original).suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({"status": "error", "message": "Unsupported file type. Upload CSV, XLSX, XLS, or Parquet."}), 415

    dataset_id = uuid.uuid4().hex
    stored_filename = f"{dataset_id}_{safe_original}"
    destination = _raw_directory() / stored_filename
    try:
        upload.save(destination)
        file_size = destination.stat().st_size
        if file_size == 0:
            destination.unlink(missing_ok=True)
            return jsonify({"status": "error", "message": "The uploaded file is empty."}), 400
        if file_size > MAX_FILE_SIZE:
            destination.unlink(missing_ok=True)
            return jsonify({"status": "error", "message": "File exceeds the 100 MB upload limit."}), 413

        try:
            rows, columns, dtypes, _preview = _inspect_file(destination, extension)
        except Exception as exc:
            destination.unlink(missing_ok=True)
            current_app.logger.info("Dataset inspection failed: %s", exc)
            return jsonify({"status": "error", "message": "The file could not be read as a valid dataset. Check its format and contents."}), 422

        metadata = {
            "dataset_id": dataset_id,
            "original_filename": original_filename,
            "stored_filename": stored_filename,
            "file_format": extension,
            "file_size": file_size,
            "row_count": int(rows),
            "column_count": len(columns),
            "columns": columns,
            "data_types": dtypes,
            "upload_timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "ready",
        }
        records = _read_index()
        records.insert(0, metadata)
        _write_index(records)
        return jsonify({"status": "success", "dataset": metadata, "message": "Dataset uploaded and inspected successfully."}), 201
    except OSError:
        destination.unlink(missing_ok=True)
        current_app.logger.exception("Dataset upload could not be stored")
        return jsonify({"status": "error", "message": "The server could not store the uploaded file."}), 500


@datasets_bp.get("/datasets/<dataset_id>")
def get_dataset(dataset_id):
    record = _dataset_record(dataset_id)
    if not record or not (_raw_directory() / record["stored_filename"]).is_file():
        return jsonify({"status": "error", "message": f"Dataset '{dataset_id}' was not found."}), 404
    return jsonify({"status": "success", "dataset": record})


@datasets_bp.get("/datasets/<dataset_id>/preview")
def preview_dataset(dataset_id):
    record = _dataset_record(dataset_id)
    if not record:
        return jsonify({"status": "error", "message": f"Dataset '{dataset_id}' was not found."}), 404
    path = _raw_directory() / record["stored_filename"]
    if not path.is_file():
        return jsonify({"status": "error", "message": f"Dataset '{dataset_id}' file is missing."}), 404
    try:
        frame = _read_frame(path, record["file_format"], nrows=10)
        records = json.loads(frame.to_json(orient="records", date_format="iso"))
        return jsonify({
            "status": "success", "dataset_id": dataset_id,
            "columns": record["columns"], "data_types": record["data_types"],
            "records": records,
        })
    except Exception:
        current_app.logger.exception("Dataset preview failed")
        return jsonify({"status": "error", "message": "The dataset preview could not be read."}), 422


@datasets_bp.delete("/datasets/<dataset_id>")
def delete_dataset(dataset_id):
    records = _read_index()
    record = next((item for item in records if item.get("dataset_id") == dataset_id), None)
    if not record:
        return jsonify({"status": "error", "message": f"Dataset '{dataset_id}' was not found."}), 404
    raw_path = _raw_directory() / record["stored_filename"]
    curated_path = _curated_directory() / f"{dataset_id}_cleaned.csv"
    quality_path = _quality_report_path(dataset_id)
    transformed_directory = Path(current_app.config["DATASET_TRANSFORMED_DIR"])
    # Standardised files name exactly one source. Integrated outputs can be
    # shared by several sources, so preserve those files and their audit trail.
    owned_transformed = list(transformed_directory.glob(f"*_{dataset_id}_standardised.*"))
    database_path = current_app.config["SQLITE_PATH"]
    try:
        initialize_database(database_path)
        with transaction(database_path) as conn:
            conn.execute("DELETE FROM data_quality_logs WHERE dataset_id=?", (dataset_id,))
            conn.execute("DELETE FROM water_metrics WHERE dataset_id=?", (dataset_id,))
            conn.execute("DELETE FROM load_history WHERE dataset_id=?", (dataset_id,))
            conn.execute("DELETE FROM datasets WHERE dataset_id=?", (dataset_id,))
            conn.execute("DELETE FROM locations WHERE NOT EXISTS (SELECT 1 FROM water_metrics WHERE water_metrics.location_id=locations.location_id)")
            integrity = conn.execute("PRAGMA foreign_key_check").fetchall()
            if integrity:
                raise RuntimeError("Foreign-key integrity check failed during dataset deletion.")
            # Keep the metadata index in step with the SQL transaction. If
            # SQLite cannot commit, the except path restores the prior index.
            _write_index([item for item in records if item.get("dataset_id") != dataset_id])
    except Exception:
        try:
            _write_index(records)
        except OSError:
            current_app.logger.exception("Unable to restore dataset metadata after deletion rollback")
        current_app.logger.exception("Dataset deletion failed")
        return jsonify({"status": "error", "message": "The dataset could not be deleted."}), 500
    cleanup_failed = []
    # These paths are dataset-owned by their generated names. Shared
    # integration outputs do not include a dataset ID and are left untouched.
    for path in [raw_path, curated_path, quality_path, *owned_transformed]:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            cleanup_failed.append(path.name)
            current_app.logger.exception("Unable to remove dataset artifact %s", path)
    return jsonify({"status": "success", "dataset_id": dataset_id,
                    "cleanup_warnings": cleanup_failed,
                    "message": "Dataset and its owned analytical records were deleted."})


@datasets_bp.post("/datasets/<dataset_id>/quality-check")
def run_quality_check(dataset_id):
    record = _dataset_record(dataset_id)
    if not record:
        return jsonify({"status": "error", "message": f"Dataset '{dataset_id}' was not found."}), 404
    raw_path = _raw_directory() / record["stored_filename"]
    if not raw_path.is_file():
        return jsonify({"status": "error", "message": "The original dataset file is missing."}), 404
    try:
        profile = profile_file(raw_path, record["file_format"])
        report = _load_report(dataset_id) or {"dataset_id": dataset_id, "cleaning_history": []}
        report["latest_quality_check"] = {"checked_at": datetime.now(timezone.utc).isoformat(), "profile": profile}
        history = report.setdefault("cleaning_history", [])
        history.append({"operation": "quality_check", "timestamp": report["latest_quality_check"]["checked_at"], "summary": {"rows": profile["total_rows"], "columns": profile["total_columns"], "missing_values": profile["missing_value_count"], "duplicates": profile["duplicate_row_count"]}})
        write_json(_quality_report_path(dataset_id), report)
        return jsonify({"status": "success", "dataset_id": dataset_id, "profile": profile, "message": "Data quality assessment completed."})
    except Exception:
        current_app.logger.exception("Quality assessment failed for %s", dataset_id)
        return jsonify({"status": "error", "message": "The dataset could not be profiled. Check the file and required format support."}), 422


@datasets_bp.get("/datasets/<dataset_id>/quality-report")
def quality_report(dataset_id):
    if not _dataset_record(dataset_id):
        return jsonify({"status": "error", "message": f"Dataset '{dataset_id}' was not found."}), 404
    report = _load_report(dataset_id)
    if not report:
        return jsonify({"status": "error", "message": "No quality report is available. Run a quality check first."}), 404
    return jsonify({"status": "success", "report": report})


@datasets_bp.post("/datasets/<dataset_id>/clean")
def clean_uploaded_dataset(dataset_id):
    record = _dataset_record(dataset_id)
    if not record:
        return jsonify({"status": "error", "message": f"Dataset '{dataset_id}' was not found."}), 404
    raw_path = _raw_directory() / record["stored_filename"]
    if not raw_path.is_file():
        return jsonify({"status": "error", "message": "The original dataset file is missing."}), 404
    cleaned_filename = f"{dataset_id}_cleaned.csv"
    cleaned_path = _curated_directory() / cleaned_filename
    temporary_path = cleaned_path.with_suffix(".csv.tmp")
    try:
        if record["file_format"] == "csv":
            before, after, operations, validation = clean_csv_file(raw_path, temporary_path)
            temporary_path.replace(cleaned_path)
        else:
            original = read_dataset(raw_path, record["file_format"])
            before = profile_dataset(original)
            cleaned, operations = clean_dataset(original)
            validation = validate_cleaned_dataset(cleaned)
            cleaned.to_csv(temporary_path, index=False)
            temporary_path.replace(cleaned_path)
            after = profile_dataset(cleaned)
        report = generate_quality_report(before, after, operations, validation, dataset_id, cleaned_filename)
        previous = _load_report(dataset_id) or {}
        report["latest_quality_check"] = previous.get("latest_quality_check")
        history = previous.get("cleaning_history", [])
        history.append({"operation": "clean", "timestamp": report["generated_at"], "cleaned_filename": cleaned_filename, "validation": validation, "operations": operations})
        report["cleaning_history"] = history
        write_json(_quality_report_path(dataset_id), report)
        return jsonify({"status": "success", "report": report, "message": "Cleaning completed. The original upload was not modified."})
    except Exception:
        temporary_path.unlink(missing_ok=True)
        current_app.logger.exception("Dataset cleaning failed for %s", dataset_id)
        return jsonify({"status": "error", "message": "The dataset could not be cleaned. The original upload was preserved."}), 422


@datasets_bp.get("/datasets/<dataset_id>/cleaned-preview")
def cleaned_preview(dataset_id):
    if not _dataset_record(dataset_id):
        return jsonify({"status": "error", "message": f"Dataset '{dataset_id}' was not found."}), 404
    report = _load_report(dataset_id)
    if not report or not report.get("cleaned_filename"):
        return jsonify({"status": "error", "message": "No cleaned dataset is available. Clean the dataset first."}), 404
    path = _curated_directory() / report["cleaned_filename"]
    if not path.is_file():
        return jsonify({"status": "error", "message": "The cleaned dataset file is missing."}), 404
    try:
        frame = pd.read_csv(path, nrows=10)
        records = json.loads(frame.to_json(orient="records", date_format="iso"))
        return jsonify({"status": "success", "dataset_id": dataset_id, "columns": list(frame.columns), "data_types": {str(name): str(dtype) for name, dtype in frame.dtypes.items()}, "records": records})
    except Exception:
        current_app.logger.exception("Cleaned dataset preview failed for %s", dataset_id)
        return jsonify({"status": "error", "message": "The cleaned dataset preview could not be read."}), 422


@datasets_bp.get("/datasets/<dataset_id>/download-cleaned")
def download_cleaned(dataset_id):
    if not __dataset_id_is_valid(dataset_id):
        return jsonify({"status": "error", "message": "Invalid dataset ID."}), 400
    if not _dataset_record(dataset_id):
        return jsonify({"status": "error", "message": f"Dataset '{dataset_id}' was not found."}), 404
    report = _load_report(dataset_id)
    if not report or not report.get("cleaned_filename"):
        return jsonify({"status": "error", "message": "No cleaned CSV is available. Clean the dataset first."}), 404
    expected = f"{dataset_id}_cleaned.csv"
    if report["cleaned_filename"] != expected:
        return jsonify({"status": "error", "message": "The cleaned file metadata is invalid."}), 400
    root = _curated_directory().resolve()
    path = (root / expected).resolve()
    if path.parent != root or not path.is_file():
        return jsonify({"status": "error", "message": "The cleaned CSV file is missing. Run cleaning again."}), 404
    return send_file(path, mimetype="text/csv; charset=utf-8", as_attachment=True, download_name=expected, conditional=True)


@datasets_bp.get("/datasets/<dataset_id>/cleaning-history")
def cleaning_history(dataset_id):
    if not _dataset_record(dataset_id):
        return jsonify({"status": "error", "message": f"Dataset '{dataset_id}' was not found."}), 404
    report = _load_report(dataset_id) or {}
    return jsonify({"status": "success", "dataset_id": dataset_id, "history": report.get("cleaning_history", [])})
