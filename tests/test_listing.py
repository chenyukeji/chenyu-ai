import tempfile
import unittest
from pathlib import Path

from amazon_product_os.io_utils import read_json
from amazon_product_os.listing import build_image_plan, export_launch_package
from amazon_product_os.models import ProductMaster


class ListingTests(unittest.TestCase):
    def test_launch_accepts_product_master_without_development_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = export_launch_package(
                read_json("examples/product_master.json"),
                read_json("examples/listings.json"),
                Path(directory),
                node_executable="unused-node",
                workbook_builder=Path(directory) / "missing-builder.mjs",
            )
            self.assertFalse(result["checks"]["development_record_supplied"])
            self.assertTrue(result["checks"]["operations_review_required"])

    def test_launch_does_not_require_a_go_decision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = export_launch_package(
                read_json("examples/product_master.json"),
                read_json("examples/listings.json"),
                Path(directory),
                development_record={"decision": "WATCH"},
                node_executable="unused-node",
                workbook_builder=Path(directory) / "missing-builder.mjs",
            )
            self.assertTrue(result["checks"]["operations_review_required"])
            self.assertEqual(result["checks"]["development_recommendation"], "WATCH")
            self.assertTrue((Path(directory) / "product_master.json").exists())

    def test_image_plan_has_seven_fact_bound_briefs(self) -> None:
        master = ProductMaster.from_dict(read_json("examples/product_master.json"))
        plan = build_image_plan(master)
        self.assertEqual(len(plan), 7)
        self.assertEqual(plan[0]["name"], "Main image")
        self.assertIn(master.quantity, plan[0]["ai_prompt"])


if __name__ == "__main__":
    unittest.main()
