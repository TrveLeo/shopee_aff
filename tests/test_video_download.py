import pathlib
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.request

from shopee_aff import video_media
from shopee_aff.video_sources import MediaRedirect, SourceError


URL = "https://down-br.vod.susercontent.com/original.mp4"


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.destination = pathlib.Path(self.temp.name) / "original.mp4"
        self.opener = MagicMock()
        self.response = self.opener.open.return_value.__enter__.return_value
        self.response.url = URL
        self.response.headers = {"Content-Length": "5"}
        self.response.read.side_effect = [b"video", b""]

    def test_original_bytes_are_downloaded_atomically(self):
        with patch("urllib.request.build_opener", return_value=self.opener):
            video_media.download(URL, self.destination)
        self.assertEqual(self.destination.read_bytes(), b"video")
        self.assertFalse(self.destination.with_suffix(".mp4.part").exists())

    def test_truncated_download_does_not_replace_existing_original(self):
        self.destination.write_bytes(b"previous")
        self.response.headers = {"Content-Length": "100"}
        with patch("urllib.request.build_opener", return_value=self.opener):
            with self.assertRaises(video_media.MediaError):
                video_media.download(URL, self.destination)
        self.assertEqual(self.destination.read_bytes(), b"previous")
        self.assertFalse(self.destination.with_suffix(".mp4.part").exists())

    def test_oversized_download_is_stopped_before_reading_body(self):
        self.response.headers = {"Content-Length": str(video_media.MAX_BYTES + 1)}
        with patch("urllib.request.build_opener", return_value=self.opener):
            with self.assertRaises(video_media.MediaError):
                video_media.download(URL, self.destination)
        self.response.read.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_untrusted_redirect_is_rejected(self):
        request = urllib.request.Request(URL)
        with self.assertRaises(SourceError):
            MediaRedirect().redirect_request(request, None, 302, "Found", {}, "https://localhost/private.mp4")


if __name__ == "__main__":
    unittest.main()
