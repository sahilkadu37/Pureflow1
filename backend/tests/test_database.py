import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import sqlite3

from app import create_app
from app.database.connection import connect, initialize_database
from app.services.database_loader import LoadError, load_dataset
from app.services.sql_analytics import country_comparison, validate_database, water_consumption, wue_by_location


@contextmanager
def db_conn(path, readonly=False):
    connection = connect(path, readonly=readonly)
    try:
        yield connection
    finally:
        connection.close()


class DatabaseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "database" / "test.sqlite"
        self.transformed = self.root / "transformed"
        self.transformed.mkdir()
        self.index = self.root / "datasets.json"
        self.dataset_id = "sample123"
        self.metadata = {"dataset_id": self.dataset_id, "original_filename": "water.csv",
            "stored_filename": f"{self.dataset_id}_water.csv", "file_format": "csv",
            "upload_timestamp": "2026-01-01T00:00:00Z"}
        self.index.write_text(json.dumps([self.metadata]), encoding="utf-8")
        self.raw = self.root / "raw"
        self.curated = self.root / "curated"
        self.quality = self.root / "quality"
        self.raw.mkdir()
        self.curated.mkdir()
        self.quality.mkdir()
        (self.raw / self.metadata["stored_filename"]).write_text("source", encoding="utf-8")
        self.output = self.transformed / f"job_{self.dataset_id}_standardised.csv"
        self.frame = pd.DataFrame([
            {"id": "a", "publisher": "A", "metric": "site_volume", "scope": "site", "facility_or_region": "North", "country": "US", "period": "2025", "wue_l_per_kwh": None, "consumption_million_gal": 2, "consumption_million_litres": 7.5},
            {"id": "b", "publisher": "A", "metric": "wue", "scope": "site", "facility_or_region": "South", "country": "US", "period": "May 2025", "wue_l_per_kwh": 0.3, "consumption_million_gal": None, "consumption_million_litres": None},
        ])
        self.frame.to_csv(self.output, index=False)
        self.app = create_app({"TESTING": True, "SQLITE_PATH": str(self.db),
            "DATASET_TRANSFORMED_DIR": str(self.transformed), "DATASET_INDEX_PATH": str(self.index),
            "DATASET_UPLOAD_DIR": str(self.raw), "DATASET_CURATED_DIR": str(self.curated),
            "DATASET_QUALITY_REPORT_DIR": str(self.quality)})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def load(self, reload=False):
        return load_dataset(self.dataset_id, self.transformed, self.index, path=self.db, reload=reload, batch_size=1)

    def test_database_and_schema_create_without_touching_other_file(self):
        initialize_database(self.db)
        self.assertTrue(self.db.is_file())
        with db_conn(self.db) as conn:
            self.assertTrue(conn.execute("PRAGMA foreign_keys").fetchone()[0])
            names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO water_metrics(dataset_id,location_id,source_record_id) VALUES('missing',999,'x')")
        self.assertTrue({"datasets", "locations", "water_metrics", "load_history", "data_quality_logs"}.issubset(names))

    def test_load_duplicate_prevention_and_explicit_reload(self):
        first = self.load()
        second = self.load()
        self.assertEqual(first["records_inserted"], 2)
        self.assertEqual(second["status"], "skipped_duplicate")
        self.assertEqual(self.load(reload=True)["records_inserted"], 2)
        with db_conn(self.db, readonly=True) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM water_metrics").fetchone()[0], 2)

    def test_rollback_on_invalid_unique_source_record(self):
        self.frame.loc[1, "id"] = "a"
        self.frame.loc[1, "facility_or_region"] = "Different place"
        self.frame.to_csv(self.output, index=False)
        with self.assertRaises(Exception):
            self.load()
        with db_conn(self.db, readonly=True) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM water_metrics").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT load_status FROM load_history ORDER BY load_id DESC LIMIT 1").fetchone()[0], "failed")

    def test_validation_and_real_join_aggregates(self):
        self.load()
        report = validate_database(self.db)
        self.assertTrue(report["valid"], report)
        consumption = water_consumption(self.db)["data"]
        self.assertEqual(consumption["million_gallons"], 2)
        countries = country_comparison(self.db)["data"]
        self.assertEqual(countries[0]["country"], "US")
        self.assertEqual(countries[0]["million_gallons"], 2)
        self.assertEqual(wue_by_location(self.db)["data"][0]["average_wue_l_per_kwh"], 0.3)

    def test_exact_duplicate_rows_are_reported_and_skipped(self):
        self.frame = pd.concat([self.frame, self.frame.iloc[[0]]], ignore_index=True)
        self.frame.to_csv(self.output, index=False)
        report = self.load()
        self.assertEqual(report["records_read"], 3)
        self.assertEqual(report["records_inserted"], 2)
        self.assertEqual(report["duplicate_records"], 1)

    def test_missing_transformed_data_is_rejected(self):
        self.output.unlink()
        with self.assertRaises(LoadError):
            self.load()

    def test_api_empty_database_and_safe_custom_query(self):
        status = self.client.get("/api/database/status")
        self.assertEqual(status.status_code, 200)
        empty = self.client.get("/api/analytics/water-consumption").get_json()
        self.assertIn("No water consumption", empty["message"])
        allowed = self.client.post("/api/analytics/custom-query", json={"query": "SELECT COUNT(*) AS n FROM water_metrics"})
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.get_json()["rows"][0]["n"], 0)
        for sql in ("DELETE FROM datasets", "DROP TABLE datasets", "WITH x AS (DELETE FROM datasets RETURNING *) SELECT * FROM x", "SELECT 1; SELECT 2"):
            response = self.client.post("/api/analytics/custom-query", json={"query": sql})
            self.assertEqual(response.status_code, 400, sql)
        with db_conn(self.db, readonly=True) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0], 0)

    def test_load_api_requires_confirmation_for_reload(self):
        self.load()
        response = self.client.post(f"/api/database/load/{self.dataset_id}", json={"reload": True})
        self.assertEqual(response.status_code, 400)
        response = self.client.post(f"/api/database/load/{self.dataset_id}", json={"reload": True, "confirm": True})
        self.assertEqual(response.status_code, 201)

    def test_delete_removes_only_selected_dataset_data_and_owned_files(self):
        self.load()
        other_id = "sample456"
        other_metadata = {**self.metadata, "dataset_id": other_id, "original_filename": "other.csv",
                          "stored_filename": f"{other_id}_other.csv"}
        (self.raw / other_metadata["stored_filename"]).write_text("other", encoding="utf-8")
        self.index.write_text(json.dumps([self.metadata, other_metadata]), encoding="utf-8")
        other_output = self.transformed / f"job_{other_id}_standardised.csv"
        self.frame.assign(id=["c", "d"]).to_csv(other_output, index=False)
        load_dataset(other_id, self.transformed, self.index, path=self.db)
        (self.curated / f"{self.dataset_id}_cleaned.csv").write_text("curated", encoding="utf-8")
        (self.quality / f"{self.dataset_id}_quality.json").write_text("{}", encoding="utf-8")
        owned_output = self.transformed / f"job_{self.dataset_id}_standardised.csv"
        owned_output.write_text("standardised", encoding="utf-8")
        shared_output = self.transformed / "job_integrated.csv"
        shared_output.write_text("shared", encoding="utf-8")

        response = self.client.delete(f"/api/datasets/{self.dataset_id}")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(self.client.delete(f"/api/datasets/{self.dataset_id}").status_code, 404)
        with db_conn(self.db) as conn:
            self.assertEqual(conn.execute("SELECT dataset_id FROM datasets").fetchall()[0][0], other_id)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM water_metrics").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM load_history WHERE dataset_id=?", (self.dataset_id,)).fetchone()[0], 0)
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual([item["dataset_id"] for item in json.loads(self.index.read_text(encoding="utf-8"))], [other_id])
        self.assertFalse((self.raw / self.metadata["stored_filename"]).exists())
        self.assertFalse((self.curated / f"{self.dataset_id}_cleaned.csv").exists())
        self.assertFalse((self.quality / f"{self.dataset_id}_quality.json").exists())
        self.assertFalse(owned_output.exists())
        self.assertTrue(other_output.exists())
        self.assertTrue(shared_output.exists())
        dashboard = self.client.get("/api/dashboard").get_json()
        # The overview is deliberately scoped to registered raw uploads, not
        # residual SQLite analytics from a separately processed dataset.
        self.assertFalse(dashboard["data_status"]["available"])
        self.assertEqual([item["dataset_id"] for item in dashboard["uploaded_datasets"]], [other_id])
        self.assertIsNone(dashboard["metrics"]["total_water_consumption"])
        self.assertEqual(dashboard["processing_summary"]["attempts"], 0)

        self.assertEqual(self.client.delete(f"/api/datasets/{other_id}").status_code, 200)
        empty_dashboard = self.client.get("/api/dashboard").get_json()
        self.assertFalse(empty_dashboard["data_status"]["available"])
        self.assertEqual(empty_dashboard["datasets"], [])
        self.assertEqual(empty_dashboard["water_consumption"], [])
        self.assertEqual(empty_dashboard["data_quality_summary"]["logged_issues"], 0)
        self.assertEqual(empty_dashboard["processing_summary"]["attempts"], 0)
        self.assertTrue(all(item["value"] == 0 for item in empty_dashboard["sdg_context"]))
        self.assertEqual(self.client.get("/api/analytics/water-consumption").get_json()["data"]["million_litres"], None)
        with db_conn(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0], 0)
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
