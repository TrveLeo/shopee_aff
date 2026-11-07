"""Link-in-bio page generator -> docs/index.html (GitHub Pages serves /docs). Static, no JS needed."""
import html, os, pathlib, time

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "index.html"
BRAND = os.environ.get("BRAND_NAME", "Achadinhos da Casa")
TAGLINE = "Os achadinhos de casa e cozinha mais vendidos da Shopee, direto pra você 🏠"
HANDLE = os.environ.get("IG_HANDLE", "")  # e.g. achadinhosdacasa
MAX_ITEMS = 40
NEW_DAYS = 3

CSS = """
:root{--bg:#fff7f2;--card:#fff;--ink:#241a16;--mute:#7a6a62;--brand:#ee4d2d;--brand-ink:#fff;--line:#f0e2da;--chip:#ffe9e1}
@media(prefers-color-scheme:dark){:root{--bg:#17110e;--card:#241b17;--ink:#f6ece6;--mute:#b3a199;--line:#352a24;--chip:#3a2219}}
*{box-sizing:border-box;margin:0}
body{font:16px/1.4 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--ink);padding:0 16px 40px}
.w{max-width:560px;margin:auto}
header{text-align:center;padding:32px 0 20px}
.logo{width:76px;height:76px;border-radius:50%;background:var(--brand);color:var(--brand-ink);display:grid;place-items:center;font-size:36px;margin:0 auto 12px}
h1{font-size:22px;letter-spacing:-.01em}
.tag{color:var(--mute);font-size:14px;margin-top:6px}
.ig{display:inline-block;margin-top:12px;font-size:14px;color:var(--brand);text-decoration:none;font-weight:600}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-top:8px}
.c{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;display:flex;flex-direction:column;text-decoration:none;color:inherit}
.im{position:relative;aspect-ratio:1;background:var(--line)}
.im img{width:100%;height:100%;object-fit:cover;display:block}
.b{position:absolute;top:8px;left:8px;background:var(--brand);color:var(--brand-ink);font-size:12px;font-weight:700;padding:2px 8px;border-radius:99px}
.b.n{left:auto;right:8px;background:#1f9d55}
.t{padding:10px 10px 4px;font-size:13px;line-height:1.3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;height:calc(2.6em + 10px);padding-bottom:0}
.p{padding:0 10px;font-weight:700;font-size:17px}
.s{padding:0 10px;color:var(--mute);font-size:12px;margin-top:2px}
.btn{margin:10px;background:var(--brand);color:var(--brand-ink);text-align:center;padding:9px;border-radius:10px;font-weight:700;font-size:14px}
.c:hover .btn,.c:focus-visible .btn{filter:brightness(1.08)}
.empty{text-align:center;color:var(--mute);padding:48px 0}
footer{margin-top:28px;font-size:12px;color:var(--mute);text-align:center}
@media(min-width:480px){.t{font-size:14px}}
"""


def _money(v) -> str:
    return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _card(i: dict, now: float) -> str:
    e = html.escape
    badges = ""
    d = int(i.get("discount") or 0)
    if d >= 5:
        badges += f'<span class="b">-{d}%</span>'
    if now - i.get("ts", 0) < NEW_DAYS * 86400:
        badges += '<span class="b n">NOVO</span>'
    sales = int(i.get("sales") or 0)
    sold = f'<div class="s">⭐ {e(str(i.get("rating", "")))} · {sales:,} vendidos</div>'.replace(",", ".") if sales else ""
    price = f'<div class="p">{_money(i["price"])}</div>' if i.get("price") else ""
    return (
        f'<a class="c" href="{e(i["link"])}" target="_blank" rel="sponsored nofollow noopener">'
        f'<div class="im"><img src="{e(i["image"])}" alt="{e(i["name"][:80])}" loading="lazy" width="300" height="300">{badges}</div>'
        f'<div class="t">{e(i["name"])}</div>{price}{sold}<div class="btn">Ver na Shopee</div></a>'
    )


def render(items: list[dict]) -> None:
    now = time.time()
    shown = list(reversed(items[-MAX_ITEMS:]))
    body = ('<div class="grid">' + "".join(_card(i, now) for i in shown) + "</div>") if shown else (
        '<p class="empty">Em breve: achadinhos fresquinhos por aqui ✨</p>')
    ig = f'<a class="ig" href="https://instagram.com/{html.escape(HANDLE)}">@{html.escape(HANDLE)}</a>' if HANDLE else ""
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(
        '<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(BRAND)}</title>"
        f'<meta name="description" content="{html.escape(TAGLINE)}">'
        f'<meta property="og:title" content="{html.escape(BRAND)}"><meta property="og:description" content="{html.escape(TAGLINE)}">'
        f"<style>{CSS}</style><body><div class=w>"
        f'<header><div class="logo">🏠</div><h1>{html.escape(BRAND)}</h1><p class="tag">{html.escape(TAGLINE)}</p>{ig}</header>'
        f"<main>{body}</main>"
        "<footer>Como afiliado da Shopee, posso receber comissão pelas compras feitas pelos links, "
        "sem custo extra pra você. Preços e disponibilidade podem mudar.</footer>"
        "</div></body></html>"
    )
