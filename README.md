# shopee_aff

Automated Shopee affiliate -> Instagram. Zero servers, zero cost.

- GitHub Actions cron (2x/day) picks best unposted product (commission x price, rating filter)
- Shopee Affiliate API -> short link; Instagram Graph API -> post image
- Link-in-bio = `site/index.html` on GitHub Pages
- State = `data/posted.json` committed by the bot

## Niche
Casa & cozinha, R$10-120, rating>=4.5, commission>=8%. Edit `KEYWORDS` in `main.py`; optional secret/env `SHOPEE_CAT_ID` to restrict by category.

## Setup
1. Repo secrets: `SHOPEE_APP_ID`, `SHOPEE_SECRET`, `IG_USER_ID`, `IG_ACCESS_TOKEN`
2. Settings > Pages > deploy from `main` /site (needs public repo on free plan)
3. Put Pages URL in Instagram bio
4. Local test: `cp .env.example .env; set -a; . ./.env; set +a; PYTHONPATH=src python -m shopee_aff.main`

## Instagram prereqs
Business/Creator account linked to a Facebook Page, Meta developer app, long-lived token (~60d, refresh needed).
