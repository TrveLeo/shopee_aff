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
Reuses the Devocional Diario account + Meta app from `TrveLeo/religious` (Instagram Login API, `graph.instagram.com`, no FB Page).
The `religious` workflows are **disabled** (re-enable: `gh workflow enable <file> -R TrveLeo/religious`). Its Cloudflare webhook ("amem" replies) is separate and still deployed.
- Copy `IG_ACCESS_TOKEN` + `IG_USER_ID` from `religious` into `.env` and this repo's Actions secrets (values are not readable via API)
- Token ~60d: `shopee_aff.instagram.refresh_token()` renews it. Do not run two repos on the same token.
- Bio link -> https://trveleo.github.io/shopee_aff/ (manual, IG API cannot edit bio)

## Sales per post
Each post gets its own Shopee `subId` (`ig<yymmddhh>x<itemId>`), saved in `data/posted.json`.
`PYTHONPATH=src python -m shopee_aff.report [days]` joins it with `conversionReport` -> commission per post.

## API notes (verified)
sortType: 1 relevance, 2 sales, 3 price desc, 4 price asc, 5 commission. `productCatId` is `Int`.
API returns intermittent `System Error 10000` -> `_call` retries with backoff.

## Token auto-refresh
`.github/workflows/refresh-token.yml` runs on the 1st and 15th, renews `IG_ACCESS_TOKEN` and rewrites the secret.
Needs secret `GH_PAT`: fine-grained PAT, only this repo, permission "Secrets: Read and write". If the workflow fails GitHub emails you.
Only works while the token is still valid - if it ever expires, generate a new one in the Meta dashboard.
