"""Sales per post. Joins data/posted.json (sub_id) with Shopee conversionReport (utmContent)."""
import collections, json, pathlib, sys, time

from . import shopee

ROOT = pathlib.Path(__file__).resolve().parents[2]


def main(days: int = 30) -> int:
    posts = json.loads((ROOT / "data" / "posted.json").read_text())
    now = int(time.time())
    conv = shopee.conversions(now - days * 86400, now)
    by_sub = collections.defaultdict(lambda: {"n": 0, "comm": 0.0})
    for c in conv:
        k = (c.get("utmContent") or "").strip() or "(sem subId)"
        by_sub[k]["n"] += 1
        by_sub[k]["comm"] += float(c.get("netCommission") or c.get("totalCommission") or 0)
    print(f"{len(posts)} posts, {len(conv)} conversions, last {days}d\n")
    for p in sorted(posts, key=lambda p: -by_sub[p.get("sub_id", "")]["comm"]):
        s = by_sub[p.get("sub_id", "")]
        print(f'R$ {s["comm"]:7.2f}  {s["n"]:3d} vendas  {p["name"][:50]}')
    other = {k: v for k, v in by_sub.items() if k not in {p.get("sub_id") for p in posts}}
    if other:
        print("\nnao ligados a post:", {k: (v["n"], round(v["comm"], 2)) for k, v in other.items()})
    print(f'\ntotal R$ {sum(v["comm"] for v in by_sub.values()):.2f}')
    return 0


if __name__ == "__main__":
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 30))
