"""Shopee Affiliate Open API (GraphQL). Stdlib only."""
import hashlib, json, os, time, urllib.request

URL = "https://open-api.affiliate.shopee.com.br/graphql"


def _call(query: str, variables: dict | None = None) -> dict:
    app_id, secret = os.environ["SHOPEE_APP_ID"], os.environ["SHOPEE_SECRET"]
    payload = json.dumps({"query": query, "variables": variables or {}}, separators=(",", ":"))
    ts = int(time.time())
    sig = hashlib.sha256(f"{app_id}{ts}{payload}{secret}".encode()).hexdigest()
    req = urllib.request.Request(
        URL,
        data=payload.encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"SHA256 Credential={app_id}, Timestamp={ts}, Signature={sig}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.load(r)
    if out.get("errors"):
        raise RuntimeError(out["errors"])
    return out["data"]


def top_products(limit: int = 30, page: int = 1, keyword: str = "", cat_id: int = 0) -> list[dict]:
    # sortType 2 = sales; listType 0 = all. Adjust in Shopee docs if needed.
    q = """
    query($limit:Int,$page:Int,$kw:String,$cat:Int64){
      productOfferV2(sortType:2, listType:0, limit:$limit, page:$page, keyword:$kw, productCatId:$cat){
        nodes{ itemId productName imageUrl priceMin priceMax commissionRate
               ratingStar sales shopName productLink offerLink }
      }
    }"""
    v = {"limit": limit, "page": page}
    if keyword:
        v["kw"] = keyword
    if cat_id:
        v["cat"] = cat_id
    return _call(q, v)["productOfferV2"]["nodes"]


def short_link(origin_url: str, sub_id: str = "ig") -> str:
    q = """
    mutation($u:String!,$s:[String!]){
      generateShortLink(input:{originUrl:$u, subIds:$s}){ shortLink }
    }"""
    return _call(q, {"u": origin_url, "s": [sub_id]})["generateShortLink"]["shortLink"]
