"""Dataset inspection, cautious standardisation and validated integration."""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.cleaning import standardise_column_names

DATE_NAMES = {"date", "day", "datetime", "timestamp", "source_date", "retrieved"}
ROLE_ALIASES = {
    "country": {"country", "country_name", "country_code"},
    "city": {"city", "city_name"},
    "region": {"region", "state", "province", "state_province"},
    "latitude": {"lat", "latitude"},
    "longitude": {"lon", "lng", "longitude"},
    "year": {"year", "period", "reporting_year", "fiscal_year"},
    "date": {"date", "day", "source_date"},
    "datetime": {"datetime", "timestamp", "recorded_at"},
}
UNIT_PATTERNS = {
    "m3": r"(?:^|_)(?:m3|cubic_m(?:etre|eter)s?)(?:_|$)",
    "million_gal": r"(?:^|_)(?:million_gal|million_gallon)s?(?:_|$)",
    "million_litres": r"(?:^|_)(?:million_litres?|million_liters?)(?:_|$)",
    "l_per_kwh": r"(?:^|_)(?:l_per_kwh|litres_per_kwh|liters_per_kwh)(?:_|$)",
    "mm": r"(?:^|_)(?:mm|millimetres?|millimeters?)(?:_|$)",
    "celsius": r"(?:^|_)(?:c|celsius|degc)(?:_|$)",
    "fahrenheit": r"(?:^|_)(?:f|fahrenheit|degf)(?:_|$)",
}


