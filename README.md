# shopee_aff

Automated Shopee affiliate -> Instagram. Zero servers, zero cost.

- GitHub Actions cron (2x/day) picks best unposted product (commission x price, rating filter)
- Shopee Affiliate API -> short link; Instagram Graph API -> post image
- Link-in-bio = `docs/index.html` on GitHub Pages
- State = `data/posted.json` committed by the bot

## Niche
Casa & cozinha, R$10-120, rating>=4.5, commission>=8%. Edit `KEYWORDS` in `main.py`; optional secret/env `SHOPEE_CAT_ID` to restrict by category.

## Setup
1. Repo secrets: `SHOPEE_APP_ID`, `SHOPEE_SECRET`, `IG_USER_ID`, `IG_ACCESS_TOKEN`
2. Settings > Pages > deploy from `main` /docs (needs public repo on free plan)
3. Put Pages URL in Instagram bio
4. Local test: `cp .env.example .env; set -a; . ./.env; set +a; PYTHONPATH=src python -m shopee_aff.main`

## Instagram prereqs
Separate IG account from `TrveLeo/religious` (devotional, non-commercial). Uses Instagram Login API (`graph.instagram.com`), no Facebook Page.
1. New IG account -> switch to Professional (Creator/Business)
2. Meta app (existing one from `religious` or new): add account as Instagram Tester, accept invite in IG app
3. App dashboard > Instagram > API setup > generate token for the account -> `IG_ACCESS_TOKEN`, `IG_USER_ID`
4. Token ~60d: `shopee_aff.instagram.refresh_token()` renews it

## Sales per post
Each post gets its own Shopee `subId` (`ig<yymmddhh>x<itemId>`), saved in `data/posted.json`.
`PYTHONPATH=src python -m shopee_aff.report [days]` joins it with `conversionReport` -> commission per post.

## API notes (verified)
sortType: 1 relevance, 2 sales, 3 price desc, 4 price asc, 5 commission. `productCatId` is `Int`.
API returns intermittent `System Error 10000` -> `_call` retries with backoff.
