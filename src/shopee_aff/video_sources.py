"""Resolve videos belonging to an exact Shopee product listing. Stdlib only."""
from __future__ import annotations

import html
from html.parser import HTMLParser
import json
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass


class SourceError(ValueError):
    pass


@dataclass(frozen=True)
class ProductRef:
    shop_id: str
    item_id: str

    @property
    def key(self) -> str:
        return f"{self.shop_id}:{self.item_id}"

    @property
    def url(self) -> str:
        return f"https://shopee.com.br/product/{self.shop_id}/{self.item_id}"

    @classmethod
    def from_url(cls, url: str) -> ProductRef:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {"shopee.com.br", "www.shopee.com.br"}:
            raise SourceError("Use the original https://shopee.com.br product URL, not a short link.")
        match = re.fullmatch(r"/product/(\d+)/(\d+)/?", parsed.path)
        if not match:
            match = re.search(r"-i\.(\d+)\.(\d+)/?$", parsed.path)
        if not match or any(int(v) <= 0 for v in match.groups()):
            raise SourceError("Product URL must contain both shopId and itemId.")
        return cls(*(str(int(v)) for v in match.groups()))

    @classmethod
    def from_product(cls, product: dict) -> ProductRef:
        ref = cls.from_url(product["productLink"])
        if ref.item_id != str(product["itemId"]):
            raise SourceError("Product URL and itemId refer to different products.")
        if product.get("shopId") and ref.shop_id != str(product["shopId"]):
            raise SourceError("Product URL and shopId refer to different shops.")
        return ref


@dataclass(frozen=True)
class VideoSource:
    product_url: str
    video_url: str
    method: str
    rights_reference: str = ""
    evidence_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def validate_video_url(url: str) -> str:
    """Only original Shopee/CDN HTTPS media, including on every redirect."""
    parsed = urllib.parse.urlsplit(url)
    hosts = ("susercontent.com", "shopeemobile.com", "shopee.com.br", "akamaihd.net")
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.port not in (None, 443)
            or not any(host == base or host.endswith("." + base) for base in hosts)):
        raise SourceError("Video URL must be HTTPS on a Shopee media CDN.")
    return url


class MediaRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_video_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _ListingHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.canonical = ""
        self.media = []
        self.documents = []
        self._script = None
        self._parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical = attrs.get("href", "")
        if tag == "meta" and attrs.get("property") in {"og:video", "og:video:url", "og:video:secure_url"}:
            self.media.append(attrs.get("content", ""))
        if tag == "script" and attrs.get("type", "").split(";")[0] in {"application/ld+json", "application/json"}:
            self._script = attrs.get("type")
            self._parts = []

    def handle_data(self, data):
        if self._script:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._script:
            try:
                self.documents.append(json.loads("".join(self._parts)))
            except (ValueError, RecursionError):
                pass
            self._script = None
            self._parts = []


def _urls(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for child in value:
            yield from _urls(child)
    elif isinstance(value, dict):
        for key in ("contentUrl", "videoUrl", "video_url", "play_url"):
            if value.get(key):
                yield from _urls(value[key])
        for key in ("video", "video_info_list", "video_list", "default_format", "format_list"):
            if value.get(key):
                yield from _urls(value[key])
        # A generic url is accepted only within a video object, never a Product.
        if value.get("url") and not value.get("@type") == "Product":
            yield from _urls(value["url"])


def _product_videos(value, ref: ProductRef):
    """Ignore recommendation videos belonging to a different product/shop."""
    if isinstance(value, list):
        for child in value:
            yield from _product_videos(child, ref)
    elif isinstance(value, dict):
        item = value.get("itemId", value.get("item_id", value.get("itemid")))
        shop = value.get("shopId", value.get("shop_id", value.get("shopid")))
        if item is not None or shop is not None:
            if str(item) == ref.item_id and str(shop) == ref.shop_id:
                for field in ("video", "videoUrl", "video_url", "video_info_list", "video_list"):
                    if value.get(field):
                        yield from _urls(value[field])
            else:
                return
        elif value.get("@type") == "Product":
            own_url = value.get("url", value.get("@id", ""))
            if not isinstance(own_url, str) or not own_url:
                return
            try:
                if ProductRef.from_url(own_url) != ref:
                    return
            except SourceError:
                return
            yield from _urls(value.get("video", []))
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from _product_videos(child, ref)


def extract_listing_video(document: str, ref: ProductRef) -> VideoSource:
    parser = _ListingHTML()
    parser.feed(document)
    if parser.canonical and ProductRef.from_url(parser.canonical) != ref:
        raise SourceError("Listing canonical URL points to a different product.")
    urls = list(parser.media)
    for data in parser.documents:
        urls.extend(_product_videos(data, ref))
    for url in urls:
        try:
            url = validate_video_url(html.unescape(url))
        except (ValueError, TypeError):
            continue
        return VideoSource(ref.url, url, "listing_metadata")
    raise SourceError("Listing has no accessible original video. Register its original CDN URL with register-source.")


def resolve(ref: ProductRef, registry: dict) -> VideoSource:
    entry = registry["sources"].get(ref.key)
    if entry:
        if ProductRef.from_url(entry["product_url"]) != ref:
            raise SourceError("Registered video belongs to a different product.")
        return VideoSource(ref.url, validate_video_url(entry["video_url"]), "registered_listing",
                           entry.get("rights_reference", ""), entry.get("evidence_url", ""))
    req = urllib.request.Request(ref.url, headers={"User-Agent": "shopee-aff-video/1.0", "Accept": "text/html"})
    # Never follow a login redirect or leave Shopee while resolving a listing.
    with urllib.request.build_opener(MediaRedirect()).open(req, timeout=25) as response:
        if ProductRef.from_url(response.url) != ref:
            raise SourceError("Listing redirected away from the requested product.")
        body = response.read(5_000_001)
        if len(body) > 5_000_000:
            raise SourceError("Listing HTML exceeds 5 MB.")
    return extract_listing_video(body.decode("utf-8", errors="replace"), ref)
