"""Conservative data profiling and cleaning for uploaded PureFlow datasets."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

DATE_TOKENS = ("date", "time", "timestamp")
NONNEGATIVE_TOKENS = ("water", "wue", "consumption", "usage")
NUMERIC_TOKENS = NONNEGATIVE_TOKENS + ("temperature", "humidity", "latitude", "longitude")
CSV_CHUNK_SIZE = 50_000
IDENTIFIER_TOKENS = {"id", "code", "zip", "postal", "phone"}


def _missing_mask(series):
    mask = series.isna()
    if pd.api.types.is_object_dtype(series.dtype) or pd.api.types.is_string_dtype(series.dtype):
        mask = mask | series.astype("string").str.strip().eq("").fillna(False)
    return mask


def _csv_identifier_dtypes(path):
    columns = pd.read_csv(path, nrows=0).columns
    return {
        column: "string"
        for column in columns
        if set(re.split(r"[^a-z0-9]+", str(column).lower())) & IDENTIFIER_TOKENS
    }


def profile_file(path, file_format):
    """Profile CSV files in bounded chunks; use format readers for other types."""
    if file_format != "csv":
        return profile_dataset(read_dataset(path, file_format))

    identifier_dtypes = _csv_identifier_dtypes(path)
    header = pd.read_csv(path, nrows=0)
    rows = 0
    memory_bytes = 0
    missing_counts = {}
    unique_sets = {}
    dtype_sets = {}
    duplicate_hashes = set()
    duplicate_count = 0
    invalid_counts = {}
    whitespace_counts = {}
    columns = [str(column) for column in header.columns]
    missing_counts = {name: 0 for name in columns}
    unique_sets = {name: set() for name in columns}
    dtype_sets = {name: set() for name in columns}
    for chunk in pd.read_csv(path, chunksize=CSV_CHUNK_SIZE, dtype=identifier_dtypes):
        rows += len(chunk)
        memory_bytes += int(chunk.memory_usage(index=True, deep=True).sum())
        for column in chunk.columns:
            name = str(column)
            series = chunk[column]
            missing_counts[name] += int(_missing_mask(series).sum())
            unique_sets[name].update(series.loc[~_missing_mask(series)].unique().tolist())
            dtype_sets[name].add(str(series.dtype))
            if pd.api.types.is_object_dtype(series.dtype) or pd.api.types.is_string_dtype(series.dtype):
                text = series.dropna().astype("string")
                whitespace_counts[name] = whitespace_counts.get(name, 0) + int(text.ne(text.str.strip()).sum())
        hashes = pd.util.hash_pandas_object(chunk, index=False)
        for hashed in hashes:
            value = int(hashed)
            if value in duplicate_hashes:
                duplicate_count += 1
            else:
                duplicate_hashes.add(value)
        invalid = detect_invalid_values(chunk)
        for name, item in invalid.items():
            key = f"{name}|{item['kind']}"
            invalid_counts[key] = invalid_counts.get(key, 0) + item["count"]

    cells = rows * len(columns)
    missing_total = sum(missing_counts.values())
    invalid_values = {}
    for key, count in invalid_counts.items():
        name, kind = key.rsplit("|", 1)
        invalid_values[name] = {"count": count, "kind": kind}
    missing = {name: {"count": count, "percentage": round(count / rows * 100, 4) if rows else None} for name, count in missing_counts.items()}
    inconsistent = {"whitespace_values": {name: count for name, count in whitespace_counts.items() if count}, "invalid_date_values": {}}
    # Invalid date counts are already included in invalid_values.
    column_types = {
        name: next(iter(values)) if len(values) == 1 else "mixed" if values else "unknown"
        for name, values in dtype_sets.items()
    }
    type_summary = {}
    for dtype in column_types.values():
        type_summary[dtype] = type_summary.get(dtype, 0) + 1
    return {
        "total_rows": rows, "total_columns": len(columns), "missing_values": missing,
        "missing_value_count": missing_total,
        "missing_value_percentage": round(missing_total / cells * 100, 4) if cells else None,
        "duplicate_row_count": duplicate_count,
        "data_types": {"columns": column_types, "summary": type_summary},
        "unique_values": {name: len(values) for name, values in unique_sets.items()},
        "invalid_values": invalid_values, "inconsistent_formats": inconsistent,
        "memory_usage_bytes": memory_bytes,
        "overall_completeness_percentage": round((cells - missing_total) / cells * 100, 4) if cells else None,
    }


def detect_missing_values(frame):
    rows = len(frame)
    result = {}
    counts = {column: int(_missing_mask(frame[column]).sum()) for column in frame.columns}
    for column, count in counts.items():
        result[str(column)] = {
            "count": int(count),
            "percentage": round(float(count / rows * 100), 4) if rows else None,
        }
    return result


def detect_duplicates(frame):
    duplicate_mask = frame.duplicated(keep="first")
    return {"duplicate_rows": int(duplicate_mask.sum()), "affected_rows": int(duplicate_mask.sum())}


def detect_invalid_values(frame):
    invalid = {}
    lowered = {column: str(column).strip().lower() for column in frame.columns}
    for column in frame.columns:
        name = lowered[column]
        series = frame[column]
        invalid_count = 0
        kind = None
        if any(token in name for token in DATE_TOKENS):
            values = series.loc[~_missing_mask(series)]
            if len(values):
                parsed = pd.to_datetime(values, errors="coerce", format="mixed")
                invalid_count = int(parsed.isna().sum())
                kind = "invalid_dates"
        elif any(token in name for token in NUMERIC_TOKENS) or set(name.split("_")) & {"lat", "lon", "lng"} or pd.api.types.is_numeric_dtype(series.dtype):
            numeric = pd.to_numeric(series, errors="coerce")
            nonempty = series.notna() & series.astype("string").str.strip().ne("")
            invalid_mask = nonempty & numeric.isna()
            finite = pd.Series(np.isfinite(numeric.to_numpy(dtype=np.float64, na_value=np.nan)), index=series.index)
            invalid_mask |= nonempty & ~finite
            if any(token in name for token in NONNEGATIVE_TOKENS):
                invalid_mask |= numeric.lt(0).fillna(False)
            if "latitude" in name or name in {"lat", "latitude"}:
                invalid_mask |= numeric.lt(-90).fillna(False) | numeric.gt(90).fillna(False)
            if "longitude" in name or name in {"lon", "lng", "longitude"}:
                invalid_mask |= numeric.lt(-180).fillna(False) | numeric.gt(180).fillna(False)
            invalid_count = int(invalid_mask.sum())
            kind = "invalid_numerical_values"
        if invalid_count:
            invalid[str(column)] = {"count": invalid_count, "kind": kind}
    return invalid


def _invalid_rows_count(frame):
    affected = pd.Series(False, index=frame.index)
    for column in frame.columns:
        name = str(column).strip().lower()
        series = frame[column]
        if any(token in name for token in DATE_TOKENS):
            present = ~_missing_mask(series)
            invalid = present & pd.to_datetime(series, errors="coerce", format="mixed").isna()
        elif any(token in name for token in NUMERIC_TOKENS) or set(name.split("_")) & {"lat", "lon", "lng"} or pd.api.types.is_numeric_dtype(series.dtype):
            numeric = pd.to_numeric(series, errors="coerce")
            present = series.notna() & series.astype("string").str.strip().ne("")
            invalid = present & numeric.isna()
            finite = pd.Series(np.isfinite(numeric.to_numpy(dtype=np.float64, na_value=np.nan)), index=series.index)
            invalid |= present & ~finite
            if any(token in name for token in NONNEGATIVE_TOKENS):
                invalid |= numeric.lt(0).fillna(False)
            if "latitude" in name or name == "lat":
                invalid |= numeric.lt(-90).fillna(False) | numeric.gt(90).fillna(False)
            if "longitude" in name or name in {"lon", "lng"}:
                invalid |= numeric.lt(-180).fillna(False) | numeric.gt(180).fillna(False)
        else:
            continue
        affected |= invalid.fillna(False)
    return int(affected.sum())


def analyse_data_types(frame):
    types = {str(column): str(dtype) for column, dtype in frame.dtypes.items()}
    summary = {}
    for dtype in types.values():
        summary[dtype] = summary.get(dtype, 0) + 1
    return {"columns": types, "summary": summary}


def detect_inconsistent_formats(frame):
    whitespace = {}
    date_invalid = {}
    for column in frame.columns:
        series = frame[column]
        if pd.api.types.is_object_dtype(series.dtype) or pd.api.types.is_string_dtype(series.dtype):
            values = series.dropna().astype("string")
            count = int(values.ne(values.str.strip()).sum())
            if count:
                whitespace[str(column)] = count
        if any(token in str(column).lower() for token in DATE_TOKENS):
            values = series.loc[~_missing_mask(series)]
            if len(values):
                bad = int(pd.to_datetime(values, errors="coerce", format="mixed").isna().sum())
                if bad:
                    date_invalid[str(column)] = bad
    return {"whitespace_values": whitespace, "invalid_date_values": date_invalid}


def profile_dataset(frame):
    total_cells = int(frame.shape[0] * frame.shape[1])
    missing = detect_missing_values(frame)
    missing_total = int(sum(item["count"] for item in missing.values()))
    return {
        "total_rows": int(len(frame)),
        "total_columns": int(len(frame.columns)),
        "missing_values": missing,
        "missing_value_count": missing_total,
        "missing_value_percentage": round(missing_total / total_cells * 100, 4) if total_cells else None,
        "duplicate_row_count": detect_duplicates(frame)["duplicate_rows"],
        "data_types": analyse_data_types(frame),
        "unique_values": {str(column): int(frame.loc[~_missing_mask(frame[column]), column].nunique(dropna=True)) for column in frame.columns},
        "invalid_values": detect_invalid_values(frame),
        "inconsistent_formats": detect_inconsistent_formats(frame),
        "memory_usage_bytes": int(frame.memory_usage(index=True, deep=True).sum()),
        "overall_completeness_percentage": round((total_cells - missing_total) / total_cells * 100, 4) if total_cells else None,
    }


def standardise_column_names(frame):
    names = []
    mapping = {}
    used = set()
    for old in frame.columns:
        base = re.sub(r"[^a-zA-Z0-9]+", "_", str(old).strip().lower()).strip("_") or "column"
        if base[0].isdigit():
            base = f"column_{base}"
        name = base
        suffix = 2
        while name in used:
            name = f"{base}_{suffix}"
            suffix += 1
        used.add(name)
        names.append(name)
        if str(old) != name:
            mapping[str(old)] = name
    cleaned = frame.copy(deep=False)
    cleaned.columns = names
    return cleaned, mapping


def _clean_frame(frame):
    result, renamed = standardise_column_names(frame)
    result = result.copy()
    operations = []
    if renamed:
        operations.append({"problem": "Column name formats", "rows_affected": 0, "action_taken": "Standardised column names to unique lowercase snake_case.", "columns_affected": renamed})

    trim_count = 0
    trimmed_rows = pd.Series(False, index=result.index)
    for column in result.columns:
        series = result[column]
        if pd.api.types.is_object_dtype(series.dtype) or pd.api.types.is_string_dtype(series.dtype):
            string_mask = series.map(lambda item: isinstance(item, str))
            string_values = series.astype("string")
            trimmed = string_values.str.strip()
            changed = string_mask & string_values.ne(trimmed).fillna(False)
            trim_count += int(changed.sum())
            trimmed_rows |= changed
            blank_mask = string_mask & trimmed.eq("").fillna(False)
            result[column] = series.where(~string_mask, trimmed).mask(blank_mask, pd.NA)
    operations.append({"problem": "Inconsistent text whitespace", "rows_affected": int(trimmed_rows.sum()), "values_affected": trim_count, "action_taken": "Trimmed leading/trailing whitespace and treated whitespace-only text as missing; retained original letter casing." if trim_count else "No unnecessary text whitespace found."})

    date_updates = {}
    invalid_dates = {}
    date_updated_rows = pd.Series(False, index=result.index)
    invalid_date_rows = pd.Series(False, index=result.index)
    for column in result.columns:
        if any(token in column.lower() for token in DATE_TOKENS):
            values = result[column]
            nonmissing = values.notna() & values.astype("string").str.strip().ne("")
            parsed = pd.to_datetime(values, errors="coerce", format="mixed")
            bad_mask = nonmissing & parsed.isna()
            bad_count = int(bad_mask.sum())
            if bad_count:
                invalid_dates[column] = bad_count
                invalid_date_rows |= bad_mask
            elif nonmissing.any():
                standardized = parsed.dt.strftime("%Y-%m-%d")
                changed = nonmissing & values.astype("string").ne(standardized.astype("string")).fillna(False)
                date_updated_rows |= changed
                result[column] = standardized.where(parsed.notna(), values)
                date_updates[column] = int(changed.sum())
    operations.append({"problem": "Date format inconsistencies", "rows_affected": int(date_updated_rows.sum()), "values_affected": sum(date_updates.values()), "action_taken": "Standardised fully parseable date columns to YYYY-MM-DD." if date_updates else "No fully parseable date values required standardisation.", "columns_affected": date_updates})
    operations.append({"problem": "Invalid dates", "rows_affected": int(invalid_date_rows.sum()), "values_affected": sum(invalid_dates.values()), "action_taken": "Flagged invalid date values and preserved them without guessing a correction." if invalid_dates else "No invalid date values detected.", "columns_affected": invalid_dates})

    missing_rows = pd.Series(False, index=result.index)
    missing = 0
    for column in result.columns:
        column_missing = _missing_mask(result[column])
        missing += int(column_missing.sum())
        missing_rows |= column_missing
    operations.append({"problem": "Missing values", "rows_affected": int(missing_rows.sum()), "values_affected": missing, "action_taken": "Preserved missing values and reported them; no measurements or categorical values were imputed." if missing else "No missing values found."})

    invalid = detect_invalid_values(result)
    operations.append({"problem": "Invalid values", "rows_affected": _invalid_rows_count(result), "values_affected": sum(item["count"] for item in invalid.values()), "action_taken": "Flagged values outside established numerical/geographical rules or values that could not be parsed; preserved source values." if invalid else "No invalid values detected by established rules.", "columns_affected": invalid})
    operations.append({"problem": "Unit conversions", "rows_affected": 0, "action_taken": "No units converted because source unit metadata was not available to establish an unambiguous conversion."})

    duplicate_count = int(result.duplicated(keep="first").sum())
    if duplicate_count:
        result = result.drop_duplicates(keep="first")
        operations.append({"problem": "Exact duplicate records", "rows_affected": duplicate_count, "action_taken": "Removed exact duplicate rows, retaining the first occurrence."})
    else:
        operations.append({"problem": "Exact duplicate records", "rows_affected": 0, "action_taken": "No exact duplicate rows found; no rows removed."})
    return result, operations


def clean_dataset(frame):
    """Return cleaned frame and an auditable list of conservative operations."""
    return _clean_frame(frame)


def validate_cleaned_dataset(frame):
    checks = []
    valid_names = all(bool(re.fullmatch(r"[a-z][a-z0-9_]*", str(name))) for name in frame.columns)
    checks.append({"check": "Column names use lowercase snake_case and are unique", "passed": valid_names and frame.columns.is_unique, "details": None if valid_names and frame.columns.is_unique else "One or more columns do not meet the naming convention or are duplicated."})
    duplicate_count = int(frame.duplicated().sum())
    checks.append({"check": "No exact duplicate rows remain", "passed": duplicate_count == 0, "details": f"{duplicate_count} duplicate rows remain." if duplicate_count else None})
    types = analyse_data_types(frame)
    checks.append({"check": "Column data types are inspectable", "passed": len(types["columns"]) == len(frame.columns), "details": None})
    invalid = detect_invalid_values(frame)
    checks.append({"check": "Established numerical and date rules", "passed": not invalid, "details": invalid or None})
    return {"passed": all(check["passed"] for check in checks), "checks": checks}


def generate_quality_report(before, after, operations, validation, dataset_id, cleaned_filename):
    problems = list(operations)
    return {
        "dataset_id": dataset_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "rows_before": before["total_rows"], "rows_after": after["total_rows"],
            "columns_before": before["total_columns"], "columns_after": after["total_columns"],
            "missing_values_before": before["missing_value_count"], "missing_values_after": after["missing_value_count"],
            "duplicates_before": before["duplicate_row_count"], "duplicates_after": after["duplicate_row_count"],
            "completeness_before": before["overall_completeness_percentage"],
            "completeness_after": after["overall_completeness_percentage"],
        },
        "before": before,
        "after": after,
        "problems": problems,
        "validation": validation,
        "cleaned_filename": cleaned_filename,
        "overall_status": "passed" if validation["passed"] else "review_required",
    }


def clean_csv_file(source, destination):
    """Clean CSV data in chunks while deduplicating across chunk boundaries."""
    before = profile_file(source, "csv")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    seen_hashes = set()
    operation_totals = {}
    first = True
    identifier_dtypes = _csv_identifier_dtypes(source)
    try:
        for chunk in pd.read_csv(source, chunksize=CSV_CHUNK_SIZE, dtype=identifier_dtypes):
            cleaned, operations = clean_dataset(chunk)
            hashes = pd.util.hash_pandas_object(cleaned, index=False)
            keep = []
            for hashed in hashes:
                value = int(hashed)
                keep.append(value not in seen_hashes)
                seen_hashes.add(value)
            cross_chunk_duplicates = len(keep) - sum(keep)
            if cross_chunk_duplicates:
                cleaned = cleaned.loc[keep]
                operation = operation_totals.setdefault("Exact duplicate records", {
                    "problem": "Exact duplicate records", "rows_affected": 0,
                    "action_taken": "Removed exact duplicate rows across the full dataset, retaining the first occurrence.",
                })
                operation["rows_affected"] += cross_chunk_duplicates
            for item in operations:
                if item["problem"] not in operation_totals:
                    operation_totals[item["problem"]] = dict(item)
                else:
                    entry = operation_totals[item["problem"]]
                    entry["rows_affected"] = entry.get("rows_affected", 0) + item.get("rows_affected", 0)
                    if "values_affected" in item:
                        entry["values_affected"] = entry.get("values_affected", 0) + item["values_affected"]
                    if "columns_affected" in item and item["problem"] != "Column name formats":
                        for name, count in item["columns_affected"].items():
                            target = entry.setdefault("columns_affected", {})
                            if isinstance(count, dict):
                                existing = target.get(name, {"count": 0, "kind": count.get("kind")})
                                target[name] = {"count": existing.get("count", 0) + count.get("count", 0), "kind": count.get("kind")}
                            else:
                                target[name] = target.get(name, 0) + count
            cleaned.to_csv(destination, index=False, mode="w" if first else "a", header=first)
            first = False
        if first:
            # Preserve header-only CSVs with the same conservative name normalization.
            headers = pd.read_csv(source, nrows=0)
            headers, _ = standardise_column_names(headers)
            headers.to_csv(destination, index=False)
        after = profile_file(destination, "csv")
        header = list(pd.read_csv(destination, nrows=0).columns)
        checks = [
            {"check": "Column names use lowercase snake_case and are unique", "passed": all(bool(re.fullmatch(r"[a-z][a-z0-9_]*", str(name))) for name in header) and len(header) == len(set(header)), "details": None},
            {"check": "No exact duplicate rows remain", "passed": after["duplicate_row_count"] == 0, "details": f"{after['duplicate_row_count']} duplicate rows remain." if after["duplicate_row_count"] else None},
            {"check": "Established numerical and date rules", "passed": not after["invalid_values"], "details": after["invalid_values"] or None},
        ]
        validation = {"passed": all(item["passed"] for item in checks), "checks": checks}
        return before, after, list(operation_totals.values()), validation
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def read_dataset(path, file_format):
    if file_format == "csv":
        return pd.read_csv(path)
    if file_format in {"xlsx", "xls"}:
        return pd.read_excel(path)
    if file_format == "parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported dataset format: {file_format}")


def write_json(path, payload):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    temporary.replace(target)
