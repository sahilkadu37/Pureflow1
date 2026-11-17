"""End-to-end run against the repository's real source CSV, isolated in a temp workspace."""
import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.services.report_generator import list_report_history


BACKEND = Path(__file__).resolve().parents[1]
REAL_CSV = BACKEND / "data" / "raw" / "1cced4863e37452db38f10683ed66961_data-center-water.csv"


@unittest.skipUnless(REAL_CSV.is_file(), "requires the repository's actual water source CSV")
class RealDataPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.original = REAL_CSV.read_bytes()
        self.original_hash = hashlib.sha256(self.original).hexdigest()
        self.app = create_app({
            "TESTING": True,
            "SQLITE_PATH": str(self.root / "database" / "e2e.sqlite"),
            "DATASET_UPLOAD_DIR": str(self.root / "raw"),
            "DATASET_INDEX_PATH": str(self.root / "datasets.json"),
            "DATASET_CURATED_DIR": str(self.root / "curated"),
            "DATASET_QUALITY_REPORT_DIR": str(self.root / "quality"),
            "DATASET_TRANSFORMED_DIR": str(self.root / "transformed"),
            "REPORT_STORAGE_DIR": str(self.root / "reports"),
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def test_upload_clean_transform_database_analytics_and_report(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        upload = self.client.post("/api/datasets/upload", data={
            "file": (io.BytesIO(self.original), "data-center-water.csv")
        }, content_type="multipart/form-data")
        self.assertEqual(upload.status_code, 201, upload.get_data(as_text=True))
        dataset = upload.get_json()["dataset"]
        dataset_id = dataset["dataset_id"]
        self.assertEqual(dataset["row_count"], 85)
        self.assertEqual(self.client.get(f"/api/datasets/{dataset_id}").status_code, 200)
        self.assertEqual(self.client.get("/api/analytics/water").status_code, 200)
        self.assertEqual(self.client.get("/api/analytics/climate").status_code, 200)
        self.assertEqual(self.client.get("/api/analytics/water-stress").status_code, 200)
        stored = self.root / "raw" / dataset["stored_filename"]
        self.assertEqual(hashlib.sha256(stored.read_bytes()).hexdigest(), self.original_hash)
        self.assertEqual(hashlib.sha256(REAL_CSV.read_bytes()).hexdigest(), self.original_hash)

        listing = self.client.get("/api/datasets").get_json()
        self.assertEqual(listing["count"], 1)
        dashboard = self.client.get("/api/dashboard").get_json()
        self.assertEqual(dashboard["upload_summary"]["dataset_count"], 1)
        self.assertEqual(dashboard["upload_summary"]["total_records"], 85)
        self.assertEqual(dashboard["uploaded_datasets"][0]["dataset_id"], dataset_id)
        self.assertEqual(self.client.get(f"/api/datasets/{dataset_id}/preview").status_code, 200)
        quality = self.client.post(f"/api/datasets/{dataset_id}/quality-check")
        self.assertEqual(quality.status_code, 200)
        self.assertEqual(quality.get_json()["profile"]["total_rows"], 85)
        self.assertEqual(self.client.get(f"/api/datasets/{dataset_id}/quality-report").status_code, 200)
        cleaned = self.client.post(f"/api/datasets/{dataset_id}/clean")
        self.assertEqual(cleaned.status_code, 200, cleaned.get_data(as_text=True))
        cleaned_filename = cleaned.get_json()["report"]["cleaned_filename"]
        curated = self.root / "curated" / cleaned_filename
        self.assertTrue(curated.is_file())
        download = self.client.get(f"/api/datasets/{dataset_id}/download-cleaned")
        self.assertEqual(download.status_code, 200)
        self.assertIn("text/csv", download.content_type)
        self.assertIn("attachment", download.headers.get("Content-Disposition", ""))
        self.assertEqual(len(download.get_data(as_text=True).splitlines()), cleaned.get_json()["report"]["summary"]["rows_after"] + 1)
        self.assertEqual(self.client.get("/api/dashboard").get_json()["upload_summary"]["cleaned_datasets"], 1)
        self.assertEqual(hashlib.sha256(stored.read_bytes()).hexdigest(), self.original_hash)
        self.assertEqual(self.client.get(f"/api/datasets/{dataset_id}/cleaned-preview").status_code, 200)
        self.assertEqual(self.client.get(f"/api/datasets/{dataset_id}/cleaning-history").status_code, 200)

        compatibility = self.client.get("/api/transform/compatibility")
        self.assertEqual(compatibility.status_code, 200)
        standardized = self.client.post("/api/transform/standardise", json={"dataset_ids": [dataset_id]})
        self.assertEqual(standardized.status_code, 200, standardized.get_data(as_text=True))
        output_name = standardized.get_json()["result"]["output_filename"]
        self.assertTrue((self.root / "transformed" / output_name).is_file())
        self.assertEqual(self.client.get("/api/transform/history").status_code, 200)
        self.assertEqual(self.client.get("/api/transform/report").status_code, 200)
        # One source is present, so a relational integration join is correctly unavailable.
        integration = self.client.post("/api/transform/integrate", json={"dataset_ids": [dataset_id]})
        self.assertEqual(integration.status_code, 400)

        loaded = self.client.post(f"/api/database/load/{dataset_id}", json={})
        self.assertEqual(loaded.status_code, 201, loaded.get_data(as_text=True))
        self.assertEqual(loaded.get_json()["report"]["records_inserted"], 85)
        self.assertTrue(self.client.get("/api/database/validation").get_json()["report"]["valid"])
        self.assertEqual(self.client.get("/api/database/status").status_code, 200)
        self.assertGreater(self.client.get("/api/database/tables").get_json()["count"], 0)
        self.assertEqual(self.client.get("/api/database/schema").status_code, 200)
        self.assertEqual(self.client.get("/api/database/load-history").status_code, 200)
        self.assertEqual(self.client.get("/api/database/datasets").status_code, 200)

        water = self.client.get("/api/analytics/water-consumption").get_json()
        self.assertEqual(water["data"]["gallon_observations"], 42)
        for endpoint in ("wue", "climate", "water-stress", "monthly-trends", "annual-trends",
                         "country-comparison", "distribution", "summary"):
            self.assertEqual(self.client.get(f"/api/analytics/{endpoint}").status_code, 200, endpoint)
        self.assertTrue(self.client.get("/api/dashboard").get_json()["data_status"]["available"])
        custom = self.client.post("/api/analytics/custom-query", json={"query": "SELECT COUNT(*) AS rows FROM water_metrics"})
        self.assertEqual(custom.get_json()["rows"][0]["rows"], 85)

        report = self.client.post("/api/reports/generate", json={"dataset_ids": [dataset_id], "report_type": "comprehensive"})
        self.assertEqual(report.status_code, 201, report.get_data(as_text=True))
        report_id = report.get_json()["report"]["report_id"]
        self.assertEqual(self.client.get("/api/reports").status_code, 200)
        for endpoint in ("overview", "insights", "recommendations", "sustainability"):
            self.assertEqual(self.client.get(f"/api/reports/{endpoint}").status_code, 200, endpoint)
        for output_format in ("pdf", "csv", "json"):
            downloaded = self.client.get(f"/api/reports/download/{report_id}?format={output_format}")
            self.assertEqual(downloaded.status_code, 200)
            downloaded.close()
        self.assertEqual(len(list_report_history(self.root / "reports")), 1)
        self.assertEqual(hashlib.sha256(REAL_CSV.read_bytes()).hexdigest(), self.original_hash)

    def test_upload_error_responses(self):
        self.assertEqual(self.client.post("/api/datasets/upload").status_code, 400)
        bad_extension = self.client.post("/api/datasets/upload", data={"file": (io.BytesIO(b"x"), "data.exe")}, content_type="multipart/form-data")
        self.assertEqual(bad_extension.status_code, 415)
        malformed = self.client.post("/api/datasets/upload", data={"file": (io.BytesIO(b"not an xlsx file"), "bad.xlsx")}, content_type="multipart/form-data")
        self.assertEqual(malformed.status_code, 422)
        self.app.config["MAX_CONTENT_LENGTH"] = 32
        oversized = self.client.post("/api/datasets/upload", data={"file": (io.BytesIO(b"x" * 80), "oversized.csv")}, content_type="multipart/form-data")
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(self.client.get("/api/datasets/missing/preview").status_code, 404)
        self.assertEqual(self.client.post("/api/transform/standardise", json={}).status_code, 400)

    def test_upload_filename_sanitization_and_cors_allowlist(self):
        uploaded = self.client.post("/api/datasets/upload", data={
            "file": (io.BytesIO(b"name\nAquaIntel\n"), "../../traversal.csv")
        }, content_type="multipart/form-data")
        self.assertEqual(uploaded.status_code, 201)
        stored = self.root / "raw" / uploaded.get_json()["dataset"]["stored_filename"]
        self.assertEqual(stored.resolve().parent, (self.root / "raw").resolve())
        blocked = self.client.get("/api/health", headers={"Origin": "https://unexpected.example"})
        self.assertNotIn("Access-Control-Allow-Origin", blocked.headers)
        allowed = self.client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(allowed.headers.get("Access-Control-Allow-Origin"), "http://localhost:5173")


if __name__ == "__main__":
    unittest.main()
