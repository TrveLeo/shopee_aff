"""Prepare original Shopee listing videos and an auditable upload queue.

This command prepares files; it never publishes to Shopee or Instagram.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import pathlib
import sys
import urllib.error

from . import main as products
from . import shopee, video_media, video_store, video_verify
from .video_sources import ProductRef, SourceError, resolve, validate_video_url


ROOT = pathlib.Path(__file__).resolve().parents[2]


class QueueError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def job_id(ref: ProductRef) -> str:
    return f"sv-{ref.shop_id}-{ref.item_id}"


def captions(product: dict, link: str) -> dict[str, str]:
    price = f"{float(product['priceMin']):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    base = (
        f"{product['productName'][:120]}\n"
        f"A partir de R$ {price}. Confira preço e disponibilidade no anúncio.\n\n"
    )
    disclosure = "Publicidade: posso receber comissão pelas compras.\n#achadinhosshopee #casa #cozinha"
    return {
        "shopee": base + "Veja o produto vinculado ao vídeo na sacolinha.\n\n" + disclosure,
        "external": base + f"Compre pelo meu link de afiliado: {link}\n\n" + disclosure,
    }


def _failure(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, urllib.error.HTTPError):
        return "http_error", f"Source HTTP {exc.code}; no login or verification bypass was attempted."
    if isinstance(exc, (urllib.error.URLError, TimeoutError)):
        return "network_error", "Source unavailable or network timeout; retry later."
    if isinstance(exc, SourceError):
        return "awaiting_source", str(exc)
    if isinstance(exc, video_media.MediaError):
        return "invalid_media", str(exc)
    if isinstance(exc, QueueError):
        return "configuration_error", str(exc)
    # Never serialize exception messages containing credentials or signed URLs.
    return "preparation_error", f"Preparation failed ({type(exc).__name__})."


def _bundle(job: dict, output: pathlib.Path) -> None:
    folder = output / job["id"]
    texts = captions(job["product"], job["affiliate_link"])
    for channel, text in texts.items():
        (folder / f"caption-{channel}.txt").write_text(text + "\n", encoding="utf-8")
    (folder / "affiliate-link.txt").write_text(job["affiliate_link"] + "\n", encoding="utf-8")
    (folder / "LEIA-ME.txt").write_text(
        f"Produto: {job['product']['productName']}\nAnúncio: {job['product_url']}\n"
        f"Loja: {job['shop_id']} | Item: {job['item_id']}\n\n"
        "Envie video.mp4 e use caption-shopee.txt na Shopee. Vincule exatamente o produto acima "
        "na sacolinha antes de publicar. O link de afiliado na legenda não substitui essa vinculação.\n"
        "cover.jpg é uma capa opcional. original.mp4 é o arquivo do anúncio, sem alteração.\n"
        "Para canais externos, use caption-external.txt e affiliate-link.txt.\n"
        "Confira a autorização do vendedor para reutilizar o vídeo e o preço atual.\n"
        "O preparo deste pacote não publicou nenhum conteúdo.\n",
        encoding="utf-8",
    )
    video_store.write(folder / "publication.json", {
        "version": 1,
        "job_id": job["id"],
        "channel": "shopee_video",
        "status": "ready_for_native_upload",
        "product": {"shop_id": job["shop_id"], "item_id": job["item_id"],
                    "url": job["product_url"], "name": job["product"]["productName"]},
        "affiliate_link": job["affiliate_link"],
        "sub_id": job["sub_id"],
        "source": job["source"],
        "video_file": "video.mp4",
        "original_file": "original.mp4",
        "cover_file": "cover.jpg",
        "media": job["media"],
        "captions": texts,
        "native_product_binding_required": True,
        "prepared_at": job["updated_at"],
    })


def prepare_job(job: dict, registry: dict, output: pathlib.Path) -> None:
    ref = ProductRef.from_product(job["product"])
    if job_id(ref) != job["id"]:
        raise SourceError("Queue job ID does not match its product.")
    source = resolve(ref, registry)
    job["source"] = source.to_dict()
    folder = output / job["id"]
    original, prepared = folder / "original.mp4", folder / "video.mp4"
    video_media.download(source.video_url, original)
    job["media"] = video_media.prepare(original, prepared)
    video_media.cover(prepared, folder / "cover.jpg")
    if not job.get("affiliate_link"):
        require_credentials()
        job["affiliate_link"] = shopee.short_link(ref.url, job["sub_id"])
    job["updated_at"] = now()
    _bundle(job, output)
    job["status"] = "ready"
    job["error"] = None
    job["artifact_run_id"] = os.environ.get("GITHUB_RUN_ID", "")


def prepare_queue(args) -> int:
    video_media.require_tools()
    if not args.products_file:
        require_credentials()
    registry = video_store.read(args.sources, "sources")
    with video_store.locked(args.queue):
        queue = video_store.read(args.queue, "jobs")
        existing = {entry["id"]: entry for entry in queue["jobs"]}
        blocked_ids = {entry["item_id"] for entry in queue["jobs"]
                       if entry["status"] in {"ready", "published"} or not args.retry}
        if args.products_file:
            selected = json.loads(args.products_file.read_text(encoding="utf-8"))
            if not isinstance(selected, list):
                raise ValueError("Products file must contain a JSON array of Affiliate API products.")
            selected = [p for p in selected if str(p["itemId"]) not in blocked_ids]
        elif args.product_url:
            ref = ProductRef.from_url(args.product_url)
            product = shopee.product_offer(int(ref.shop_id), int(ref.item_id))
            if not product:
                raise QueueError("Selected product is not available in the Affiliate API.")
            selected = [product]
        else:
            selected = products.candidates(blocked_ids)
        prepared_count = 0
        scanned = 0
        for product in selected[:args.scan_limit]:
            if prepared_count >= args.limit:
                break
            scanned += 1
            try:
                ref = ProductRef.from_product(product)
            except (SourceError, KeyError, TypeError, ValueError) as exc:
                print(f"Skipped invalid product: {type(exc).__name__}")
                continue
            identifier = job_id(ref)
            job = existing.get(identifier)
            if job and (job["status"] in {"ready", "published"} or not args.retry):
                continue
            if job is None:
                job = {
                    "id": identifier, "channel": "shopee_video", "item_id": ref.item_id,
                    "shop_id": ref.shop_id, "product_url": ref.url,
                    "sub_id": f"sv{ref.shop_id}x{ref.item_id}",
                    "product": product, "created_at": now(), "attempts": 0,
                }
                queue["jobs"].append(job)
                existing[identifier] = job
            else:
                job["product"] = product
            job.update(status="preparing", attempts=job["attempts"] + 1, updated_at=now())
            video_store.write(args.queue, queue)
            try:
                prepare_job(job, registry, args.output)
            except (SourceError, video_media.MediaError, urllib.error.URLError,
                    TimeoutError, RuntimeError, ValueError, KeyError, OSError) as exc:
                code, message = _failure(exc)
                job.update(status="blocked", error={"code": code, "message": message}, updated_at=now())
                print(f"{identifier}: blocked ({code}): {message}")
            else:
                prepared_count += 1
                print(f"{identifier}: ready -> {args.output / identifier}")
            video_store.write(args.queue, queue)
        args.output.mkdir(parents=True, exist_ok=True)
        video_store.write(args.output / "queue.json", queue)
        video_store.write(args.output / "preparation.json", {
            "version": 1, "prepared": prepared_count, "inspected": scanned,
            "completed_at": now(), "artifact_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        })
        print(f"Prepared {prepared_count} video(s); inspected {scanned} product(s). No publication was made.")
        if args.require_ready and not prepared_count:
            print("Validation failed: no real upload package was prepared.", file=sys.stderr)
            return 2
    return 0


def require_credentials() -> None:
    missing = [key for key in ("SHOPEE_APP_ID", "SHOPEE_SECRET") if not os.environ.get(key)]
    if missing:
        raise QueueError("Configure Affiliate API credentials: " + ", ".join(missing))


def register_source(args) -> int:
    ref = ProductRef.from_url(args.product_url)
    url = validate_video_url(args.video_url)
    with video_store.locked(args.sources):
        registry = video_store.read(args.sources, "sources")
        registry["sources"][ref.key] = {
            "product_url": ref.url, "video_url": url,
            "rights_reference": args.rights_reference, "evidence_url": args.evidence_url, "registered_at": now(),
        }
        video_store.write(args.sources, registry)
    print(f"Registered original listing video for {ref.key}. Use prepare --retry to process blocked jobs.")
    return 0


def rebuild(args) -> int:
    video_media.require_tools()
    registry = video_store.read(args.sources, "sources")
    with video_store.locked(args.queue):
        queue = video_store.read(args.queue, "jobs")
        job = next((job for job in queue["jobs"] if job["id"] == args.job_id), None)
        if not job or job["status"] != "ready":
            raise QueueError("Only a ready job can be rebuilt. Use prepare --retry for blocked jobs.")
        try:
            prepare_job(job, registry, args.output)
        except (SourceError, video_media.MediaError, urllib.error.URLError,
                TimeoutError, RuntimeError, ValueError, KeyError, OSError) as exc:
            code, message = _failure(exc)
            job.update(status="blocked", error={"code": code, "message": message}, updated_at=now())
            video_store.write(args.queue, queue)
            raise QueueError(message) from exc
        video_store.write(args.queue, queue)
        video_store.write(args.output / "queue.json", queue)
    print(f"Rebuilt {job['id']} with the existing affiliate link. No publication was made.")
    return 0


def mark_published(args) -> int:
    with video_store.locked(args.queue):
        queue = video_store.read(args.queue, "jobs")
        job = next((job for job in queue["jobs"] if job["id"] == args.job_id), None)
        if not job or job["status"] != "ready":
            raise QueueError("Only a ready job can be marked published.")
        publication_id = args.publication_id.strip()
        if not publication_id:
            raise QueueError("The actual publication ID or URL is required.")
        job.update(status="published", publication_id=publication_id, published_at=now(),
                   publication_recorded_by="manual", updated_at=now())
        video_store.write(args.queue, queue)
    print(f"Recorded native publication of {job['id']}.")
    return 0


def status(args) -> int:
    queue = video_store.read(args.queue, "jobs")
    if not queue["jobs"]:
        print("Video queue is empty.")
    for job in queue["jobs"]:
        error = (job.get("error") or {}).get("code", "")
        print(f"{job['id']}  {job['status']}  attempts={job['attempts']}  {error}")
    return 0


def verify(args) -> int:
    video_media.require_tools()
    results = []
    queue = video_store.read(args.queue, "jobs")
    jobs = {job["id"]: job for job in queue["jobs"]}
    for manifest in sorted(args.output.glob("sv-*/publication.json")):
        result = video_verify.verify_bundle(manifest.parent)
        job = jobs.get(result["job_id"])
        if (not job or job["status"] not in {"ready", "published"}
                or job["media"]["sha256"] != result["sha256"]):
            raise QueueError("Package does not match a ready/published entry in the queue.")
        results.append(result)
    if not results and not args.allow_empty:
        raise QueueError("No upload package is available to verify.")
    video_store.write(args.output / "verification.json", {
        "version": 1, "verified_at": now(), "verified": len(results), "packages": results,
    })
    print(f"Verified {len(results)} upload package(s) against actual media, captions, links and checksums.")
    return 0


def positive(value: str) -> int:
    number = int(value)
    if not 1 <= number <= 50:
        raise argparse.ArgumentTypeError("Use a value between 1 and 50.")
    return number


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--queue", type=pathlib.Path, default=ROOT / "data" / "video_queue.json")
    root.add_argument("--sources", type=pathlib.Path, default=ROOT / "data" / "video_sources.json")
    root.add_argument("--output", type=pathlib.Path, default=ROOT / "artifacts" / "videos")
    commands = root.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Discover original listing videos and build upload packages.")
    prepare.add_argument("--limit", type=positive, default=3)
    prepare.add_argument("--scan-limit", type=positive, default=15)
    prepare.add_argument("--retry", action="store_true", help="Retry blocked or interrupted preparation jobs.")
    prepare.add_argument("--require-ready", action="store_true", help="Fail if no real upload package is prepared.")
    selection = prepare.add_mutually_exclusive_group()
    selection.add_argument("--products-file", type=pathlib.Path, help="Affiliate API product array; otherwise fetch live offers.")
    selection.add_argument("--product-url", help="Fetch an explicitly selected product from the live Affiliate API.")
    prepare.set_defaults(run=prepare_queue)
    source = commands.add_parser("register-source", help="Register the original video URL obtained from a product listing.")
    source.add_argument("--product-url", required=True)
    source.add_argument("--video-url", required=True)
    source.add_argument("--rights-reference", default="", help="Optional reference to seller permission for reuse.")
    source.add_argument("--evidence-url", default="", help="Optional URL documenting the listing-to-video association.")
    source.set_defaults(run=register_source)
    commands.add_parser("status", help="Inspect queue without contacting any service.").set_defaults(run=status)
    restore = commands.add_parser("rebuild", help="Download and recreate the files of a ready job.")
    restore.add_argument("job_id")
    restore.set_defaults(run=rebuild)
    published = commands.add_parser("mark-published", help="Record a publication completed in Shopee's native interface.")
    published.add_argument("job_id")
    published.add_argument("--publication-id", required=True)
    published.set_defaults(run=mark_published)
    verification = commands.add_parser("verify", help="Verify actual package files, checksums, media and queue identity.")
    verification.add_argument("--allow-empty", action="store_true", help="Allow routine runs that produced no new packages.")
    verification.set_defaults(run=verify)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.run(args)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        code, message = _failure(exc)
        if isinstance(exc, QueueError):
            message = str(exc)
        elif not isinstance(exc, (SourceError, video_media.MediaError)):
            message = "Check configuration, credentials, state file format and filesystem permissions."
        print(f"Video pipeline error ({code}): {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
