import re
import sqlite3
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from app.database.connection import connect, initialize_database
from app.services.database_loader import LoadError, inspect_dataset, load_dataset
from app.services.sql_analytics import validate_database

database_bp = Blueprint("database", __name__)


def _path():
    return current_app.config["SQLITE_PATH"]


def _error(message, code=500, details=None):
    payload = {"status": "error", "message": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), code


def _tables():
    initialize_database(_path())
    conn = connect(_path(), readonly=True)
    try:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return [{"name": name, "record_count": conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]} for name in names]
    finally:
        conn.close()


@database_bp.get("/database/status")
def database_status():
    try:
        target = initialize_database(_path())
        return jsonify({"status": "success", "connected": True, "database": str(target),
                        "exists": target.exists(), "size_bytes": target.stat().st_size,
                        "journal_mode": "WAL", "foreign_keys": True})
    except sqlite3.Error:
        current_app.logger.exception("Database status check failed")
        return _error("The SQLite database could not be opened.", 503)


@database_bp.get("/database/tables")
def database_tables():
    try:
        tables = _tables()
        return jsonify({"status": "success", "tables": tables, "count": len(tables)})
    except sqlite3.Error:
        current_app.logger.exception("Database table listing failed")
        return _error("Could not inspect database tables.", 503)


@database_bp.get("/database/schema")
def database_schema():
    initialize_database(_path())
    conn = connect(_path(), readonly=True)
    try:
        schemas = {}
        for table in (r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")):
            schemas[table] = {"columns": [dict(row) for row in conn.execute(f'PRAGMA table_info("{table}")')],
                              "foreign_keys": [dict(row) for row in conn.execute(f'PRAGMA foreign_key_list("{table}")')]}
        return jsonify({"status": "success", "schema": schemas})
    finally:
        conn.close()


@database_bp.post("/database/load/<dataset_id>")
def database_load(dataset_id):
    payload = request.get_json(silent=True) or {}
    reload_requested = payload.get("reload") is True
    if reload_requested and payload.get("confirm") is not True:
        return _error("Explicit confirmation is required to reload and replace a previously loaded dataset.", 400)
    try:
        report = load_dataset(dataset_id, current_app.config["DATASET_TRANSFORMED_DIR"],
                              current_app.config["DATASET_INDEX_PATH"], path=_path(), reload=reload_requested)
        return jsonify({"status": "success", "report": report, "message": report["message"]}), (200 if report["status"] == "skipped_duplicate" else 201)
    except LoadError as error:
        return _error(str(error), error.status_code, error.report)
    except (sqlite3.Error, OSError, ValueError):
        current_app.logger.exception("Database dataset load failed for %s", dataset_id)
        return _error("Dataset loading failed and was rolled back.", 422)


@database_bp.get("/database/load-history")
def load_history():
    initialize_database(_path())
    conn = connect(_path(), readonly=True)
    try:
        rows = [dict(row) for row in conn.execute("SELECT * FROM load_history ORDER BY loaded_at DESC,load_id DESC LIMIT 500")]
        return jsonify({"status": "success", "history": rows})
    finally:
        conn.close()


@database_bp.get("/database/validation")
def database_validation():
    try:
        report = validate_database(_path())
        return jsonify({"status": "success", "report": report})
    except sqlite3.Error:
        current_app.logger.exception("Database validation failed")
        return _error("Database validation could not be completed.", 503)


@database_bp.get("/database/datasets")
def transformed_datasets():
    from app.routes.datasets import _read_index
    directory = Path(current_app.config["DATASET_TRANSFORMED_DIR"])
    datasets = []
    for record in _read_index():
        try:
            info = inspect_dataset(record["dataset_id"], directory, current_app.config["DATASET_INDEX_PATH"])
            datasets.append({**info, "status": "transformed"})
        except LoadError:
            continue
    return jsonify({"status": "success", "datasets": datasets})


def _analytics_result(result):
    return jsonify({"status": "success", **result})


@database_bp.get("/analytics/water-consumption")
def analytics_water_consumption():
    from app.services.sql_analytics import water_consumption
    return _analytics_result(water_consumption(_path()))


@database_bp.get("/analytics/wue")
def analytics_wue():
    from app.services.sql_analytics import wue_by_location
    return _analytics_result(wue_by_location(_path()))


@database_bp.get("/analytics/climate")
def analytics_climate():
    from app.services.sql_analytics import climate_analysis
    return _analytics_result(climate_analysis(_path()))


@database_bp.get("/analytics/water-stress")
def analytics_water_stress():
    from app.services.sql_analytics import stress_analysis
    return _analytics_result(stress_analysis(_path()))


@database_bp.get("/analytics/monthly-trends")
def analytics_monthly():
    from app.services.sql_analytics import monthly_trends
    return _analytics_result(monthly_trends(_path()))


@database_bp.get("/analytics/annual-trends")
def analytics_annual():
    from app.services.sql_analytics import annual_trends
    return _analytics_result(annual_trends(_path()))


@database_bp.get("/analytics/country-comparison")
def analytics_country():
    from app.services.sql_analytics import country_comparison
    return _analytics_result(country_comparison(_path()))


@database_bp.get("/analytics/distribution")
def analytics_distribution():
    from app.services.sql_analytics import site_distribution
    return _analytics_result(site_distribution(_path()))


@database_bp.get("/analytics/summary")
def analytics_summary():
    from app.services.sql_analytics import summary
    return _analytics_result(summary(_path()))


@database_bp.route("/analytics/custom-query", methods=["GET", "POST"])
def custom_query():
    payload = request.get_json(silent=True) or {}
    sql = (payload.get("query") or request.args.get("query") or "").strip()
    params = payload.get("params", [])
    try:
        limit = max(1, min(int(payload.get("limit", request.args.get("limit", 200))), 500))
    except (TypeError, ValueError):
        return _error("limit must be an integer between 1 and 500.", 400)
    statement = sql[:-1].rstrip() if sql.endswith(";") else sql
    if not statement or not re.match(r"^(SELECT|WITH)\b", statement, re.IGNORECASE) or ";" in statement:
        return _error("Only one SELECT query is allowed.", 400)
    if not isinstance(params, list):
        return _error("params must be a JSON array.", 400)
    initialize_database(_path())
    conn = connect(_path(), readonly=True)
    permitted = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    if hasattr(sqlite3, "SQLITE_RECURSIVE"):
        permitted.add(sqlite3.SQLITE_RECURSIVE)
    conn.set_authorizer(lambda action, _a, _b, _db, _source: sqlite3.SQLITE_OK if action in permitted else sqlite3.SQLITE_DENY)
    try:
        cursor = conn.execute(f"SELECT * FROM ({statement}) AS pureflow_query LIMIT {limit + 1}", params)
        rows = [dict(row) for row in cursor.fetchmany(limit + 1)]
        truncated = len(rows) > limit
        rows = rows[:limit]
        return jsonify({"status": "success", "columns": [item[0] for item in cursor.description or []],
                        "rows": rows, "row_count": len(rows), "limit": limit, "truncated": truncated})
    except (sqlite3.Error, ValueError) as error:
        return _error(f"Query rejected or failed: {error}", 400)
    finally:
        conn.close()
