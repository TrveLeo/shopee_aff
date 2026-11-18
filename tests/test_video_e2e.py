"""Exercise the complete CLI with replayed HTTP boundaries and real FFmpeg.

The generated test media and replayed affiliate URL never enter production state.
"""
import contextlib
import io
import json
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from shopee_aff import shopee, videos


PRODUCT = {"itemId": 456, "shopId": 123, "productName": "Pote hermético E2E fixture", "priceMin": "25.90",
           "productLink": "https://shopee.com.br/product/123/456", "commissionRate": "0.10",
           "ratingStar": "4.8", "sales": 150, "imageUrl": "https://example.org/photo.jpg"}
VIDEO_URL = "https://down-br.vod.susercontent.com/e2e-fixture.mp4"
AFFILIATE_URL = "https://s.shopee.com.br/e2e-fixture"


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg and ffprobe required")
class VideoEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.sample = pathlib.Path(cls.fixture.name) / "test-source.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
            "testsrc2=size=320x180:rate=10", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "3.2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(cls.sample),
        ], check=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.output = self.root / "packages"
        self.queue = self.root / "queue.json"
        self.common = ["--queue", str(self.queue), "--sources", str(self.root / "sources.json"), "--output", str(self.output)]
        self.requests = []
        self.deny_listing = False
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict("os.environ", {"SHOPEE_APP_ID": "e2e-test", "SHOPEE_SECRET": "e2e-test"}))
        self.stack.enter_context(patch("urllib.request.OpenerDirector.open", autospec=True, side_effect=self.http))

    def http(self, opener, request, *args, **kwargs):
        url = request.full_url if hasattr(request, "full_url") else request
        self.requests.append(url)
        if url == shopee.URL:
            payload = json.loads(request.data)
            if "productOfferV2" in payload["query"]:
                data = {"data": {"productOfferV2": {"nodes": [PRODUCT]}}}
            elif "generateShortLink" in payload["query"]:
                self.assertEqual(payload["variables"]["u"], PRODUCT["productLink"])
                self.assertEqual(payload["variables"]["s"], ["sv123x456"])
                data = {"data": {"generateShortLink": {"shortLink": AFFILIATE_URL}}}
            else:
                self.fail("Unexpected Affiliate API operation")
            body = json.dumps(data).encode()
        elif url == PRODUCT["productLink"]:
            if self.deny_listing:
                raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
            body = (f'<link rel="canonical" href="{url}"><meta property="og:video" content="{VIDEO_URL}">').encode()
        elif url == VIDEO_URL:
            body = self.sample.read_bytes()
        else:
            self.fail(f"Unexpected network request: {url}")
        response = io.BytesIO(body)
        response.url = url
        response.headers = {"Content-Length": str(len(body))}
        return response

    def cli(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return videos.main(self.common + list(args))

    def test_full_preparation_download_conversion_link_package_and_verification(self):
        self.assertEqual(self.cli("prepare", "--limit", "1", "--require-ready"), 0)
        self.assertIn(PRODUCT["productLink"], self.requests)
        self.assertIn(VIDEO_URL, self.requests)
        self.assertEqual(self.cli("verify"), 0)
        verification = json.loads((self.output / "verification.json").read_text())
        self.assertEqual(verification["verified"], 1)
        self.assertEqual((self.output / "sv-123-456" / "original.mp4").read_bytes(), self.sample.read_bytes())
        queue = json.loads(self.queue.read_text())
        self.assertEqual(queue["jobs"][0]["affiliate_link"], AFFILIATE_URL)
        self.assertEqual(queue["jobs"][0]["status"], "ready")
        # Repeating selection cannot download or generate links for the same product.
        requests_before = self.requests.count(VIDEO_URL)
        self.assertEqual(self.cli("prepare", "--limit", "1"), 0)
        self.assertEqual(self.requests.count(VIDEO_URL), requests_before)
        self.assertEqual(len(json.loads(self.queue.read_text())["jobs"]), 1)

    def test_verification_detects_modified_video_and_wrong_product(self):
        self.assertEqual(self.cli("prepare", "--limit", "1", "--require-ready"), 0)
        folder = self.output / "sv-123-456"
        manifest_path = folder / "publication.json"
        manifest = json.loads(manifest_path.read_text())
        wrong = dict(manifest, product=dict(manifest["product"], item_id="999"))
        manifest_path.write_text(json.dumps(wrong))
        self.assertEqual(self.cli("verify"), 1)
        manifest_path.write_text(json.dumps(manifest))
        with (folder / "video.mp4").open("ab") as stream:
            stream.write(b"tampered")
        self.assertEqual(self.cli("verify"), 1)

    def test_live_source_failure_is_not_reported_as_end_to_end_success(self):
        self.deny_listing = True
        self.assertEqual(self.cli("prepare", "--limit", "1", "--require-ready"), 2)
        self.assertEqual(self.cli("verify"), 1)
        queue = json.loads(self.queue.read_text())
        self.assertEqual(queue["jobs"][0]["status"], "blocked")
        self.assertEqual(queue["jobs"][0]["error"]["code"], "http_error")
        self.assertNotIn(VIDEO_URL, self.requests)

    def test_explicit_product_uses_live_lookup_and_listing_bound_source(self):
        self.assertEqual(self.cli("prepare", "--product-url", PRODUCT["productLink"], "--require-ready"), 0)
        self.assertEqual(self.cli("verify"), 0)
        self.assertEqual(self.requests.count(VIDEO_URL), 1)


if __name__ == "__main__":
    unittest.main()
