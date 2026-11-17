"""Dataset-scoped dashboard analytics calculated from registered raw uploads."""
import re
from pathlib import Path

import pandas as pd


SUPPORTED_EXTENSIONS = {"csv", "xlsx", "xls", "parquet"}
UNIT_PATTERNS = (
    ("million_litres", ("millionlitre", "millionliter", "mlnlitre", "mlnliter")),
    ("million_gallons", ("milliongallon", "milliongal")),
    ("litres", ("litre", "liter", "liters", "litres", "waterl", "lwater", "consumptionl")),
    ("gallons", ("gallon", "gallons", "galwater")),
    ("cubic_metres", ("cubicmetre", "cubicmeter", "m3")),
)
CONSUMPTION_TOKENS = ("consumption", "consumed", "wateruse", "waterusage", "waterdemand")
COUNTRY_TOKENS = ("country", "nation")
LOCATION_TOKENS = ("city", "location", "region", "facility", "site", "datacenter", "municipality", "place")
MIX_TOKENS = LOCATION_TOKENS + ("category", "coolingsystem", "technology", "type")
DATE_TOKENS = ("date", "year", "period", "timestamp", "datetime", "measurementtime")


def _normalized(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _read_frame(path):
    ext = path.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(path)
    if ext in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if ext == ".parquet":
        return pd.read_parquet(path)
    raise ValueError("Unsupported uploaded data format.")


def _resolve_upload(record, raw_directory):
    root = Path(raw_directory).resolve()
    name = record.get("stored_filename")
    if not isinstance(name, str) or not name:
        return None
    path = (root / name).resolve()
    if path.parent != root or path.suffix.lower().lstrip(".") not in SUPPORTED_EXTENSIONS or not path.is_file():
        return None
    return path


def _consumption_column(columns):
    candidates = []
    for column in columns:
        normalized = _normalized(column)
        has_consumption_semantics = any(token in normalized for token in CONSUMPTION_TOKENS)
        unit = next((name for name, patterns in UNIT_PATTERNS if any(pattern in normalized for pattern in patterns)), None)
        if unit and has_consumption_semantics:
            candidates.append((column, unit))
        elif unit and normalized.startswith("water") and ("consumption" in normalized or "million" in normalized or "volume" in normalized):
            candidates.append((column, unit))
    return candidates[0] if len(candidates) == 1 else (None, None)


def _find_column(columns, tokens):
    normalized = {column: _normalized(column) for column in columns}
    for token in tokens:
        match = next((column for column, name in normalized.items() if name == token), None)
        if match is not None:
            return match
    for token in tokens:
        match = next((column for column, name in normalized.items() if token in name), None)
        if match is not None:
            return match
    return None


def _year_values(series, column):
    normalized = _normalized(column)
    numeric = pd.to_numeric(series, errors="coerce")
    present = series.notna() & series.astype("string").str.strip().ne("")
    numeric_years = bool(present.any() and numeric.loc[present].notna().all()
                         and numeric.loc[present].between(1900, 2200).all()
                         and numeric.loc[present].mod(1).eq(0).all())
    if "year" in normalized or numeric_years:
        years = numeric
    else:
        parsed = pd.to_datetime(series, errors="coerce", format="mixed")
        years = parsed.dt.year
    return years.where(years.between(1900, 2200)).astype("Int64")


def _period_granularity_values(series, column):
    normalized = _normalized(column)
    values = series.astype("string").str.strip()
    numeric = pd.to_numeric(series, errors="coerce")
    present = series.notna() & values.ne("")
    numeric_years = bool(present.any() and numeric.loc[present].notna().all()
                         and numeric.loc[present].between(1900, 2200).all()
                         and numeric.loc[present].mod(1).eq(0).all())
    if normalized in {"year", "reportingyear", "measurementyear"} or numeric_years:
        return pd.Series("annual", index=series.index, dtype="string")
    annual = values.str.fullmatch(r"\d{4}").fillna(False)
    monthly = values.str.fullmatch(r"\d{4}[-/]\d{1,2}|[A-Za-z]{3,9}\s+\d{4}").fillna(False)
    daily = values.str.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}").fillna(False)
    result = pd.Series("dated", index=series.index, dtype="string")
    result.loc[annual] = "annual"
    result.loc[monthly] = "monthly"
    result.loc[daily] = "daily"
    return result


