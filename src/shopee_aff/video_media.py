"""Download an original listing video and prepare an MP4 without cropping it."""
from __future__ import annotations

import hashlib
import json
import math
import pathlib
import shutil
import subprocess
import urllib.request

from .video_sources import MediaRedirect, validate_video_url


class MediaError(RuntimeError):
    pass


MAX_BYTES = 100 * 1024 * 1024


def require_tools() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if not shutil.which(name)]
    if missing:
        raise MediaError("Install FFmpeg (including ffprobe) before preparing videos: " + ", ".join(missing))


def sha256(path: pathlib.Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(url: str, destination: pathlib.Path) -> None:
    validate_video_url(url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "shopee-aff-video/1.0"})
    try:
        with urllib.request.build_opener(MediaRedirect()).open(request, timeout=45) as response, partial.open("wb") as stream:
            validate_video_url(response.url)
            length = int(response.headers.get("Content-Length") or 0)
            if length > MAX_BYTES:
                raise MediaError("Original video exceeds the 100 MiB download limit.")
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_BYTES:
                    raise MediaError("Original video exceeds the 100 MiB download limit.")
                stream.write(chunk)
            if not total or (length and total != length):
                raise MediaError("Original video download is empty or incomplete.")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def _run(args: list[str], timeout: int) -> str:
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout).stdout
    except FileNotFoundError as exc:
        raise MediaError("FFmpeg/ffprobe is not installed.") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError("Video processing timed out.") from exc
    except subprocess.CalledProcessError as exc:
        # FFmpeg stderr may contain signed source URLs. Keep errors local and terse.
        raise MediaError(f"{pathlib.Path(args[0]).name} could not process the video (exit {exc.returncode}).") from exc


def probe(path: pathlib.Path) -> dict:
    data = json.loads(_run([
        "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
        "-show_entries", "format=duration,format_name:stream=codec_type,codec_name,width,height,duration",
        "-of", "json", str(path),
    ], timeout=30))
    videos = [stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"]
    if not videos:
        raise MediaError("Downloaded file contains no video stream.")
    video = videos[0]
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    if not math.isfinite(duration) or duration < 3:
        raise MediaError("Video duration must be at least 3 seconds.")
    if not video.get("width") or not video.get("height"):
        raise MediaError("Video dimensions are unavailable.")
    return {
        "duration": duration,
        "width": int(video["width"]),
        "height": int(video["height"]),
        "codec": video.get("codec_name", ""),
        "audio": any(stream.get("codec_type") == "audio" for stream in data.get("streams", [])),
    }


def prepare(source: pathlib.Path, destination: pathlib.Path) -> dict:
    require_tools()
    original = probe(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(".part.mp4")
    try:
        _run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-protocol_whitelist", "file,pipe", "-i", str(source),
            "-map", "0:v:0", "-map", "0:a:0?", "-t", "60",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,"
                   "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30",
            "-c:v", "libx264", "-threads", "2", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart",
            "-map_metadata", "-1", str(partial),
        ], timeout=300)
        result = probe(partial)
        if result["duration"] > 60.1 or result["codec"] != "h264" or (result["width"], result["height"]) != (1080, 1920):
            raise MediaError("Prepared video does not meet the output profile.")
        if partial.stat().st_size > MAX_BYTES:
            raise MediaError("Prepared video exceeds 100 MiB.")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)
    return {"original": original, "prepared": result, "sha256": sha256(destination),
            "original_sha256": sha256(source), "bytes": destination.stat().st_size,
            "trimmed": original["duration"] > 60}


def cover(video: pathlib.Path, destination: pathlib.Path) -> None:
    temporary = destination.with_suffix(".part.jpg")
    try:
        _run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-protocol_whitelist", "file,pipe", "-ss", "0.5", "-i", str(video),
            "-frames:v", "1", "-vf", "scale=540:960", "-q:v", "2", str(temporary),
        ], timeout=30)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
