import unittest
from unittest.mock import patch

from shopee_aff import main, shopee


class SelectionTests(unittest.TestCase):
    def test_shared_candidate_selection_preserves_filters_and_commission_ranking(self):
        base = {"itemId": 1, "commissionRate": "0.10", "priceMin": "20", "ratingStar": "4.8",
                "sales": 150, "imageUrl": "https://example.org/image.jpg"}
        products = [base, dict(base, itemId=2, priceMin="50"),
                    dict(base, itemId=3, ratingStar="3.0"),
                    dict(base, itemId=4, commissionRate="0.01"),
                    dict(base, itemId=5, sales=0), dict(base, itemId=6, priceMin="200"),
                    dict(base, itemId=7, imageUrl=""), dict(base, itemId=8)]
        with patch.object(shopee, "top_products", return_value=products):
            result = main.candidates({"8"})
        self.assertEqual([product["itemId"] for product in result], [2, 1])

    def test_existing_image_picker_still_returns_one_product_or_none(self):
        with patch.object(main, "candidates", return_value=[{"itemId": 1}]):
            self.assertEqual(main.pick(set()), {"itemId": 1})
        with patch.object(main, "candidates", return_value=[]):
            self.assertIsNone(main.pick(set()))


if __name__ == "__main__":
    unittest.main()
