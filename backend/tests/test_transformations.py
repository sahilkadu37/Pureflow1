import hashlib
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app import create_app
from app.services.transformations import (
    TransformError,
    build_compatibility_report,
    discover_curated_datasets,
    integrate_curated_datasets,
    normalise_name,
    standardise_curated_dataset,
)


BACKEND = Path(__file__).resolve().parents[1]
CURATED = BACKEND / "data" / "curated"
INDEX = BACKEND / "data" / "datasets.json"
REAL_DATASET_ID = "1cced4863e37452db38f10683ed66961"


@unittest.skipUnless((CURATED / f"{REAL_DATASET_ID}_cleaned.csv").is_file(), "requires the project's uploaded curated dataset")
class ExistingCuratedDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.datasets = discover_curated_datasets(CURATED, INDEX)
        cls.dataset = next(item for item in cls.datasets if item["dataset_id"] == REAL_DATASET_ID)

    def test_column_standardisation_and_safe_date_output(self):
        self.assertEqual(normalise_name("Source Date"), "source_date")
        before_hash = hashlib.sha256(Path(self.dataset["path"]).read_bytes()).hexdigest()
        source = pd.read_csv(self.dataset["path"])
        with tempfile.TemporaryDirectory() as directory:
            result = standardise_curated_dataset(self.dataset, directory)
            output = pd.read_csv(Path(directory) / result["output_filename"])
        after_hash = hashlib.sha256(Path(self.dataset["path"]).read_bytes()).hexdigest()
        self.assertEqual(before_hash, after_hash)
        self.assertEqual(len(output), self.dataset["row_count"])
        if "source_date" in output.columns:
            expected = source["source_date"].astype("string").str.strip().fillna("<missing>").tolist()
            actual = output["source_date"].astype("string").fillna("<missing>").tolist()
            self.assertEqual(actual, expected)
        if "retrieved" in output.columns:
            self.assertTrue(output["retrieved"].dropna().str.fullmatch(r"\d{4}-\d{2}-\d{2}").all())
        units = {column["standardised_name"]: column["unit"] for column in self.dataset["columns"]}
        self.assertEqual(units.get("wue_l_per_kwh"), "l_per_kwh")

    def test_compatibility_uses_only_existing_curated_sources(self):
        report = build_compatibility_report(CURATED, INDEX)
        self.assertEqual(report["dataset_count"], len(self.datasets))
        self.assertTrue(all(item["filename"].endswith("_cleaned.csv") for item in report["datasets"]))
        if len(self.datasets) == 1:
            self.assertEqual(report["pairs"], [])

    def test_single_dataset_is_rejected_for_integration(self):
        with self.assertRaises(TransformError):
            integrate_curated_datasets(
                {self.dataset["dataset_id"]: self.dataset},
                [self.dataset["dataset_id"]],
                {self.dataset["dataset_id"]: ["country"]},
                "inner",
                tempfile.mkdtemp(),
            )


class TransformApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        self.client = create_app({
            "TESTING": True,
            "DATASET_CURATED_DIR": str(base / "curated"),
            "DATASET_INDEX_PATH": str(base / "datasets.json"),
            "DATASET_TRANSFORMED_DIR": str(base / "transformed"),
        }).test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_empty_compatibility_and_report_status(self):
        response = self.client.get("/api/transform/compatibility")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["compatibility"]["dataset_count"], 0)
        self.assertEqual(self.client.get("/api/transform/history").status_code, 200)
        self.assertEqual(self.client.get("/api/transform/report").status_code, 404)


@unittest.skipUnless(
    (CURATED / f"{REAL_DATASET_ID}_cleaned.csv").is_file()
    and (BACKEND / "data" / "raw" / f"{REAL_DATASET_ID}_data-center-water.csv").is_file(),
    "requires the project's uploaded curated dataset and source file",
)
class RealDatasetTransformApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.transformed = Path(self.temp_dir.name) / "transformed"
        self.raw_file = BACKEND / "data" / "raw" / f"{REAL_DATASET_ID}_data-center-water.csv"
        self.raw_hash = hashlib.sha256(self.raw_file.read_bytes()).hexdigest()
        self.client = create_app({
            "TESTING": True,
            "DATASET_CURATED_DIR": str(CURATED),
            "DATASET_INDEX_PATH": str(INDEX),
            "DATASET_TRANSFORMED_DIR": str(self.transformed),
        }).test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_standardise_api_writes_output_report_and_history(self):
        compatibility = self.client.get("/api/transform/compatibility")
        self.assertEqual(compatibility.status_code, 200)
        response = self.client.post("/api/transform/standardise", json={"dataset_ids": [REAL_DATASET_ID]})
        self.assertEqual(response.status_code, 200)
        result = response.json["result"]
        self.assertTrue((self.transformed / result["output_filename"]).is_file())
        self.assertTrue((self.transformed / result["report_filename"]).is_file())
        self.assertEqual(self.client.get("/api/transform/history").json["history"][0]["operation"], "standardise")
        self.assertEqual(self.client.get("/api/transform/report").status_code, 200)
        self.assertEqual(hashlib.sha256(self.raw_file.read_bytes()).hexdigest(), self.raw_hash)


if __name__ == "__main__":
    unittest.main()
