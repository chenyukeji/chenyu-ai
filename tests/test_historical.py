import unittest
import tempfile
from pathlib import Path

from amazon_product_os.sellersprite import analyze_sellersprite


class HistoricalTests(unittest.TestCase):
    def test_sellersprite_chinese_export_columns_and_excel_percentages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "seller.csv"
            path.write_text(
                "ASIN,商品标题,小类目,月销量,销量环比增长率,评分数,价格(€),上架天数,包装重量（单位换算）,包装尺寸（单位换算）\n"
                "B000000001,Produit A,Accessoires,100,0.45,20,19.99,100,200 g,20 x 15 x 5 cm\n"
                "B000000002,Produit B,Accessoires,120,0.35,30,21.99,120,220 g,21 x 16 x 5 cm\n",
                encoding="utf-8",
            )

            candidates = analyze_sellersprite(path, marketplace="FR")

            self.assertEqual(candidates[0].product_type, "Accessoires")
            self.assertEqual(candidates[0].evidence["spike_asins"], 2)
            self.assertEqual(candidates[0].evidence["average_growth_pct"], 40.0)
            self.assertEqual(candidates[0].evidence["low_review_success"], 2)

    def test_sellersprite_csv_becomes_shared_candidates(self) -> None:
        candidates = analyze_sellersprite("examples/sellersprite_sample.csv", marketplace="DE")
        skeleton = next(candidate for candidate in candidates if candidate.product_type == "Skeleton Glow Gloves")

        self.assertEqual(skeleton.source, "Historical Spike")
        self.assertEqual(skeleton.evidence["same_type_asins"], 4)
        self.assertEqual(skeleton.evidence["spike_asins"], 3)
        self.assertEqual(skeleton.evidence["low_review_success"], 2)
        self.assertFalse(skeleton.evidence["profit_scored"])
        self.assertEqual(sum(skeleton.evidence["score_components"].values()), skeleton.score)

    def test_growth_is_derived_when_growth_column_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "history.csv"
            source.write_text(
                "ASIN,标题,产品类型,月销量,评论数,价格,月份,包装重量,包装尺寸\n"
                "B0DERIVE01,Glow Skeleton Gloves,Skeleton Glow Gloves,100,20,9.99,2025-10,120 g,20 x 15 x 4 cm\n"
                "B0DERIVE01,Glow Skeleton Gloves,Skeleton Glow Gloves,150,25,9.99,2025-11,120 g,20 x 15 x 4 cm\n"
                "B0DERIVE02,Bone Skeleton Gloves,Skeleton Glow Gloves,140,30,10.99,2025-11,130 g,21 x 16 x 4 cm\n",
                encoding="utf-8-sig",
            )
            candidates = analyze_sellersprite(source, marketplace="DE")
            skeleton = candidates[0]
            self.assertEqual(skeleton.evidence["spike_asins"], 1)
            self.assertEqual(skeleton.evidence["max_growth_pct"], 50.0)

    def test_low_price_and_compact_size_are_strict_filters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "filters.csv"
            source.write_text(
                "ASIN,标题,产品类型,月销量,销量增长率,评论数,价格,包装重量,包装尺寸\n"
                "B0GOOD0001,Good One,Compact Product,500,60%,20,19.99,300 g,20 x 15 x 5 cm\n"
                "B0GOOD0002,Good Two,Compact Product,450,50%,30,24.99,400 g,22 x 16 x 6 cm\n"
                "B0PRICE001,Too Expensive,Compact Product,900,90%,10,39.99,300 g,20 x 15 x 5 cm\n"
                "B0WEIGHT01,Too Heavy,Compact Product,900,90%,10,19.99,1.5 kg,20 x 15 x 5 cm\n"
                "B0SIZE0001,Too Large,Compact Product,900,90%,10,19.99,500 g,60 x 40 x 30 cm\n"
                "B0MISSING1,Missing Size,Compact Product,900,90%,10,19.99,,\n",
                encoding="utf-8-sig",
            )

            candidate = analyze_sellersprite(source)[0]

            self.assertEqual(candidate.evidence["same_type_asins"], 2)
            self.assertEqual(candidate.evidence["hard_filter"]["counts"]["eligible"], 2)
            self.assertEqual(candidate.evidence["hard_filter"]["counts"]["price_above_limit"], 1)
            self.assertEqual(candidate.evidence["hard_filter"]["counts"]["weight_above_limit"], 1)
            self.assertEqual(candidate.evidence["hard_filter"]["counts"]["dimensions_above_limit"], 1)
            self.assertEqual(candidate.evidence["hard_filter"]["counts"]["missing_size_or_weight"], 1)
            self.assertEqual(candidate.representative_asins, ["B0GOOD0001", "B0GOOD0002"])

    def test_missing_reviews_do_not_count_as_low_review_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "reviews.csv"
            source.write_text(
                "ASIN,标题,产品类型,月销量,销量增长率,评论数,价格,包装重量,包装尺寸\n"
                "B0REV00001,Review Missing,Compact Product,500,60%,,19.99,300 g,20 x 15 x 5 cm\n"
                "B0REV00002,Review Zero,Compact Product,450,50%,0,19.99,300 g,20 x 15 x 5 cm\n",
                encoding="utf-8-sig",
            )

            candidate = analyze_sellersprite(source)[0]

            self.assertEqual(candidate.evidence["spike_asins"], 2)
            self.assertEqual(candidate.evidence["low_review_success"], 0)

    def test_plain_five_means_five_percent_not_five_hundred(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "growth.csv"
            source.write_text(
                "ASIN,标题,产品类型,月销量,销量增长率,评论数,价格,包装重量,包装尺寸\n"
                "B0GROW0001,Growth One,Compact Product,500,5,20,19.99,300 g,20 x 15 x 5 cm\n"
                "B0GROW0002,Growth Two,Compact Product,450,4,30,19.99,300 g,20 x 15 x 5 cm\n",
                encoding="utf-8-sig",
            )

            candidate = analyze_sellersprite(source)[0]

            self.assertEqual(candidate.evidence["max_growth_pct"], 5.0)
            self.assertEqual(candidate.evidence["spike_asins"], 0)

    def test_many_flat_asins_do_not_create_a_full_score(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "crowded.csv"
            rows = [
                "ASIN,标题,产品类型,月销量,销量增长率,评论数,价格,包装重量,包装尺寸"
            ]
            rows.extend(
                f"B0FLAT{i:05d},Flat {i},Crowded Product,100,0%,500,19.99,300 g,20 x 15 x 5 cm"
                for i in range(25)
            )
            source.write_text("\n".join(rows), encoding="utf-8-sig")

            candidate = analyze_sellersprite(source)[0]

            self.assertEqual(candidate.evidence["same_type_asins"], 25)
            self.assertLess(candidate.score, 50)


if __name__ == "__main__":
    unittest.main()
