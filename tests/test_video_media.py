import pathlib
import shutil
import subprocess
import tempfile
import unittest

from shopee_aff import video_media


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg and ffprobe are required for integration tests")
class MediaIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)

    def test_real_landscape_video_becomes_vertical_and_retains_original(self):
        original = self.root / "original.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "3.2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(original),
        ], check=True, timeout=30)
        original_hash = video_media.sha256(original)
        prepared = self.root / "video.mp4"
        metadata = video_media.prepare(original, prepared)
        self.assertEqual(video_media.sha256(original), original_hash)
        self.assertEqual(metadata["original_sha256"], original_hash)
        self.assertEqual((metadata["prepared"]["width"], metadata["prepared"]["height"]), (1080, 1920))
        self.assertTrue(metadata["prepared"]["audio"])
        self.assertEqual(metadata["prepared"]["codec"], "h264")
        self.assertFalse(metadata["trimmed"])
        video_media.cover(prepared, self.root / "cover.jpg")
        self.assertGreater((self.root / "cover.jpg").stat().st_size, 0)
        self.assertFalse(list(self.root.glob("*.part.*")))

    def test_html_disguised_as_mp4_is_rejected(self):
        original = self.root / "original.mp4"
        original.write_text("<html>Please log in</html>")
        with self.assertRaises(video_media.MediaError):
            video_media.prepare(original, self.root / "video.mp4")
        self.assertFalse((self.root / "video.mp4").exists())

    def test_too_short_video_is_rejected(self):
        original = self.root / "original.mp4"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10", "-t", "1",
            "-c:v", "libx264", str(original),
        ], check=True, timeout=30)
        with self.assertRaises(video_media.MediaError):
            video_media.prepare(original, self.root / "video.mp4")


if __name__ == "__main__":
    unittest.main()
