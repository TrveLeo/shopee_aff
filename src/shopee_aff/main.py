"""Pick best unposted product -> caption -> Instagram -> update link-in-bio page."""
import json, os, pathlib, sys, time

from . import instagram, shopee, site

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "posted.json"
MIN_COMMISSION = 0.08  # 8%
MIN_RATING = 4.5
MIN_SALES = 50  # social proof; sortType=commission returns lots of 0-sales junk
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
    kw = KEYWORDS[int(time.time() // 43200) % len(KEYWORDS)]
    print("keyword:", kw)
    raw = {}
    for sort in (shopee.SORT_SALES, shopee.SORT_COMMISSION):
        for p in shopee.top_products(50, keyword=kw, cat_id=CAT_ID, sort=sort):
            raw[p["itemId"]] = p
    cands = [
        p for p in raw.values()
        if str(p["itemId"]) not in posted_ids
        and float(p.get("commissionRate") or 0) >= MIN_COMMISSION
        and float(p.get("ratingStar") or 0) >= MIN_RATING
        and p.get("imageUrl")
        and int(p.get("sales") or 0) >= MIN_SALES
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


def main() -> int:
    dry = os.environ.get("DRY_RUN", "1") == "1"
    items = load()
    p = pick({i["id"] for i in items})
    if not p:
        print("no candidate"); return 0
    sub_id = f"ig{time.strftime('%y%m%d%H')}x{p['itemId']}"  # one subId per post -> per-post sales
    link = shopee.short_link(p["productLink"], sub_id)
    cap = caption(p, link)
    print(cap, link, p["imageUrl"], sep="\n")
    if dry:
        return 0
    instagram.publish_image(p["imageUrl"], cap)
    items.append({"id": str(p["itemId"]), "name": p["productName"], "image": p["imageUrl"], "link": link, "sub_id": sub_id, "ts": int(time.time()),
                  "commission": p["commissionRate"], "price": p["priceMin"],
                  "discount": p.get("priceDiscountRate") or 0, "rating": p["ratingStar"], "sales": p["sales"]})
    STATE.write_text(json.dumps(items, ensure_ascii=False, indent=1))
    site.render(items)
    return 0


if __name__ == "__main__":
    sys.exit(main())
