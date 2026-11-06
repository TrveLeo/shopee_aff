"""Pick best unposted product -> caption -> Instagram -> update link-in-bio page."""
import html, json, os, pathlib, sys

from . import instagram, shopee

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "posted.json"
SITE = ROOT / "site" / "index.html"
MIN_COMMISSION = 0.08  # 8%
MIN_RATING = 4.5
MIN_PRICE, MAX_PRICE = 10, 120  # impulse-buy range (R$)
CAT_ID = int(os.environ.get("SHOPEE_CAT_ID") or 0)  # optional: Home & Living category id
# niche: casa & cozinha. One keyword per run, rotated by day/slot.
KEYWORDS = [
    "organizador cozinha", "porta temperos", "utensilios cozinha silicone", "pote hermetico",
    "organizador geladeira", "escorredor louca", "tapete cozinha", "panela antiaderente",
    "faca cozinha", "mini processador", "airfryer acessorios", "organizador banheiro",
    "gancho adesivo", "lixeira pia", "tabua corte", "toalha microfibra", "cesto organizador",
    "luminaria led cozinha", "dispenser sabao", "ralador multifuncional",
]


def load() -> list[dict]:
    return json.loads(STATE.read_text()) if STATE.exists() else []


def pick(posted_ids: set[str]) -> dict | None:
    import time
    kw = KEYWORDS[int(time.time() // 43200) % len(KEYWORDS)]
    print("keyword:", kw)
    cands = [
        p for p in shopee.top_products(50, keyword=kw, cat_id=CAT_ID)
        if str(p["itemId"]) not in posted_ids
        and float(p.get("commissionRate") or 0) >= MIN_COMMISSION
        and float(p.get("ratingStar") or 0) >= MIN_RATING
        and p.get("imageUrl")
        and MIN_PRICE <= float(p.get("priceMin") or 0) <= MAX_PRICE
    ]
    cands.sort(key=lambda p: float(p["commissionRate"]) * float(p["priceMin"] or 0), reverse=True)
    return cands[0] if cands else None


def caption(p: dict, link: str) -> str:
    price = float(p["priceMin"])
    return (
        f"🔥 {p['productName'][:90]}\n\n"
        f"💰 A partir de R$ {price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        + f"\n⭐ {p['ratingStar']} | 🛒 {p['sales']} vendidos\n\n"
        f"👉 Link na bio\n\n#achadinhosdacasa #achadinhosshopee #casa #cozinha #organizacao #utilidadesdomesticas"
    )


def render_site(items: list[dict]) -> None:
    rows = "\n".join(
        f'<a class="c" href="{html.escape(i["link"])}" rel="sponsored nofollow">'
        f'<img src="{html.escape(i["image"])}" loading="lazy"><span>{html.escape(i["name"][:80])}</span></a>'
        for i in reversed(items[-30:])
    )
    SITE.write_text(
        '<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">'
        "<title>Achadinhos</title><style>body{font:16px system-ui;max-width:480px;margin:auto;padding:16px}"
        ".c{display:flex;gap:12px;align-items:center;margin:12px 0;color:inherit;text-decoration:none}"
        ".c img{width:80px;height:80px;object-fit:cover;border-radius:8px}</style>"
        f"<h1>Achadinhos p/ Casa & Cozinha</h1>{rows}"
    )


def main() -> int:
    dry = os.environ.get("DRY_RUN", "1") == "1"
    items = load()
    p = pick({i["id"] for i in items})
    if not p:
        print("no candidate"); return 0
    link = shopee.short_link(p["offerLink"] or p["productLink"])
    cap = caption(p, link)
    print(cap, link, p["imageUrl"], sep="\n")
    if dry:
        return 0
    instagram.publish_image(p["imageUrl"], cap)
    items.append({"id": str(p["itemId"]), "name": p["productName"], "image": p["imageUrl"], "link": link})
    STATE.write_text(json.dumps(items, ensure_ascii=False, indent=1))
    render_site(items)
    return 0


if __name__ == "__main__":
    sys.exit(main())
