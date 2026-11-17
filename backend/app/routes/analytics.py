from flask import Blueprint, current_app, jsonify
from app.services.sql_analytics import water_consumption, climate_analysis, stress_analysis

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.get("/analytics/water")
def water_analytics():
    result = water_consumption(current_app.config["SQLITE_PATH"])
    return jsonify({"status": "success", **result})


@analytics_bp.get("/analytics/climate")
def climate_analytics():
    return jsonify({"status": "success", **climate_analysis(current_app.config["SQLITE_PATH"])})


@analytics_bp.get("/analytics/water-stress")
def water_stress():
    return jsonify({"status": "success", **stress_analysis(current_app.config["SQLITE_PATH"])})
