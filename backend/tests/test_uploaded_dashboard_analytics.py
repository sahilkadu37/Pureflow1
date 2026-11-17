import io
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app import create_app


SOURCE = b"""data_center_id,city,date,water_consumption_liters,energy_consumption_kwh,wue_l_per_kwh,cooling_system
DC001,Mumbai,2026-01-01,12500.0,420.0,0.78,Cooling Tower
DC002,Pune,2026-01-01,9800.0,350.0,0.72,Chilled Water
DC003,Hyderabad,2026-01-01,14300.0,510.0,0.81,Cooling Tower
DC004,Bengaluru,2026-01-01,11200.0,390.0,0.75,Air Cooling
DC005,Chennai,2026-01-01,15800.0,600.0,0.84,Cooling Tower
DC006,Delhi,2026-01-01,,470.0,0.79,Chilled Water
DC007,Kolkata,2026-01-01,10900.0,,0.73,Air Cooling
DC008,Ahmedabad,2026-01-01,13100.0,455.0,,Cooling Tower
DC009,Jaipur,2026-01-01,8700.0,310.0,0.7,
DC010,Lucknow,2026-01-01,12000.0,405.0,0.77,Chilled Water
DC002,Pune,2026-01-01,9800.0,350.0,0.72,Chilled Water
DC005,Chennai,2026-01-01,15800.0,600.0,0.84,Cooling Tower
DC011,Indore,2026-01-02,10100.0,365.0,0.74,Air Cooling
DC012,Nagpur,2026-01-02,11600.0,410.0,0.76,Chilled Water
DC013,Surat,2026-01-02,13400.0,490.0,0.8,Cooling Tower
DC014,Bhopal,2026-01-02,9200.0,330.0,0.71,Air Cooling
DC015,Kochi,2026-01-02,14700.0,545.0,0.82,Cooling Tower
DC016,Patna,2026-01-02,10500.0,375.0,0.75,Chilled Water
DC017,Visakhapatnam,2026-01-02,12800.0,465.0,0.79,Cooling Tower
DC018,Coimbatore,2026-01-02,9900.0,345.0,0.73,Air Cooling
"""


class UploadedDashboardAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.database = root / "aquaintel-test.sqlite"
        self.app = create_app({
            "TESTING": True,
            "SQLITE_PATH": str(self.database),
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

    def upload(self, contents, filename):
        response = self.client.post("/api/datasets/upload", data={"file": (io.BytesIO(contents), filename)}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["dataset"]

    def test_dashboard_values_match_source_and_keep_units_and_dataset_selection_separate(self):
        first = self.upload(SOURCE, "water-test.csv")
        frame = pd.read_csv(io.BytesIO(SOURCE))
        numeric = pd.to_numeric(frame["water_consumption_liters"], errors="coerce")
        expected_total = float(numeric.sum())
        expected_observations = int(numeric.notna().sum())
        expected_groups = frame.assign(_value=numeric).dropna(subset=["_value"]).groupby("city")["_value"].sum().to_dict()

        selected = self.client.get(f"/api/dashboard?dataset_id={first['dataset_id']}").get_json()
        analytics = selected["dashboard_analytics"]
        self.assertEqual(selected["upload_summary"]["dataset_count"], 1)
        self.assertEqual(selected["upload_summary"]["total_records"], len(frame))
        self.assertEqual(selected["upload_summary"]["missing_values"], int(frame.isna().to_numpy().sum()))
        self.assertEqual(selected["upload_summary"]["duplicate_records"], int(frame.duplicated().sum()))
        self.assertEqual(selected["upload_summary"]["attention_datasets"], 1)
        self.assertEqual(analytics["units"], ["litres"])
        self.assertEqual(analytics["annual"][0]["year"], 2026)
        self.assertEqual(analytics["annual"][0]["value"], expected_total)
        self.assertEqual(analytics["annual"][0]["observations"], expected_observations)
        self.assertEqual({row["name"]: row["value"] for row in analytics["by_location"]}, expected_groups)
        self.assertEqual(sum(row["observations"] for row in selected["observation_mix"]), len(frame))
        self.assertEqual(analytics["wue_observations"], int(pd.to_numeric(frame["wue_l_per_kwh"], errors="coerce").notna().sum()))
        self.assertFalse(self.database.exists(), "Dashboard analytics must not initialize or query the SQLite database.")

        second = self.upload(b"country,year,consumption_gallons\nUSA,2025,3\nCanada,2025,7\n", "gallons.csv")
        all_data = self.client.get("/api/dashboard").get_json()
        self.assertEqual(set(all_data["dashboard_analytics"]["units"]), {"litres", "gallons"})
        self.assertEqual(all_data["upload_summary"]["dataset_count"], 2)
        self.assertEqual(all_data["upload_summary"]["total_records"], len(frame) + 2)
        self.assertEqual(sum(row["value"] for row in all_data["dashboard_analytics"]["annual"] if row["unit"] == "gallons"), 10)
        country_values = {row["name"]: row["value"] for row in all_data["dashboard_analytics"]["by_location"] if row["unit"] == "gallons"}
        self.assertEqual(country_values, {"Canada": 7.0, "USA": 3.0})

        deleted = self.client.delete(f"/api/datasets/{second['dataset_id']}")
        self.assertEqual(deleted.status_code, 200)
        after_delete = self.client.get("/api/dashboard").get_json()
        self.assertEqual(after_delete["upload_summary"]["dataset_count"], 1)
        self.assertEqual(after_delete["dashboard_analytics"]["units"], ["litres"])
        self.assertEqual(after_delete["dashboard_analytics"]["annual"][0]["value"], expected_total)

    def test_incompatible_upload_returns_empty_analytics_without_sql_fallback(self):
        dataset = self.upload(b"center,wue_l_per_kwh\nA,0.4\n", "wue-only.csv")
        response = self.client.get(f"/api/dashboard?dataset_id={dataset['dataset_id']}").get_json()
        self.assertEqual(response["dashboard_analytics"]["annual"], [])
        self.assertEqual(response["dashboard_analytics"]["by_location"], [])
        self.assertEqual(response["dashboard_analytics"]["message"], "No compatible water consumption data found in the selected dataset.")
        self.assertFalse(self.database.exists())


if __name__ == "__main__":
    unittest.main()