class TransformError(Exception):
    def __init__(self, message, status_code=400, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


def normalise_name(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _missing_values(series):
    mask = series.isna()
    if pd.api.types.is_object_dtype(series.dtype) or pd.api.types.is_string_dtype(series.dtype):
        mask = mask | series.astype("string").str.strip().eq("").fillna(False)
    return int(mask.sum())


def infer_key_role(column, series=None):
    name = normalise_name(column)
    for role, aliases in ROLE_ALIASES.items():
        if name == role or name in aliases:
            if role == "year" and series is not None:
                values = pd.to_numeric(series.dropna(), errors="coerce")
                if values.empty or not values.between(1800, 2200).all():
                    return None
            return role
    return None


def _unit_for(column):
    name = normalise_name(column)
    for unit, pattern in UNIT_PATTERNS.items():
        if re.search(pattern, name):
            return unit
    return None


def _measurement_family(column):
    name = normalise_name(column)
    for tokens, family in [
        (("wue", "effectiveness"), "wue"),
        (("consumption",), "water_consumption"),
        (("withdrawal",), "water_withdrawal"),
        (("discharge",), "water_discharge"),
        (("precipitation", "rainfall"), "precipitation"),
        (("temperature", "temp"), "temperature"),
        (("humidity",), "humidity"),
    ]:
        if any(token in name for token in tokens):
            return family
    return None


def _is_numeric_measurement(name):
    """Only validate fields that represent measurements, not water labels."""
    tokens = set(name.split("_"))
    if tokens & {"scope", "type", "category", "class", "status", "source", "id"}:
        return False
    return bool(_unit_for(name) or tokens & {"wue", "consumption", "withdrawal", "discharge", "usage", "volume", "effectiveness"})


def _candidate_values(series, role):
    values = series.dropna()
    if role in {"city", "country", "region"}:
        return set(values.astype("string").str.strip().str.casefold())
    if role == "year":
        parsed = pd.to_numeric(values, errors="coerce").dropna()
        return set(parsed.astype("Int64"))
    if role in {"date", "datetime"}:
        parsed = pd.to_datetime(values, errors="coerce", format="mixed").dropna()
        return set(parsed.dt.strftime("%Y-%m-%d" if role == "date" else "%Y-%m-%dT%H:%M:%S"))
    if role in {"latitude", "longitude"}:
        parsed = pd.to_numeric(values, errors="coerce").dropna()
        return set(parsed.astype("float64"))
    return set(values)


def _read_frame(path, extension):
    extension = extension.lower().lstrip(".")
    if extension == "csv":
        return pd.read_csv(path)
    if extension in {"xlsx", "xls"}:
        return pd.read_excel(path)
    if extension == "parquet":
        return pd.read_parquet(path)
    raise TransformError(f"Unsupported curated format: {extension}", 415)


def _index_records(index_path):
    path = Path(index_path)
    if not path.is_file():
        return []
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
        return content if isinstance(content, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def discover_curated_datasets(curated_dir, index_path):
    root = Path(curated_dir)
    root.mkdir(parents=True, exist_ok=True)
    by_id = {item.get("dataset_id"): item for item in _index_records(index_path)}
    supported = {".csv", ".xlsx", ".xls", ".parquet"}
    results = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in supported or path.name.endswith("_standardised.csv"):
            continue
        match = re.match(r"^([a-f0-9]{32})_cleaned$", path.stem)
        dataset_id = match.group(1) if match else f"curated-{path.stem}"
        source = by_id.get(dataset_id, {})
        try:
            frame = _read_frame(path, path.suffix)
        except Exception as exc:
            results.append({"dataset_id": dataset_id, "filename": path.name, "path": str(path), "inspectable": False, "error": str(exc)})
            continue
        empty_schema, _ = standardise_column_names(frame.head(0))
        schema = []
        key_candidates = []
        for original, standard in zip(frame.columns, empty_schema.columns):
            series = frame[original]
            role = infer_key_role(standard, series)
            dtype = str(series.dtype)
            sample = series.dropna().head(100)
            date_granularity = _date_granularity(sample, standard)
            unit = _unit_for(standard)
            entry = {
                "original_name": str(original), "standardised_name": str(standard),
                "data_type": dtype, "missing_values": _missing_values(series),
                "unique_values": int(series.nunique(dropna=True)),
                "key_role": role, "date_granularity": date_granularity,
                "unit": unit, "measurement_family": _measurement_family(standard),
            }
            schema.append(entry)
            if role:
                key_candidates.append({"column": str(standard), "role": role, "data_type": dtype, "unique_values": entry["unique_values"], "missing_values": entry["missing_values"], "date_granularity": date_granularity})
        results.append({
            "dataset_id": dataset_id, "filename": path.name,
            "source_filename": source.get("original_filename", path.name.replace("_cleaned", "")),
            "file_format": path.suffix.lower().lstrip("."),
            "row_count": int(len(frame)), "column_count": int(len(frame.columns)),
            "file_size": path.stat().st_size, "columns": schema,
            "key_candidates": key_candidates, "inspectable": True,
            "path": str(path),
        })
    return results


def _date_granularity(values, column):
    if not len(values):
        return None
    if infer_key_role(column, values) == "year":
        return "year"
    if normalise_name(column) not in DATE_NAMES | {"recorded_at"}:
        return None
    parsed = pd.to_datetime(values, errors="coerce", format="mixed").dropna()
    if parsed.empty:
        return "unparsed"
    if (parsed.dt.minute == 0).all() and (parsed.dt.second == 0).all() and (parsed.dt.hour != 0).any():
        return "hourly"
    if (parsed.dt.day == 1).all() and parsed.dt.month.nunique() > 1:
        return "monthly"
    if parsed.dt.day.nunique() > 1:
        return "daily"
    return "monthly_or_coarser"


def _validate_frame(frame):
    checks = []
    missing_keys = {}
    invalid_dates = {}
    invalid_numeric = {}
    for column in frame.columns:
        series = frame[column]
        role = infer_key_role(column, series)
        if role:
            count = int(series.isna().sum())
            if count:
                missing_keys[str(column)] = count
        name = normalise_name(column)
        if role in {"date", "datetime"}:
            present = series.notna() & series.astype("string").str.strip().ne("")
            parsed = pd.to_datetime(series, errors="coerce", format="mixed")
            count = int((present & parsed.isna()).sum())
            if count:
                invalid_dates[str(column)] = count
        is_measurement = _is_numeric_measurement(name)
        if role in {"latitude", "longitude"} or is_measurement:
            numeric = pd.to_numeric(series, errors="coerce")
            present = series.notna() & series.astype("string").str.strip().ne("")
            invalid = present & numeric.isna()
            if role == "latitude":
                invalid |= numeric.lt(-90).fillna(False) | numeric.gt(90).fillna(False)
            elif role == "longitude":
                invalid |= numeric.lt(-180).fillna(False) | numeric.gt(180).fillna(False)
            elif is_measurement:
                invalid |= numeric.lt(0).fillna(False)
            count = int(invalid.sum())
            if count:
                invalid_numeric[str(column)] = count
    duplicates = int(frame.duplicated().sum())
    checks.extend([
        {"check": "Recognized geographic/time join keys contain no missing values", "passed": not missing_keys, "details": missing_keys or None},
        {"check": "Recognized date values parse consistently", "passed": not invalid_dates, "details": invalid_dates or None},
        {"check": "Established geographic/numerical ranges", "passed": not invalid_numeric, "details": invalid_numeric or None},
        {"check": "Exact duplicate records", "passed": duplicates == 0, "details": {"duplicate_rows": duplicates} if duplicates else None},
    ])
    return {"passed": all(item["passed"] for item in checks), "checks": checks}


def build_compatibility_report(curated_dir, index_path):
    datasets = discover_curated_datasets(curated_dir, index_path)
    pairs = []
    for left_index, left in enumerate(datasets):
        if not left.get("inspectable"):
            continue
        for right in datasets[left_index + 1:]:
            if not right.get("inspectable"):
                continue
            right_by_role = {}
            for candidate in right["key_candidates"]:
                right_by_role.setdefault(candidate["role"], []).append(candidate)
            candidates = []
            units_left = {column["measurement_family"]: column for column in left["columns"] if column["unit"] and column["measurement_family"]}
            units_right = {column["measurement_family"]: column for column in right["columns"] if column["unit"] and column["measurement_family"]}
            unit_mismatches = [{"column": family, "left_column": units_left[family]["standardised_name"], "right_column": units_right[family]["standardised_name"], "left_unit": units_left[family]["unit"], "right_unit": units_right[family]["unit"], "action": "Values retained separately; no conversion inferred."} for family in units_left.keys() & units_right.keys() if units_left[family]["unit"] != units_right[family]["unit"]]
            for lc in left["key_candidates"]:
                for rc in right_by_role.get(lc["role"], []):
                    if lc["column"] != rc["column"]:
                        continue
                    if lc["date_granularity"] and rc["date_granularity"] and lc["date_granularity"] != rc["date_granularity"]:
                        continue
                    left_frame = _read_frame(left["path"], left["file_format"])
                    right_frame = _read_frame(right["path"], right["file_format"])
                    left_name = lc["original_name"] if lc.get("original_name") else lc["column"]
                    right_name = rc["original_name"] if rc.get("original_name") else rc["column"]
                    left_set = _candidate_values(left_frame[left_name], lc["role"])
                    right_set = _candidate_values(right_frame[right_name], rc["role"])
                    overlap = len(left_set & right_set)
                    if overlap == 0:
                        continue
                    left_duplicate_rows = int(left_frame[left_name].duplicated(keep=False).sum())
                    right_duplicate_rows = int(right_frame[right_name].duplicated(keep=False).sum())
                    many_to_many = left_duplicate_rows > 0 and right_duplicate_rows > 0
                    candidates.append({
                        "left_column": lc["column"], "right_column": rc["column"],
                        "role": lc["role"], "left_type": lc["data_type"],
                        "right_type": rc["data_type"],
                        "granularity": lc["date_granularity"] or rc["date_granularity"],
                        "distinct_value_overlap": overlap,
                        "left_value_coverage": round(overlap / len(left_set) * 100, 4) if left_set else None,
                        "right_value_coverage": round(overlap / len(right_set) * 100, 4) if right_set else None,
                        "left_missing_values": lc["missing_values"], "right_missing_values": rc["missing_values"],
                        "left_duplicate_key_rows": left_duplicate_rows,
                        "right_duplicate_key_rows": right_duplicate_rows,
                        "safe_join": not many_to_many,
                    })
            pairs.append({
                "left_dataset_id": left["dataset_id"], "left_filename": left["filename"],
                "right_dataset_id": right["dataset_id"], "right_filename": right["filename"],
                "candidate_join_keys": candidates, "compatible": bool(candidates),
                "unit_mismatches": unit_mismatches,
                "reason": "Explicit same-name semantic keys with compatible granularity were found. Duplicate-key checks still apply to the selected key combination." if candidates else "No verified common keys were found. Similar labels alone are not sufficient.",
            })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_count": len(datasets),
        "datasets": [{key: val for key, val in item.items() if key != "path"} for item in datasets],
        "pairs": pairs,
        "message": "At least two curated datasets are required to evaluate joins." if len(datasets) < 2 else "Compatibility is based on exact standardized column names, semantic roles, values and time granularity.",
    }


def _standardise_frame(frame):
    result, mapping = standardise_column_names(frame)
    result = result.copy()
    steps = [{"step": "standardise_column_names", "columns_renamed": mapping}] if mapping else []
    steps.append({"step": "trim_text_whitespace", "action": "Trimmed text whitespace; did not change letter casing."})
    for column in result.columns:
        series = result[column]
        if pd.api.types.is_object_dtype(series.dtype) or pd.api.types.is_string_dtype(series.dtype):
            text = series.astype("string").str.strip()
            result[column] = text.mask(text.eq(""), pd.NA).where(series.notna(), series)
    date_columns = []
    for column in result.columns:
        if normalise_name(column) in DATE_NAMES | {"recorded_at"}:
            values = result[column]
            present = values.notna() & values.astype("string").str.strip().ne("")
            parsed = pd.to_datetime(values, errors="coerce", format="mixed")
            if present.any() and int((present & parsed.isna()).sum()) == 0:
                result[column] = parsed.dt.strftime("%Y-%m-%d").where(parsed.notna(), values)
                date_columns.append(column)
    steps.append({"step": "standardise_dates", "columns": date_columns, "format": "YYYY-MM-DD", "action": "Only fully parseable recognized date columns were converted; ambiguous values were preserved."})
    steps.append({"step": "units", "action": "No unit conversions performed; source units are retained and reported only when explicit in column names."})
    return result, steps, mapping


def standardise_curated_dataset(dataset, output_dir):
    if not dataset.get("inspectable"):
        raise TransformError("Dataset could not be inspected.", 422)
    source = Path(dataset["path"])
    frame = _read_frame(source, dataset["file_format"])
    output, steps, mapping = _standardise_frame(frame)
    job_id = uuid.uuid4().hex
    filename = f"{job_id}_{dataset['dataset_id']}_standardised.csv"
    destination = Path(output_dir) / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".csv.tmp")
    output.to_csv(temporary, index=False)
    temporary.replace(destination)
    return {
        "job_id": job_id, "dataset_id": dataset["dataset_id"],
        "source_filename": dataset["source_filename"], "source_path": source.name,
        "output_filename": filename, "output_rows": int(len(output)),
        "output_columns": list(output.columns), "column_mapping": mapping,
        "steps": steps, "generated_at": datetime.now(timezone.utc).isoformat(),
        "preview": {"columns": list(output.columns), "records": json.loads(output.head(10).to_json(orient="records", date_format="iso"))},
        "validation": _validate_frame(output),
        "units": [{"column": str(column), "unit_from_name": _unit_for(column)} for column in output.columns if _unit_for(column)],
    }


def _normalise_join_series(series, role):
    if role in {"city", "country", "region"}:
        return series.astype("string").str.strip().str.casefold()
    if role in {"date", "datetime"}:
        parsed = pd.to_datetime(series, errors="coerce", format="mixed")
        if parsed.isna().any():
            raise TransformError(f"Join key '{series.name}' contains values that cannot be safely parsed as dates.", 422)
        return parsed.dt.strftime("%Y-%m-%d" if role == "date" else "%Y-%m-%dT%H:%M:%S")
    if role == "year":
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.isna().any() or not numeric.between(1800, 2200).all():
            raise TransformError(f"Join key '{series.name}' contains values that are not valid years.", 422)
        return numeric.astype("Int64")
    if role in {"latitude", "longitude"}:
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.isna().any() or not np.isfinite(numeric.to_numpy(dtype=np.float64)).all():
            raise TransformError(f"Join key '{series.name}' contains invalid coordinates.", 422)
        return numeric
    raise TransformError("Join key has no verified semantic role; select recognized geographic or temporal fields.", 422)


def integrate_curated_datasets(datasets_by_id, dataset_ids, join_keys, join_type, output_dir):
    if not isinstance(dataset_ids, list) or len(dataset_ids) < 2 or len(set(dataset_ids)) != len(dataset_ids):
        raise TransformError("Select at least two distinct curated datasets.", 400)
    if join_type not in {"inner", "left"}:
        raise TransformError("Join type must be 'inner' or 'left'.", 400)
    missing = [dataset_id for dataset_id in dataset_ids if dataset_id not in datasets_by_id]
    if missing:
        raise TransformError("Selected dataset is not available in curated storage.", 404, {"dataset_ids": missing})
    if not isinstance(join_keys, dict) or any(dataset_id not in join_keys for dataset_id in dataset_ids):
        raise TransformError("Provide selected join columns for every dataset.", 400)

    frames = []
    shared_roles = None
    granularities = []
    sources = []
    for position, dataset_id in enumerate(dataset_ids):
        dataset = datasets_by_id[dataset_id]
        requested = join_keys[dataset_id]
        requested = [requested] if isinstance(requested, str) else requested
        if not isinstance(requested, list) or not requested or any(not isinstance(name, str) for name in requested):
            raise TransformError(f"Join keys for {dataset_id} must be a non-empty column list.")
        frame = _read_frame(dataset["path"], dataset["file_format"])
        normalized_frame, _, _ = _standardise_frame(frame)
        original_to_standard = {entry["original_name"]: entry["standardised_name"] for entry in dataset["columns"]}
        keys = [original_to_standard.get(name, normalise_name(name)) for name in requested]
        if any(key not in normalized_frame.columns for key in keys):
            raise TransformError(f"One or more selected join columns do not exist in {dataset['filename']}.")
        roles = [infer_key_role(key, normalized_frame[key]) for key in keys]
        if any(role is None for role in roles):
            raise TransformError(f"Join keys in {dataset['filename']} have no verified geographic or temporal meaning.", 422)
        if shared_roles is None:
            shared_roles = roles
        elif roles != shared_roles:
            raise TransformError("Selected join keys have incompatible semantic roles or order.", 422)
        granularity = [
            _date_granularity(normalized_frame[key].dropna().head(100), key) if role in {"year", "date", "datetime"} else None
            for key, role in zip(keys, roles)
        ]
        granularities.append(granularity)
        if any(_missing_values(normalized_frame[key]) for key in keys):
            raise TransformError(f"Join keys in {dataset['filename']} contain missing values. Exclude or resolve them explicitly before integration.", 422)
        helper_keys = []
        for key, role in zip(keys, roles):
            helper = f"__join_{position}_{key}"
            normalized_frame[helper] = _normalise_join_series(normalized_frame[key], role)
            helper_keys.append(helper)
        lineage = f"__source_row_{dataset_id[:8]}"
        if lineage in normalized_frame:
            raise TransformError("Source dataset uses a reserved lineage column name.", 422)
        normalized_frame[lineage] = np.arange(1, len(normalized_frame) + 1)
        frames.append((normalized_frame, helper_keys, keys, dataset))
        sources.append({"dataset_id": dataset_id, "filename": dataset["source_filename"], "curated_file": dataset["filename"], "rows": int(len(normalized_frame))})

    if any(granularity != granularities[0] for granularity in granularities[1:]):
        raise TransformError("Temporal join-key granularities differ. Aggregate explicitly to a shared period before joining.", 422, {"granularities_by_dataset": dict(zip(dataset_ids, granularities))})

    current, current_join_keys, current_original_keys, current_dataset = frames[0]
    join_results = []
    for position, (right, right_join_keys, right_original_keys, right_dataset) in enumerate(frames[1:], start=1):
        if len(current_join_keys) != len(right_join_keys):
            raise TransformError("Join key counts do not match across datasets.", 422)
        left_dupes = current.duplicated(current_join_keys, keep=False)
        right_dupes = right.duplicated(right_join_keys, keep=False)
        if left_dupes.any() and right_dupes.any():
            raise TransformError("A many-to-many join was blocked because both datasets contain duplicate join keys.", 409)
        left_keys = current[current_join_keys].drop_duplicates()
        right_keys = right[right_join_keys].drop_duplicates()
        left_probe = current[current_join_keys].merge(right_keys, left_on=current_join_keys, right_on=right_join_keys, how="left", indicator=True)
        right_probe = right[right_join_keys].merge(left_keys, left_on=right_join_keys, right_on=current_join_keys, how="left", indicator=True)
        matched_left = int((left_probe["_merge"] == "both").sum())
        matched_right = int((right_probe["_merge"] == "both").sum())
        right_unique = not right_dupes.any()
        validate = "many_to_one" if right_unique else "one_to_many"
        merged = current.merge(right, left_on=current_join_keys, right_on=right_join_keys, how=join_type, indicator="__join_status", suffixes=("", f"_{position}"), validate=validate)
        matched_rows = int((merged["__join_status"] == "both").sum())
        left_total = int(len(current))
        join_results.append({
            "left_dataset_id": current_dataset.get("dataset_id", "integrated"),
            "right_dataset_id": right_dataset["dataset_id"], "join_type": join_type,
            "join_keys": [{"left": lkey, "right": rkey, "role": role} for lkey, rkey, role in zip(current_original_keys, right_original_keys, shared_roles)],
            "matched_rows": matched_rows,
            "left_unmatched_records": int(len(current) - matched_left),
            "right_unmatched_records": int(len(right) - matched_right),
            "match_percentage": round(matched_left / left_total * 100, 4) if left_total else None,
            "unmatched_explanation": "Unmatched counts are source records whose normalized selected key combination has no equal key in the other source.",
            "left_input_rows": left_total, "right_input_rows": int(len(right)),
            "duplicate_key_rows_left": int(left_dupes.sum()), "duplicate_key_rows_right": int(right_dupes.sum()),
            "row_count_before": left_total, "row_count_after": int(len(merged)),
        })
        merged = merged.drop(columns=["__join_status"])
        current = merged
        current_join_keys = [key for key in current_join_keys if key in current.columns]
        current_original_keys = [key for key in current_original_keys if key in current.columns]
        current_dataset = {"dataset_id": "integrated"}

    job_id = uuid.uuid4().hex
    generated = datetime.now(timezone.utc).isoformat()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_filename = f"{job_id}_integrated.csv"
    output_path = output_dir / output_filename
    temporary = output_path.with_suffix(".csv.tmp")
    current.to_csv(temporary, index=False)
    temporary.replace(output_path)
    validation = _validate_frame(current)
    duplicates = int(current.duplicated().sum())
    unit_sources = {}
    for dataset_id in dataset_ids:
        dataset = datasets_by_id[dataset_id]
        unit_sources[dataset_id] = {column["measurement_family"]: column for column in dataset["columns"] if column.get("unit") and column.get("measurement_family")}
    unit_mismatches = []
    for index, left_id in enumerate(dataset_ids):
        for right_id in dataset_ids[index + 1:]:
            for column in unit_sources[left_id].keys() & unit_sources[right_id].keys():
                left_meta, right_meta = unit_sources[left_id][column], unit_sources[right_id][column]
                left_unit, right_unit = left_meta["unit"], right_meta["unit"]
                if left_unit != right_unit:
                    unit_mismatches.append({"left_dataset_id": left_id, "right_dataset_id": right_id, "column": column, "left_column": left_meta["standardised_name"], "right_column": right_meta["standardised_name"], "left_unit": left_unit, "right_unit": right_unit, "action": "Values retained separately; no conversion inferred."})
    validation["duplicate_output_rows"] = duplicates
    for join in join_results:
        coverage_passed = join["match_percentage"] == 100.0
        validation["checks"].append({
            "check": f"Join coverage for {join['right_dataset_id']}",
            "passed": coverage_passed,
            "details": None if coverage_passed else {"match_percentage": join["match_percentage"], "left_unmatched_records": join["left_unmatched_records"], "right_unmatched_records": join["right_unmatched_records"]},
        })
    validation["checks"].append({
        "check": "Measurement units agree across shared fields",
        "passed": not unit_mismatches,
        "details": unit_mismatches or None,
    })
    validation["passed"] = all(item["passed"] for item in validation["checks"]) and duplicates == 0
    return {
        "job_id": job_id, "generated_at": generated, "operation": "integrate",
        "dataset_ids": dataset_ids, "sources": sources, "join_type": join_type,
        "join_results": join_results, "output_filename": output_filename,
        "output_rows": int(len(current)), "output_columns": int(len(current.columns)),
        "lineage_columns": [column for column in current.columns if column.startswith("__source_row_")],
        "preview": {"columns": list(current.columns), "records": json.loads(current.head(10).to_json(orient="records", date_format="iso"))},
        "steps": ["source files read from curated storage", "join-key semantics and time granularities validated", "many-to-many joins blocked", "source row lineage columns included"],
        "validation": validation,
        "unit_mismatches": unit_mismatches,
    }


def load_history(transformed_dir):
    path = Path(transformed_dir) / "transformation_history.json"
    if not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_transformation(transformed_dir, result):
    root = Path(transformed_dir)
    root.mkdir(parents=True, exist_ok=True)
    report = root / f"{result['job_id']}_report.json"
    temporary = report.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    temporary.replace(report)
    history = load_history(root)
    history.insert(0, {key: result.get(key) for key in ("job_id", "generated_at", "operation", "dataset_ids", "output_filename", "output_rows", "output_columns", "validation")})
    history_path = root / "transformation_history.json"
    temporary_history = history_path.with_suffix(".json.tmp")
    temporary_history.write_text(json.dumps(history, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    temporary_history.replace(history_path)
    return report.name


def latest_report(transformed_dir):
    history = load_history(transformed_dir)
    if not history:
        return None
    path = Path(transformed_dir) / f"{history[0]['job_id']}_report.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
