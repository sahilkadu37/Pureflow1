import json
from pathlib import Path
from flask import Blueprint, current_app, jsonify, request
from app.services.uploaded_dataset_analytics import analyze_uploaded_datasets

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/health")
def health():
    return jsonify({"status": "success", "project": current_app.config.get("PROJECT_NAME", "PureFlow"), "message": "PureFlow API is running"})


@dashboard_bp.get("/dashboard")
def dashboard():
    try:
        uploaded = json.loads(Path(current_app.config["DATASET_INDEX_PATH"]).read_text(encoding="utf-8"))
        uploaded = uploaded if isinstance(uploaded, list) else []
    except (OSError, json.JSONDecodeError):
        uploaded = []
    raw_root = Path(current_app.config["DATASET_UPLOAD_DIR"]).resolve()
    uploaded = [item for item in uploaded if isinstance(item, dict) and
                (raw_root / str(item.get("stored_filename", ""))).resolve().parent == raw_root and
                (raw_root / str(item.get("stored_filename", ""))).is_file()]
    requested_id = request.args.get("dataset_id")
    if requested_id in {None, "", "all"}:
        requested_id = None
    elif not any(item.get("dataset_id") == requested_id for item in uploaded):
        return jsonify({"status": "error", "message": "The selected uploaded dataset was not found."}), 404
    analytics = analyze_uploaded_datasets(uploaded, raw_root, requested_id)
    selected_uploads = [item for item in uploaded if not requested_id or item.get("dataset_id") == requested_id]
    quality_root = Path(current_app.config["DATASET_QUALITY_REPORT_DIR"])
    activity = []
    quality_totals = {"missing_values": 0, "duplicate_records": 0, "cleaned_datasets": 0, "attention_datasets": 0}
    analytics_by_id = {item["dataset_id"]: item for item in analytics["datasets"]}
    dashboard_uploads = []
    for item in uploaded:
        dataset_id = item.get("dataset_id", "")
        report_path = quality_root / f"{dataset_id}_quality.json"
        try:
            report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
        except (OSError, json.JSONDecodeError):
            report = {}
        source_metrics = analytics_by_id.get(dataset_id, {})
        missing_values = int(source_metrics.get("missing_values", 0) or 0)
        duplicate_records = int(source_metrics.get("duplicate_records", 0) or 0)
        dashboard_uploads.append({**item, "compatible": bool(source_metrics.get("compatible")),
                                  "compatibility_reason": source_metrics.get("compatibility_reason"),
                                  "cleaning_status": "cleaned" if report.get("cleaned_filename") else "not cleaned",
                                  "quality_status": "attention" if missing_values or duplicate_records else "no detected issues",
                                  "missing_values": missing_values, "duplicate_records": duplicate_records})
        activity.append({"type": "uploaded", "dataset_id": dataset_id, "dataset_name": item.get("original_filename"), "timestamp": item.get("upload_timestamp")})
        history = report.get("cleaning_history", [])
        for event in history:
            activity.append({"type": event.get("operation"), "dataset_id": dataset_id, "dataset_name": item.get("original_filename"), "timestamp": event.get("timestamp")})
    active_ids = {item.get("dataset_id") for item in uploaded}
    transform_history_path = Path(current_app.config["DATASET_TRANSFORMED_DIR"]) / "transformation_history.json"
    try:
        transform_history = json.loads(transform_history_path.read_text(encoding="utf-8")) if transform_history_path.is_file() else []
        transform_history = transform_history if isinstance(transform_history, list) else []
    except (OSError, json.JSONDecodeError):
        transform_history = []
    transform_history = [event for event in transform_history if active_ids.intersection(event.get("dataset_ids", []))]
    for event in transform_history:
        operation = event.get("operation")
        if operation in {"standardise", "integrate"}:
            activity.append({"type": operation, "dataset_id": None, "dataset_ids": event.get("dataset_ids", []), "dataset_name": event.get("output_filename"),
                            "timestamp": event.get("generated_at")})
    cleaned_ids = {item.get("dataset_id") for item in dashboard_uploads if item.get("cleaning_status") == "cleaned"}
    for item in selected_uploads:
        source_metrics = analytics_by_id.get(item.get("dataset_id"), {})
        quality_totals["missing_values"] += int(source_metrics.get("missing_values", 0) or 0)
        quality_totals["duplicate_records"] += int(source_metrics.get("duplicate_records", 0) or 0)
        if item.get("dataset_id") in cleaned_ids:
            quality_totals["cleaned_datasets"] += 1
        if source_metrics.get("missing_values") or source_metrics.get("duplicate_records"):
            quality_totals["attention_datasets"] += 1
    quality_totals["total_records"] = sum(int(item.get("row_count", 0) or 0) for item in selected_uploads)
    quality_totals["dataset_count"] = len(selected_uploads)
    quality_totals["uploaded_rows"] = quality_totals["total_records"]
    quality_totals["compatible_dataset_count"] = analytics["compatible_dataset_count"]
    has_data = bool(analytics["water_observations"])
    if requested_id:
        activity = [event for event in activity if event.get("dataset_id") == requested_id or (event.get("type") in {"standardise", "integrate"} and requested_id in event.get("dataset_ids", []))]
    return jsonify({
        "status": "success",
        "metrics": {
            "total_data_centres": None,
            "total_water_consumption": None,
            "water_consumption_unit": None,
            "average_wue": analytics["average_wue"],
            "average_wue_unit": "L/kWh",
            "high_water_stress_locations": None,
        },
        "water_consumption": analytics["annual"],
        "country_comparison": analytics["by_location"],
        "wue_trends": [],
        "observation_mix": analytics["observation_mix"],
        "dashboard_analytics": analytics,
        "regional_water_stress": [],
        "climate_summary": {"observations": 0, "locations": 0, "message": "No linked uploaded climate measurements are available."},
        "datasets": [],
        "uploaded_datasets": dashboard_uploads,
        "upload_summary": quality_totals,
        "recent_activity": sorted((event for event in activity if event.get("timestamp")), key=lambda event: event["timestamp"], reverse=True)[:10],
        "transformation_summary": {"standardisation_runs": sum(event.get("operation") == "standardise" for event in transform_history),
                                    "integration_runs": sum(event.get("operation") == "integrate" for event in transform_history),
                                    "latest_status": "completed" if transform_history else None,
                                    "latest_operation": transform_history[-1].get("operation") if transform_history else None},
        "processing_summary": {"attempts": 0, "records_read": 0, "records_inserted": 0, "records_rejected": 0, "duplicate_records": quality_totals["duplicate_records"], "successful_loads": 0},
        "data_quality_summary": {
            "metrics": [],
            "logged_issues": quality_totals["missing_values"] + quality_totals["duplicate_records"],
            "rejected_records": 0,
            "duplicate_records": quality_totals["duplicate_records"],
        },
        "sdg_context": ([
            {"goal": "SDG 6", "label": "Clean water and sanitation", "measure": "Uploaded water consumption observations", "value": analytics["water_observations"], "unit": "source observations"},
        ] + ([{"goal": "SDG 12", "label": "Responsible consumption", "measure": "Water-use efficiency observations", "value": analytics["wue_observations"], "unit": "uploaded observations"}] if analytics["wue_observations"] else [])),
        "data_status": {"available": has_data, "message": "Analytics use registered uploaded source files." if has_data else analytics["message"]},
        "analytics_messages": {"water_consumption": analytics["message"] or ("No compatible date or year column was found in the selected uploaded datasets." if not analytics["annual"] else None),
                               "location_consumption": "No compatible uploaded location and water consumption fields were found." if not analytics["by_location"] else None},
    })
