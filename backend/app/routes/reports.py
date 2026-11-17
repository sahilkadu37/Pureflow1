from datetime import date
import re
import sqlite3

from flask import Blueprint, current_app, jsonify, request, send_file
from werkzeug.exceptions import NotFound

from app.services.report_generator import (
    REPORT_TYPES, build_report, list_report_history, report_download_path,
    write_report_exports,
)

reports_bp = Blueprint("reports", __name__)


def _filters(payload=None):
    payload = payload if isinstance(payload, dict) else {}
    dataset_ids = payload.get("dataset_ids", [])
    if isinstance(dataset_ids, str):
        dataset_ids = [value.strip() for value in dataset_ids.split(",") if value.strip()]
    if not isinstance(dataset_ids, list) or len(dataset_ids) > 50 or any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value) for value in dataset_ids):
        raise ValueError("dataset_ids must be an array of up to 50 valid dataset identifiers.")
    start_date, end_date = payload.get("start_date") or None, payload.get("end_date") or None
    for name, value in (("start_date", start_date), ("end_date", end_date)):
        if value:
            try:
                date.fromisoformat(value)
            except (TypeError, ValueError):
                raise ValueError(f"{name} must use YYYY-MM-DD format.") from None
    if start_date and end_date and start_date > end_date:
        raise ValueError("start_date must be earlier than or equal to end_date.")
    location = payload.get("location") or None
    if location is not None and (not isinstance(location, str) or len(location) > 120):
        raise ValueError("location must be a text value of at most 120 characters.")
    return {"dataset_ids": dataset_ids, "start_date": start_date, "end_date": end_date, "location": location}


def _build(filters, report_type="comprehensive"):
    return build_report(
        current_app.config["SQLITE_PATH"], **filters,
        quality_dir=current_app.config["DATASET_QUALITY_REPORT_DIR"],
        transformed_dir=current_app.config["DATASET_TRANSFORMED_DIR"], report_type=report_type,
    )


def _error(message, code, details=None):
    payload = {"status": "error", "message": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), code


def _query_filters():
    dataset_ids = request.args.getlist("dataset_id")
    if not dataset_ids and request.args.get("dataset_ids"):
        dataset_ids = request.args.get("dataset_ids")
    return _filters({"dataset_ids": dataset_ids, "start_date": request.args.get("start_date"),
                     "end_date": request.args.get("end_date"), "location": request.args.get("location")})


@reports_bp.get("/reports")
@reports_bp.get("/reports/history")
def reports_history():
    history = list_report_history(current_app.config["REPORT_STORAGE_DIR"])
    return jsonify({"status": "success", "reports": history, "history": history, "count": len(history),
                    "message": "Reports loaded." if history else "No reports have been generated yet."})


@reports_bp.get("/reports/overview")
def report_overview():
    try:
        report = _build(_query_filters())
        return jsonify({"status": "success", "overview": {
            "project": report["project"], "generated_at": report["generated_at"], "filters": report["filters"],
            "selected_datasets": report["selected_datasets"], "available_datasets": report["available_datasets"],
            "available_report_types": sorted(REPORT_TYPES),
            "database": report["database"]["table_counts"], "ingestion": report["ingestion"],
            "water_consumption": report["analysis"]["water_consumption"], "wue": report["analysis"]["wue"],
            "finding_count": len(report["findings"]), "recommendation_count": len(report["recommendations"]),
            "findings": report["findings"], "recommendations": report["recommendations"],
            "sustainability": report["sustainability"],
            "limitations": report["limitations"],
        }})
    except ValueError as error:
        return _error(str(error), 400)


@reports_bp.get("/reports/insights")
def report_insights():
    try:
        report = _build(_query_filters())
        return jsonify({"status": "success", "findings": report["findings"], "filters": report["filters"],
                        "analysis": report["analysis"]})
    except ValueError as error:
        return _error(str(error), 400)


@reports_bp.get("/reports/recommendations")
def report_recommendations():
    try:
        report = _build(_query_filters())
        return jsonify({"status": "success", "recommendations": report["recommendations"], "filters": report["filters"]})
    except ValueError as error:
        return _error(str(error), 400)


@reports_bp.get("/reports/sustainability")
def report_sustainability():
    try:
        report = _build(_query_filters())
        return jsonify({"status": "success", "sustainability": report["sustainability"],
                        "recommendations": report["recommendations"], "limitations": report["limitations"],
                        "filters": report["filters"]})
    except ValueError as error:
        return _error(str(error), 400)


@reports_bp.post("/reports/generate")
def generate_report():
    payload = request.get_json(silent=True) or {}
    try:
        filters = _filters(payload)
        report_type = payload.get("report_type", "comprehensive")
        if not isinstance(report_type, str) or report_type not in REPORT_TYPES:
            return _error(f"report_type must be one of: {', '.join(sorted(REPORT_TYPES))}.", 400)
        report = _build(filters, report_type)
        result = write_report_exports(report, current_app.config["REPORT_STORAGE_DIR"])
        return jsonify({"status": "success", "report": result, "downloads": {
            output_format: f"/api/reports/download/{result['report_id']}?format={output_format}"
            for output_format in result["formats"]
        }, "message": "Report generated from stored PureFlow data."}), 201
    except ValueError as error:
        return _error(str(error), 400)
    except sqlite3.Error:
        current_app.logger.exception("Report analytics query failed")
        return _error("The report could not read the analytical database.", 503)
    except (OSError, UnicodeError):
        current_app.logger.exception("Report export could not be written")
        return _error("The report could not be saved.", 500)


@reports_bp.get("/reports/download/<report_id>")
def download_report(report_id):
    output_format = request.args.get("format", "pdf").lower()
    path = report_download_path(current_app.config["REPORT_STORAGE_DIR"], report_id, output_format)
    if path is None:
        raise NotFound("The requested report export was not found.")
    mimetypes = {"pdf": "application/pdf", "csv": "text/csv; charset=utf-8", "json": "application/json"}
    return send_file(path, mimetype=mimetypes[output_format], as_attachment=True,
                     download_name=f"pureflow_report_{report_id}.{output_format}", conditional=True)
