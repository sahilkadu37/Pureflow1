from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from app.services.transformations import (
    TransformError,
    build_compatibility_report,
    discover_curated_datasets,
    integrate_curated_datasets,
    latest_report,
    load_history,
    save_transformation,
    standardise_curated_dataset,
)

transform_bp = Blueprint("transform", __name__)


def _directories():
    return (
        Path(current_app.config["DATASET_CURATED_DIR"]),
        Path(current_app.config["DATASET_INDEX_PATH"]),
        Path(current_app.config["DATASET_TRANSFORMED_DIR"]),
    )


def _error_response(error):
    payload = {"status": "error", "message": str(error)}
    if getattr(error, "details", None) is not None:
        payload["details"] = error.details
    return jsonify(payload), getattr(error, "status_code", 500)


@transform_bp.get("/transform/compatibility")
def compatibility():
    curated_dir, index_path, _transformed_dir = _directories()
    try:
        report = build_compatibility_report(curated_dir, index_path)
        return jsonify({"status": "success", "compatibility": report})
    except Exception:
        current_app.logger.exception("Dataset compatibility analysis failed")
        return jsonify({"status": "error", "message": "Could not inspect curated datasets."}), 422


@transform_bp.post("/transform/standardise")
def standardise():
    curated_dir, index_path, transformed_dir = _directories()
    payload = request.get_json(silent=True) or {}
    selected = payload.get("dataset_ids") or ([payload["dataset_id"]] if payload.get("dataset_id") else [])
    if not isinstance(selected, list) or not selected:
        return jsonify({"status": "error", "message": "Provide one or more dataset_ids to standardise."}), 400
    try:
        available = {item["dataset_id"]: item for item in discover_curated_datasets(curated_dir, index_path)}
        missing = [dataset_id for dataset_id in selected if dataset_id not in available]
        if missing:
            raise TransformError("Selected dataset is not available in curated storage.", 404, {"dataset_ids": missing})
        results = [standardise_curated_dataset(available[dataset_id], transformed_dir) for dataset_id in selected]
        result = {
            "job_id": results[0]["job_id"], "generated_at": results[0]["generated_at"],
            "operation": "standardise", "dataset_ids": selected,
            "outputs": results, "output_filename": results[0]["output_filename"],
            "output_rows": sum(item["output_rows"] for item in results),
            "output_columns": results[0].get("output_columns"), "preview": results[0].get("preview"),
            "validation": {"passed": all(item.get("validation", {}).get("passed", False) for item in results), "datasets": [{"dataset_id": item["dataset_id"], **item.get("validation", {})} for item in results]},
        }
        result["report_filename"] = save_transformation(transformed_dir, result)
        return jsonify({"status": "success", "result": result, "message": "Standardised outputs saved without modifying curated or raw sources."})
    except TransformError as error:
        return _error_response(error)
    except Exception:
        current_app.logger.exception("Dataset standardisation failed")
        return jsonify({"status": "error", "message": "Could not standardise the selected curated dataset(s)."}), 422


@transform_bp.post("/transform/integrate")
def integrate():
    curated_dir, index_path, transformed_dir = _directories()
    payload = request.get_json(silent=True) or {}
    try:
        available = {item["dataset_id"]: item for item in discover_curated_datasets(curated_dir, index_path)}
        result = integrate_curated_datasets(
            available,
            payload.get("dataset_ids"),
            payload.get("join_keys"),
            payload.get("join_type", "inner"),
            transformed_dir,
        )
        result["report_filename"] = save_transformation(transformed_dir, result)
        return jsonify({"status": "success", "result": result, "message": "Integrated output saved. Source files were not modified."}), 201
    except TransformError as error:
        return _error_response(error)
    except Exception:
        current_app.logger.exception("Dataset integration failed")
        return jsonify({"status": "error", "message": "Dataset integration failed; source files were not modified."}), 422


@transform_bp.get("/transform/history")
def history():
    _curated_dir, _index_path, transformed_dir = _directories()
    return jsonify({"status": "success", "history": load_history(transformed_dir)})


@transform_bp.get("/transform/report")
def report():
    _curated_dir, _index_path, transformed_dir = _directories()
    latest = latest_report(transformed_dir)
    if latest is None:
        return jsonify({"status": "error", "message": "No transformation report is available yet."}), 404
    return jsonify({"status": "success", "report": latest})
