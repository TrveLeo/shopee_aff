import contextlib
import io
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from shopee_aff import video_store, videos
from shopee_aff.video_sources import SourceError, VideoSource


PRODUCT = {"itemId": 456, "shopId": 123, "productName": "Pote hermético", "priceMin": "25.90",
           "productLink": "https://shopee.com.br/product/123/456", "commissionRate": "0.10",
           "ratingStar": "4.8", "sales": 150, "imageUrl": "https://example.org/photo.jpg"}
SOURCE = VideoSource(PRODUCT["productLink"], "https://down-br.vod.susercontent.com/original.mp4", "registered_listing")


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.queue = self.root / "queue.json"
        self.sources = self.root / "sources.json"
        self.output = self.root / "output"
        self.products = self.root / "products.json"
        self.products.write_text(json.dumps([PRODUCT]), encoding="utf-8")
        self.common = ["--queue", str(self.queue), "--sources", str(self.sources), "--output", str(self.output)]
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict("os.environ", {"SHOPEE_APP_ID": "test", "SHOPEE_SECRET": "test"}))
        self.stack.enter_context(patch.object(videos.video_media, "require_tools"))
        self.resolve = self.stack.enter_context(patch.object(videos, "resolve", return_value=SOURCE))
        self.download = self.stack.enter_context(patch.object(videos.video_media, "download", side_effect=lambda url, path: (path.parent.mkdir(parents=True, exist_ok=True), path.write_bytes(b"original"))))
        self.transcode = self.stack.enter_context(patch.object(videos.video_media, "prepare", side_effect=lambda source, dest: (dest.write_bytes(b"prepared"), {"sha256": "digest", "duration": 15})[1]))
        self.stack.enter_context(patch.object(videos.video_media, "cover", side_effect=lambda video, dest: dest.write_bytes(b"cover")))
        self.link = self.stack.enter_context(patch.object(videos.shopee, "short_link", return_value="https://s.shopee.com.br/affiliate-test"))

    def run_cli(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return videos.main(self.common + list(args))

    def prepare(self, *extra):
        return self.run_cli("prepare", "--products-file", str(self.products), *extra)

    def state(self):
        return video_store.read(self.queue, "jobs")["jobs"]

    def test_prepare_creates_complete_package_and_distinct_captions(self):
        self.assertEqual(self.prepare(), 0)
        job = self.state()[0]
        self.assertEqual(job["status"], "ready")
        folder = self.output / job["id"]
        for name in ("original.mp4", "video.mp4", "cover.jpg", "caption-shopee.txt", "caption-external.txt", "affiliate-link.txt", "publication.json", "LEIA-ME.txt"):
            self.assertTrue((folder / name).is_file(), name)
        manifest = json.loads((folder / "publication.json").read_text())
        self.assertEqual(manifest["product"]["item_id"], "456")
        self.assertTrue(manifest["native_product_binding_required"])
        self.assertIn(job["affiliate_link"], manifest["captions"]["external"])
        self.assertNotIn(job["affiliate_link"], manifest["captions"]["shopee"])
        self.assertIn("25,90", manifest["captions"]["shopee"])
        self.assertEqual(job["source"]["product_url"], PRODUCT["productLink"])

    def test_ready_and_published_products_are_not_duplicated(self):
        self.prepare()
        self.prepare()
        self.assertEqual(self.run_cli("mark-published", "sv-123-456", "--publication-id", "native-1"), 0)
        self.prepare("--retry")
        self.assertEqual(len(self.state()), 1)
        self.assertEqual(self.state()[0]["status"], "published")
        self.assertEqual(self.link.call_count, 1)
        self.assertEqual(self.download.call_count, 1)

    def test_missing_original_video_never_generates_affiliate_link_or_ready_state(self):
        self.resolve.side_effect = SourceError("No original listing video.")
        self.prepare()
        job = self.state()[0]
        self.assertEqual(job["status"], "blocked")
        self.assertEqual(job["error"]["code"], "awaiting_source")
        self.link.assert_not_called()
        self.download.assert_not_called()
        self.assertEqual(self.run_cli("mark-published", job["id"], "--publication-id", "fake"), 1)

    def test_strict_validation_fails_when_no_package_is_prepared(self):
        self.resolve.side_effect = SourceError("No original listing video.")
        self.assertEqual(self.prepare("--require-ready"), 2)
        summary = json.loads((self.output / "preparation.json").read_text())
        self.assertEqual(summary["prepared"], 0)
        self.assertEqual(self.state()[0]["status"], "blocked")

    def test_blocked_job_requires_retry_and_recovers_without_duplicate(self):
        self.resolve.side_effect = SourceError("No original listing video.")
        self.prepare()
        self.resolve.side_effect = None
        self.prepare()
        self.assertEqual(self.resolve.call_count, 1)
        self.prepare("--retry")
        self.assertEqual(len(self.state()), 1)
        self.assertEqual(self.state()[0]["status"], "ready")
        self.assertEqual(self.state()[0]["attempts"], 2)

    def test_media_or_network_failure_is_recorded_without_false_success(self):
        for error in (videos.video_media.MediaError("No video stream."), urllib.error.HTTPError("https://cdn", 403, "Forbidden", {}, None)):
            with self.subTest(error=error):
                self.download.side_effect = error
                self.prepare("--retry")
                self.assertEqual(self.state()[0]["status"], "blocked")
                self.link.assert_not_called()

    def test_rebuild_reuses_affiliate_link_and_existing_identity(self):
        self.prepare()
        before = self.state()[0]
        self.assertEqual(self.run_cli("rebuild", before["id"]), 0)
        after = self.state()[0]
        self.assertEqual(before["sub_id"], after["sub_id"])
        self.assertEqual(before["affiliate_link"], after["affiliate_link"])
        self.assertEqual(self.link.call_count, 1)

    def test_registering_source_does_not_contact_shopee(self):
        result = self.run_cli("register-source", "--product-url", PRODUCT["productLink"],
                              "--video-url", SOURCE.video_url, "--rights-reference", "seller permission")
        self.assertEqual(result, 0)
        registry = video_store.read(self.sources, "sources")
        self.assertEqual(registry["sources"]["123:456"]["rights_reference"], "seller permission")
        self.download.assert_not_called()
        self.link.assert_not_called()

    def test_mismatched_product_ids_never_download_video(self):
        self.products.write_text(json.dumps([dict(PRODUCT, itemId=999)]))
        self.prepare()
        self.download.assert_not_called()

    def test_atomic_write_keeps_old_queue_on_serialization_failure(self):
        original = {"version": 1, "jobs": []}
        video_store.write(self.queue, original)
        with self.assertRaises(ValueError):
            video_store.write(self.queue, {"bad": float("nan")})
        self.assertEqual(video_store.read(self.queue, "jobs"), original)
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_concurrent_writer_is_refused(self):
        with video_store.locked(self.queue):
            self.assertEqual(self.prepare(), 1)
        self.download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
