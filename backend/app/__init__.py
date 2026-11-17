from flask import Flask, jsonify
from flask_cors import CORS
from pathlib import Path
import os
import sqlite3


def create_app(test_config=None):
    app = Flask(__name__)
    app.logger.name = "PureFlow"
    backend_root = Path(__file__).resolve().parent.parent
    app.config.from_mapping(
        JSON_SORT_KEYS=False,
        PROJECT_NAME="PureFlow",
        PROJECT_TITLE="PureFlow \u2013 Water Consumption and Sustainability Analytics Platform",
        PROJECT_TAGLINE="Smarter Water Insights. Sustainable Tomorrow.",
        PROJECT_DESCRIPTION="PureFlow is a data analytics platform designed to analyse water consumption in data centres, assess data quality, identify missing values and duplicates, clean and transform datasets, and generate meaningful insights to support sustainable water management.",
        SQLALCHEMY_DATABASE_URI="sqlite:///database/aquaintel.db",
        DATASET_UPLOAD_DIR=str(backend_root / "data" / "raw"),
        DATASET_INDEX_PATH=str(backend_root / "data" / "datasets.json"),
        DATASET_CURATED_DIR=str(backend_root / "data" / "curated"),
        DATASET_QUALITY_REPORT_DIR=str(backend_root / "data" / "quality_reports"),
        DATASET_TRANSFORMED_DIR=str(backend_root / "data" / "transformed"),
        REPORT_STORAGE_DIR=str(backend_root / "data" / "reports"),
        MAX_CONTENT_LENGTH=101 * 1024 * 1024,
        DEBUG=os.environ.get("PUREFLOW_DEBUG", os.environ.get("AQUAINTEL_DEBUG", "false")).strip().lower() in {"1", "true", "yes"},
    )
    app.config["SQLITE_PATH"] = str(backend_root / "database" / "aquaintel.db")
    if test_config:
        app.config.update(test_config)

    configured_origins = os.environ.get("PUREFLOW_CORS_ORIGINS", os.environ.get("AQUAINTEL_CORS_ORIGINS", ""))
    cors_origins = ([origin.strip() for origin in configured_origins.split(",") if origin.strip() and origin.strip() != "*"]
                    if configured_origins else [
                        "https://pureflow1-1.onrender.com",
                        "http://localhost:5173",
                        "http://127.0.0.1:5173",
                    ])
    CORS(app, resources={r"/api/*": {
        "origins": cors_origins,
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
    }})

    from app.routes import api_blueprints
    for blueprint in api_blueprints:
        app.register_blueprint(blueprint, url_prefix="/api")

    @app.get("/")
    def home():
        return jsonify({"project": app.config["PROJECT_NAME"], "title": app.config["PROJECT_TITLE"], "tagline": app.config["PROJECT_TAGLINE"], "description": app.config["PROJECT_DESCRIPTION"], "status": "running"})

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"status": "error", "message": "The requested resource was not found."}), 404

    @app.errorhandler(500)
    def internal_error(_error):
        return jsonify({"status": "error", "message": "An internal server error occurred."}), 500

    @app.errorhandler(sqlite3.Error)
    def database_error(_error):
        app.logger.exception("SQLite operation failed")
        return jsonify({"status": "error", "message": "The database operation could not be completed."}), 503

    @app.errorhandler(413)
    def request_too_large(_error):
        return jsonify({"status": "error", "message": "File exceeds the 100 MB upload limit."}), 413

    return app