def _analyze_one(record, raw_directory):
    path = _resolve_upload(record, raw_directory)
    result = {
        "dataset_id": record.get("dataset_id"), "dataset_name": record.get("original_filename"),
        "row_count": int(record.get("row_count", 0) or 0), "column_count": int(record.get("column_count", 0) or 0),
        "compatible": False, "compatibility_reason": "No explicitly unit-labelled water consumption field was found.",
        "units": [], "annual": [], "by_location": [], "observation_mix": [], "location_type": None,
        "water_records": 0, "missing_values": 0, "duplicate_records": 0,
        "wue_observations": 0, "wue_sum": 0.0,
    }
    if path is None:
        result["compatibility_reason"] = "The original uploaded file is missing or its stored path is invalid."
        return result
    try:
        frame = _read_frame(path)
    except Exception:
        result["compatibility_reason"] = "The uploaded file could not be read for analytics."
        return result
    result["row_count"] = int(len(frame))
    result["column_count"] = int(len(frame.columns))
    missing_mask = frame.isna()
    for column in frame.columns:
        if pd.api.types.is_object_dtype(frame[column].dtype) or pd.api.types.is_string_dtype(frame[column].dtype):
            missing_mask[column] = missing_mask[column] | frame[column].astype("string").str.strip().eq("").fillna(False)
    result["missing_values"] = int(missing_mask.to_numpy().sum())
    result["duplicate_records"] = int(frame.duplicated(keep="first").sum())
    columns = list(frame.columns)
    consumption_column, unit = _consumption_column(columns)
    country_column = _find_column(columns, COUNTRY_TOKENS)
    location_column = country_column or _find_column(columns, MIX_TOKENS)
    date_column = _find_column(columns, DATE_TOKENS)
    period_granularity = _period_granularity_values(frame[date_column], date_column) if date_column else pd.Series("undated", index=frame.index, dtype="string")
    wue_column = next((column for column in columns if "wue" in _normalized(column)), None)
    if wue_column:
        wue_values = pd.to_numeric(frame[wue_column], errors="coerce")
        wue_values = wue_values.loc[wue_values.notna() & wue_values.ge(0)]
        result["wue_observations"] = int(len(wue_values))
        result["wue_sum"] = float(wue_values.sum())

    if location_column:
        location_type = "country" if country_column else ("location" if _normalized(location_column) in {_normalized(item) for item in LOCATION_TOKENS} or any(token in _normalized(location_column) for token in LOCATION_TOKENS) else "category")
        result["location_type"] = location_type
        counts = frame[location_column].astype("string").str.strip().replace("", pd.NA).dropna().value_counts()
        result["observation_mix"] = [{"name": str(name), "observations": int(count)} for name, count in counts.items()]
    if not consumption_column:
        return result

    numeric = pd.to_numeric(frame[consumption_column], errors="coerce")
    valid = numeric.notna() & numeric.ge(0)
    result["water_records"] = int(valid.sum())
    result["units"] = [unit]
    result["compatible"] = True
    result["compatibility_reason"] = None
    if date_column:
        years = _year_values(frame[date_column], date_column)
        annual_frame = pd.DataFrame({"year": years, "value": numeric, "period_granularity": period_granularity}).loc[valid & years.notna()]
        grouped = annual_frame.groupby(["year", "period_granularity"], sort=True)["value"].agg(["sum", "count"]).reset_index()
        result["annual"] = [{"year": int(row["year"]), "unit": unit, "period_granularity": row["period_granularity"], "value": float(row["sum"]), "observations": int(row["count"]),
                              "dataset_id": record.get("dataset_id"), "dataset_name": record.get("original_filename")} for row in grouped.to_dict("records")]
    if location_column:
        location_values = frame[location_column].astype("string").str.strip().replace("", pd.NA)
        location_frame = pd.DataFrame({"name": location_values, "value": numeric, "period_granularity": period_granularity}).loc[valid & location_values.notna()]
        grouped = location_frame.groupby(["name", "period_granularity"], sort=True)["value"].agg(["sum", "count"]).reset_index()
        result["by_location"] = [{"name": str(row["name"]), "value": float(row["sum"]), "observations": int(row["count"]),
                                  "unit": unit, "location_type": result["location_type"],
                                  "period_granularity": row["period_granularity"],
                                  "dataset_id": record.get("dataset_id"), "dataset_name": record.get("original_filename")} for row in grouped.to_dict("records")]
    return result


