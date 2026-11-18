"""Verify upload packages from their actual files, independently of queue success."""
from __future__ import annotations

import json
import pathlib
import urllib.parse

from . import video_media
from .video_sources import ProductRef, validate_video_url


def verify_bundle(folder: pathlib.Path) -> dict:
    required = ("publication.json", "original.mp4", "video.mp4", "cover.jpg",
                "caption-shopee.txt", "caption-external.txt", "affiliate-link.txt", "LEIA-ME.txt")
    for name in required:
        path = folder / name
        if not path.is_file() or path.is_symlink() or not path.stat().st_size:
            raise ValueError(f"Missing or invalid package file: {name}")
    manifest = json.loads((folder / "publication.json").read_text(encoding="utf-8"))
    product = manifest["product"]
    ref = ProductRef.from_url(product["url"])
    identifier = f"sv-{ref.shop_id}-{ref.item_id}"
    if (folder.name != identifier or manifest["job_id"] != identifier
            or product["shop_id"] != ref.shop_id or product["item_id"] != ref.item_id
            or ProductRef.from_url(manifest["source"]["product_url"]) != ref):
        raise ValueError("Package product identity does not match its source.")
    validate_video_url(manifest["source"]["video_url"])
    if manifest.get("native_product_binding_required") is not True:
        raise ValueError("Package does not require the native Shopee product binding.")
    link = manifest["affiliate_link"]
    url = urllib.parse.urlsplit(link)
    if (url.scheme != "https" or url.hostname not in {"s.shopee.com.br", "shope.ee", "shp.ee"}
            or url.username or url.password):
        raise ValueError("Package does not contain a valid Shopee affiliate URL.")
    if (folder / "affiliate-link.txt").read_text(encoding="utf-8").strip() != link:
        raise ValueError("Affiliate link file differs from the manifest.")
    for channel in ("shopee", "external"):
        text = (folder / f"caption-{channel}.txt").read_text(encoding="utf-8")
        if text != manifest["captions"][channel] + "\n":
            raise ValueError("Caption file differs from the manifest.")
    if link not in manifest["captions"]["external"] or link in manifest["captions"]["shopee"]:
        raise ValueError("Affiliate link is not assigned to the correct channel caption.")
    media = manifest["media"]
    for filename, field in (("original.mp4", "original_sha256"), ("video.mp4", "sha256")):
        if video_media.sha256(folder / filename) != media[field]:
            raise ValueError(f"Package checksum does not match: {filename}")
    original = video_media.probe(folder / "original.mp4")
    prepared = video_media.probe(folder / "video.mp4")
    if ((prepared["width"], prepared["height"]) != (1080, 1920)
            or prepared["codec"] != "h264" or prepared["duration"] > 60.1
            or (original["audio"] and not prepared["audio"])):
        raise ValueError("Prepared video or audio does not meet the upload profile.")
    if (folder / "video.mp4").stat().st_size != media["bytes"]:
        raise ValueError("Prepared video size differs from the manifest.")
    cover = (folder / "cover.jpg").read_bytes()
    if not cover.startswith(b"\xff\xd8") or not cover.endswith(b"\xff\xd9"):
        raise ValueError("Package cover is not a JPEG image.")
    return {"job_id": identifier, "sha256": media["sha256"], "original_sha256": media["original_sha256"],
            "bytes": media["bytes"], "duration": prepared["duration"], "product_url": ref.url}
