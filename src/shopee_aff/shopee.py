"""Shopee Affiliate Open API (GraphQL). Stdlib only."""
import hashlib, json, os, time, urllib.error, urllib.request

URL = "https://open-api.affiliate.shopee.com.br/graphql"


def _call(query: str, variables: dict | None = None, retries: int = 4) -> dict:
    """Shopee API is flaky ('System Error' 10000, 5xx). Retry w/ backoff; re-sign each try."""
    for i in range(retries):
        try:
            return _call_once(query, variables)
        except (RuntimeError, urllib.error.URLError, TimeoutError) as e:
            transient = isinstance(e, (urllib.error.URLError, TimeoutError)) or "10000" in str(e)
            if i == retries - 1 or not transient:
                raise
            time.sleep(2 ** i)


def _call_once(query: str, variables: dict | None = None) -> dict:
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


SORT_RELEVANCE, SORT_SALES, SORT_PRICE_DESC, SORT_PRICE_ASC, SORT_COMMISSION = 1, 2, 3, 4, 5


def top_products(limit: int = 30, page: int = 1, keyword: str = "", cat_id: int = 0,
                 sort: int = SORT_SALES) -> list[dict]:
    q = """
    query($limit:Int,$page:Int,$kw:String,$cat:Int,$sort:Int){
      productOfferV2(sortType:$sort, listType:0, limit:$limit, page:$page, keyword:$kw, productCatId:$cat){
        nodes{ itemId productName imageUrl priceMin priceMax commissionRate
               ratingStar sales shopName productLink offerLink productCatIds priceDiscountRate commission }
      }
    }"""
    v = {"limit": limit, "page": page, "sort": sort}
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


def conversions(start_ts: int, end_ts: int, limit: int = 500) -> list[dict]:
    """Conversions (sales) in window. utmContent = our subIds joined by '-'."""
    out, sid = [], ""
    while True:
        scroll = f', scrollId:"{sid}"' if sid else ""
        q = f"""
        {{ conversionReport(purchaseTimeStart:{int(start_ts)}, purchaseTimeEnd:{int(end_ts)}, limit:{min(limit, 500)}{scroll}){{
            nodes{{ purchaseTime conversionId conversionStatus utmContent totalCommission netCommission
                   orders{{ orderId orderStatus items{{ itemId itemName itemPrice qty itemTotalCommission }} }} }}
            pageInfo{{ hasNextPage scrollId }} }} }}"""
        d = _call(q)["conversionReport"]
        out += d["nodes"]
        pi = d.get("pageInfo") or {}
        if not pi.get("hasNextPage") or len(out) >= limit:
            return out
        sid = pi["scrollId"]
