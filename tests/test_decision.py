import unittest

from amazon_product_os.compliance import assess_compliance
from amazon_product_os.decision import evaluate_product
from amazon_product_os.io_utils import read_json
from amazon_product_os.profit import calculate_profit


class DecisionTests(unittest.TestCase):
    def test_profit_has_normal_and_conservative_scenarios(self) -> None:
        result = calculate_profit(read_json("examples/profit_input.json"))
        self.assertGreater(result["normal"]["net_profit"], result["conservative"]["net_profit"])
        self.assertGreater(result["conservative"]["net_profit"], 0)
        self.assertGreater(result["normal"]["net_margin"], 0.2)
        self.assertTrue(result["meets_target"])

    def test_regulated_product_missing_documents_is_hard_gate(self) -> None:
        result = assess_compliance({"toy": True, "packaging": True, "documents": []}, "DE")
        self.assertEqual(result["risk"], "high")
        self.assertTrue(result["hard_gate"])
        self.assertIn("CE", result["missing_evidence"])
        self.assertNotIn("documents", result["profile_flags"])

    def test_example_development_case_is_go(self) -> None:
        card = evaluate_product(read_json("examples/development_case.json"))
        self.assertEqual(card["decision"], "GO")
        self.assertGreaterEqual(card["development_score"], 75)
        self.assertEqual(card["hard_gates"], [])


if __name__ == "__main__":
    unittest.main()
