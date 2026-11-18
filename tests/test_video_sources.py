import json
import unittest
from unittest.mock import patch

from shopee_aff.video_sources import ProductRef, SourceError, extract_listing_video, resolve, validate_video_url


PRODUCT = "https://shopee.com.br/product/123/456"
VIDEO = "https://down-br.vod.susercontent.com/api/v4/original-product.mp4"


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.ref = ProductRef("123", "456")

    def test_product_identity_from_both_listing_url_formats(self):
        for url in (PRODUCT, "https://shopee.com.br/Pote-Hermetico-i.123.456?extra=1"):
            self.assertEqual(ProductRef.from_url(url), self.ref)

    def test_short_links_and_mismatched_api_ids_rejected(self):
        for url in ("https://shp.ee/test", "http://shopee.com.br/product/123/456", "https://shopee.com.br/product/0/456"):
            with self.assertRaises(SourceError):
                ProductRef.from_url(url)
        with self.assertRaises(SourceError):
            ProductRef.from_product({"productLink": PRODUCT, "itemId": 999, "shopId": 123})
        with self.assertRaises(SourceError):
            ProductRef.from_product({"productLink": PRODUCT, "itemId": 456, "shopId": 999})

    def test_media_urls_require_original_shopee_hosts(self):
        self.assertEqual(validate_video_url(VIDEO), VIDEO)
        for url in ("http://down-br.vod.susercontent.com/a.mp4", "https://localhost/a.mp4",
                    "https://susercontent.com.example.org/a.mp4", "file:///etc/passwd",
                    "https://user:password@down-br.vod.susercontent.com/a.mp4"):
            with self.assertRaises(SourceError):
                validate_video_url(url)

    def test_listing_open_graph_video(self):
        document = f'<link rel="canonical" href="{PRODUCT}"><meta property="og:video" content="{VIDEO}">'
        self.assertEqual(extract_listing_video(document, self.ref).video_url, VIDEO)

    def test_product_jsonld_video(self):
        data = {"@type": "Product", "url": PRODUCT, "video": {"@type": "VideoObject", "contentUrl": VIDEO}}
        document = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
        self.assertEqual(extract_listing_video(document, self.ref).video_url, VIDEO)

    def test_product_state_with_original_video_format(self):
        data = {"item": {"itemid": 456, "shopid": 123, "video_info_list": [{"default_format": {"url": VIDEO}}]}}
        document = '<script type="application/json">' + json.dumps(data) + '</script>'
        self.assertEqual(extract_listing_video(document, self.ref).video_url, VIDEO)

    def test_recommended_product_video_is_never_used(self):
        for data in ({"@type": "Product", "url": "https://shopee.com.br/product/777/888", "video": {"contentUrl": VIDEO}},
                     {"itemid": 888, "shopid": 777, "video_info_list": [{"video_url": VIDEO}]}):
            document = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
            with self.assertRaises(SourceError):
                extract_listing_video(document, self.ref)

    def test_product_video_with_unverifiable_identity_is_not_used(self):
        data = {"@type": "Product", "video": {"contentUrl": VIDEO}}
        document = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
        with self.assertRaises(SourceError):
            extract_listing_video(document, self.ref)

    def test_login_shell_and_wrong_canonical_do_not_produce_videos(self):
        for document in ('<div id="app"></div>', '<script type="application/json">broken json</script>',
                         f'<link rel="canonical" href="https://shopee.com.br/product/777/888"><meta property="og:video" content="{VIDEO}">'):
            with self.assertRaises(SourceError):
                extract_listing_video(document, self.ref)

    def test_registered_source_is_bound_to_the_exact_listing(self):
        registry = {"version": 1, "sources": {self.ref.key: {"product_url": PRODUCT, "video_url": VIDEO}}}
        with patch("urllib.request.build_opener") as network:
            self.assertEqual(resolve(self.ref, registry).video_url, VIDEO)
            network.assert_not_called()
        registry["sources"][self.ref.key]["product_url"] = "https://shopee.com.br/product/777/888"
        with self.assertRaises(SourceError):
            resolve(self.ref, registry)


if __name__ == "__main__":
    unittest.main()