def analyze_uploaded_datasets(records, raw_directory, selected_dataset_id=None):
    analyzed = [_analyze_one(record, raw_directory) for record in records]
    selected = [item for item in analyzed if not selected_dataset_id or item["dataset_id"] == selected_dataset_id]
    compatible_ids = {item["dataset_id"] for item in selected if item["compatible"]}
    compatible = [item for item in selected if item["compatible"]]

    annual = {}
    by_location = {}
    observation_mix = {}
    units = set()
    contributors = []
    for item in compatible:
        contributors.append({"dataset_id": item["dataset_id"], "dataset_name": item["dataset_name"], "unit": item["units"][0], "records": item["water_records"]})
        for row in item["annual"]:
            key = (row["year"], row["unit"], row["period_granularity"])
            target = annual.setdefault(key, {"year": row["year"], "unit": row["unit"], "period_granularity": row["period_granularity"], "value": 0.0, "observations": 0, "dataset_names": set()})
            target["value"] += row["value"]
            target["observations"] += row["observations"]
            target["dataset_names"].add(row["dataset_name"])
        for row in item["by_location"]:
            key = (row["name"], row["location_type"], row["unit"], row["period_granularity"])
            target = by_location.setdefault(key, {**row, "value": 0.0, "observations": 0, "dataset_names": set()})
            target["value"] += row["value"]
            target["observations"] += row["observations"]
            target["dataset_names"].add(row["dataset_name"])
        for row in item["observation_mix"]:
            key = (row["name"], item["location_type"])
            observation_mix[key] = observation_mix.get(key, 0) + row["observations"]
        units.update(item["units"])

    annual_rows = [{**row, "dataset_names": sorted(row["dataset_names"])} for _, row in sorted(annual.items())]
    location_rows = [{**row, "dataset_names": sorted(row["dataset_names"])} for _, row in sorted(by_location.items())]
    mix_rows = [{"name": name, "location_type": kind, "observations": count} for (name, kind), count in sorted(observation_mix.items())]
    wue_count = sum(int(item.get("wue_observations", 0)) for item in selected)
    wue_sum = sum(float(item.get("wue_sum", 0)) for item in selected)
    water_observations = sum(int(item.get("water_records", 0)) for item in compatible)
    return {
        "selection": selected_dataset_id or "all",
        "datasets": analyzed,
        "compatible_dataset_ids": sorted(compatible_ids),
        "compatible_dataset_count": len(compatible_ids),
        "units": sorted(units),
        "series": [{"unit": unit, "period_granularity": period, "label": f"{unit.replace('_', ' ')} · {period}"}
                   for unit, period in sorted({(row["unit"], row["period_granularity"]) for row in annual_rows})],
        "annual": annual_rows,
        "by_location": location_rows,
        "observation_mix": mix_rows,
        "contributors": contributors,
        "wue_observations": wue_count,
        "average_wue": wue_sum / wue_count if wue_count else None,
        "water_observations": water_observations,
        "annual_message": None if annual_rows else ("No compatible date or year column was found in the selected uploaded datasets." if compatible else "No compatible water consumption data found in the selected dataset."),
        "message": None if compatible else "No compatible water consumption data found in the selected dataset.",
    }
