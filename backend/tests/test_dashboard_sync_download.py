import io
import tempfile
import unittest
from pathlib import Path

from app import create_app


class DashboardAndCleanedDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.app = create_app({
            "TESTING": True,
            "SQLITE_PATH": str(root / "database" / "test.sqlite"),
            "DATASET_UPLOAD_DIR": str(root / "raw"),
            "DATASET_INDEX_PATH": str(root / "datasets.json"),
            "DATASET_CURATED_DIR": str(root / "curated"),
            "DATASET_QUALITY_REPORT_DIR": str(root / "quality"),
            "DATASET_TRANSFORMED_DIR": str(root / "transformed"),
            "REPORT_STORAGE_DIR": str(root / "reports"),
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def test_dashboard_tracks_upload_clean_and_delete_and_download_is_real_csv(self):
        source = b" Site Name ,Value,Date\nA,1,2025-01-01\nA,1,2025-01-01\nB,,2025-01-02\n"
        uploaded = self.client.post("/api/datasets/upload", data={"file": (io.BytesIO(source), "sample.csv")}, content_type="multipart/form-data")
        self.assertEqual(uploaded.status_code, 201)
        dataset_id = uploaded.get_json()["dataset"]["dataset_id"]
        summary = self.client.get("/api/dashboard").get_json()["upload_summary"]
        self.assertEqual((summary["dataset_count"], summary["total_records"]), (1, 3))
        cleaned = self.client.post(f"/api/datasets/{dataset_id}/clean")
        self.assertEqual(cleaned.status_code, 200)
        report = cleaned.get_json()["report"]
        download = self.client.get(f"/api/datasets/{dataset_id}/download-cleaned")
        self.assertEqual(download.status_code, 200)
        self.assertIn("text/csv", download.content_type)
        self.assertIn("attachment", download.headers["Content-Disposition"])
        self.assertEqual(len(download.get_data(as_text=True).splitlines()) - 1, report["summary"]["rows_after"])
        self.assertIn("site_name", download.get_data(as_text=True).splitlines()[0])
        download.close()
        self.assertEqual((Path(self.app.config["DATASET_UPLOAD_DIR"]) / uploaded.get_json()["dataset"]["stored_filename"]).read_bytes(), source)
        dashboard = self.client.get("/api/dashboard").get_json()
        self.assertEqual(dashboard["upload_summary"]["cleaned_datasets"], 1)
        self.assertEqual(dashboard["uploaded_datasets"][0]["cleaning_status"], "cleaned")
        self.assertEqual(self.client.delete(f"/api/datasets/{dataset_id}").status_code, 200)
        after_delete = self.client.get("/api/dashboard").get_json()
        self.assertEqual(after_delete["upload_summary"]["dataset_count"], 0)
        self.assertEqual(after_delete["uploaded_datasets"], [])

    def test_cleaned_download_requires_valid_existing_cleaning_run(self):
        self.assertEqual(self.client.get("/api/datasets/../../bad/download-cleaned").status_code, 404)


if __name__ == "__main__":
    unittest.main()
