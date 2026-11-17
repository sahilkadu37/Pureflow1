import json
import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.database.connection import connect, initialize_database
from app.services.report_generator import build_report, report_download_path, write_report_exports
from app.services.recommendation_engine import generate_recommendations


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "test.sqlite"
        self.reports = self.root / "reports"
        self.quality = self.root / "quality"
        self.transformed = self.root / "transformed"
        self.quality.mkdir(); self.transformed.mkdir()
        initialize_database(self.db)
        conn = connect(self.db)
        try:
            conn.execute("INSERT INTO datasets(dataset_id,dataset_name,source_filename,transformed_filename,source_type,source_record_count,record_count,loaded_at,processing_status) VALUES('demo','Demo','demo.csv','job_demo_standardised.csv','csv',10,10,'2026-01-01','loaded')")
            for index in range(10):
                country = "US" if index == 0 else None
                conn.execute("INSERT INTO locations(place_name,country) VALUES(?,?)", (f"Place {index}", country))
                location_id = conn.execute("SELECT location_id FROM locations WHERE place_name=?", (f"Place {index}",)).fetchone()[0]
                conn.execute("INSERT INTO water_metrics(dataset_id,location_id,source_record_id,publisher,metric_type,scope,measurement_period,reporting_year,wue_l_per_kwh,consumption_million_gal) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    ("demo", location_id, f"row-{index}", "Publisher", "site_volume", "site", "2025", 2025,
                     10.0 if index == 9 else 1.0, 3.0 if index == 0 else None))
            conn.execute("INSERT INTO load_history(dataset_id,source_filename,transformed_filename,records_read,records_inserted,records_rejected,duplicate_records,loaded_at,load_status) VALUES('demo','demo.csv','job_demo_standardised.csv',10,10,0,0,'2026-01-01','loaded')")
            conn.commit()
        finally:
            conn.close()
        self.app = create_app({"TESTING": True, "SQLITE_PATH": str(self.db),
            "REPORT_STORAGE_DIR": str(self.reports), "DATASET_QUALITY_REPORT_DIR": str(self.quality),
            "DATASET_TRANSFORMED_DIR": str(self.transformed)})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def test_recommendations_use_transparent_data_evidence(self):
        report = build_report(self.db, quality_dir=self.quality, transformed_dir=self.transformed)
        self.assertEqual(report["analysis"]["wue"]["observations"], 10)
        self.assertFalse(report["sustainability"]["indicator_available"])
        outlier = next(item for item in report["recommendations"] if item["id"] == "review-wue-outliers")
        self.assertEqual(outlier["supporting_evidence"]["flagged_observations"][0]["value"], 10.0)
        self.assertIn("internal screening heuristic", outlier["reason"])
        self.assertTrue(any(item["id"] == "improve-location-coverage" for item in report["recommendations"]))

    def test_csv_json_pdf_exports_and_history(self):
        report = build_report(self.db, quality_dir=self.quality, transformed_dir=self.transformed)
        created = write_report_exports(report, self.reports)
        self.assertEqual(set(created["formats"]), {"pdf", "csv", "json"})
        directory = self.reports / created["report_id"]
        pdf = (directory / "report.pdf").read_bytes()
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertIn(b"ANNUAL CHART SUMMARY", pdf)
        self.assertIn(b"Page 1 of", pdf)
        self.assertIn(b"section,metric,value,unit,evidence", (directory / "report.csv").read_bytes())
        payload = json.loads((directory / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["report_id"], created["report_id"])
        self.assertIsNotNone(report_download_path(self.reports, created["report_id"], "pdf"))
        self.assertIsNone(report_download_path(self.reports, "../test.sqlite", "pdf"))

    def test_report_api_filters_generation_download_history_and_errors(self):
        overview = self.client.get("/api/reports/overview?dataset_ids=demo&start_date=2025-01-01&end_date=2025-12-31&location=Place%200")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.get_json()["overview"]["water_consumption"]["records"], 1)
        self.assertEqual(self.client.get("/api/reports/recommendations?dataset_id=unknown").status_code, 400)
        self.assertEqual(self.client.get("/api/reports/overview?start_date=bad-date").status_code, 400)
        generated = self.client.post("/api/reports/generate", json={"dataset_ids": ["demo"], "report_type": "comprehensive"})
        self.assertEqual(generated.status_code, 201)
        report_id = generated.get_json()["report"]["report_id"]
        for output_format, prefix in (("pdf", b"%PDF-"), ("csv", b"\xef\xbb\xbf"), ("json", b"{")):
            downloaded = self.client.get(f"/api/reports/download/{report_id}?format={output_format}")
            self.assertEqual(downloaded.status_code, 200)
            self.assertTrue(downloaded.data.startswith(prefix))
            downloaded.close()
        self.assertEqual(self.client.get(f"/api/reports/download/{'a'*32}?format=pdf").status_code, 404)
        self.assertEqual(self.client.get("/api/reports/history").get_json()["count"], 1)

    def test_empty_database_readiness_and_no_invented_recommendations(self):
        empty = self.root / "empty.sqlite"
        app = create_app({"TESTING": True, "SQLITE_PATH": str(empty), "REPORT_STORAGE_DIR": str(self.root / "empty-reports"),
            "DATASET_QUALITY_REPORT_DIR": str(self.quality), "DATASET_TRANSFORMED_DIR": str(self.transformed)})
        report = app.test_client().get("/api/reports/sustainability").get_json()
        self.assertFalse(report["sustainability"]["indicator_available"])
        self.assertEqual(report["recommendations"], [])
        self.assertIsNone(report["sustainability"]["calculation"])


if __name__ == "__main__":
    unittest.main()
