# shopee_aff

Shopee affiliate products -> Instagram, plus original listing video preparation for Shopee Video.

- GitHub Actions cron (2x/day) picks best unposted product (commission x price, rating filter)
- Shopee Affiliate API -> short link; Instagram Graph API -> post image
- Link-in-bio = `docs/index.html` on GitHub Pages
- State = `data/posted.json` committed by the bot
- Videos = original product listing media, MP4 upload packages, affiliate links and a separate preparation queue

## Vídeos dos próprios anúncios

Esta etapa **prepara a fila e os arquivos**; não publica vídeos na Shopee nem no Instagram.
O envio será conectado depois de verificar os recursos disponíveis na conta. Nenhuma API pública de
publicação no Shopee Vídeo foi confirmada para esta integração.

O fluxo seleciona ofertas usando os filtros do projeto, identifica o anúncio por `shopId` + `itemId`,
procura o vídeo original em metadados públicos da página e baixa a mídia do CDN da Shopee.
Preserva o original e cria um MP4 H.264/AAC vertical de 1080×1920, com bordas para manter o produto
inteiro, até 60 segundos e capa JPG. Não cria vídeos a partir de fotos nem substitui o produto.

**Limitação verificada em 17/11/2026:** a API brasileira `productOfferV2` não expõe vídeos.
Páginas que carregam a mídia somente por JavaScript ou exigem login/verificação podem não fornecer
o vídeo ao resolvedor. Nesses casos, o item fica `blocked` com motivo; não é marcado como pronto.
É possível cadastrar a URL original do vídeo do anúncio, obtida do vendedor ou da própria página.
O cadastro é uma declaração de origem, não uma verificação independente de direitos de uso.
Confirme com o vendedor a autorização de reutilização; estar no anúncio não concede essa autorização.

### Preparar localmente

Requer Python 3.12 e FFmpeg com `ffprobe` (`sudo apt-get install ffmpeg` no Ubuntu).
Não há dependências Python externas. Carregue as credenciais de afiliado sem sobrescrever o `.env` existente:

```bash
set -a
. ./.env
set +a
export PYTHONPATH=src

python -m shopee_aff.videos prepare --limit 3 --scan-limit 15
python -m shopee_aff.videos status
python -m shopee_aff.videos verify
```

Para cadastrar um vídeo original quando a descoberta automática não conseguir encontrá-lo:

```bash
python -m shopee_aff.videos register-source \
  --product-url 'https://shopee.com.br/product/SHOP_ID/ITEM_ID' \
  --video-url 'https://down-br.vod.susercontent.com/CAMINHO_ORIGINAL.mp4' \
  --evidence-url 'https://FONTE_QUE_ASSOCIA_ANUNCIO_E_VIDEO' \
  --rights-reference 'Referência da autorização de reutilização do vendedor'

python -m shopee_aff.videos prepare --retry --limit 3
```

Substitua os valores de exemplo pelas URLs reais do **mesmo anúncio**. Links curtos não identificam
a origem do vídeo; use a URL completa do produto. A URL de mídia precisa ser HTTPS em um CDN aceito
da Shopee. `--evidence-url` documenta a associação entre anúncio e mídia; não comprova permissão.
Preencha `--rights-reference` somente quando houver uma autorização real; caso contrário, omita-o.
O resolvedor não usa cookies de conta nem contorna verificações da plataforma.

### Arquivos e fila

Cada produto pronto gera `artifacts/videos/sv-SHOP_ID-ITEM_ID/` contendo:

| Arquivo | Uso |
|---|---|
| `original.mp4` | Vídeo baixado do anúncio, sem alteração |
| `video.mp4` | Versão preparada para upload |
| `cover.jpg` | Capa extraída do próprio vídeo |
| `caption-shopee.txt` | Legenda com chamada para o produto vinculado |
| `caption-external.txt` | Legenda com nosso link de afiliado para canais externos |
| `affiliate-link.txt` | Link de afiliado com `subId` próprio do produto/vídeo |
| `publication.json` | Produto a vincular, origem da mídia, hashes e informações do arquivo |
| `LEIA-ME.txt` | Instruções de upload e vinculação |

Na Shopee, **vincule o produto à sacolinha antes de publicar**. Inserir nosso link de afiliado na
legenda não substitui essa vinculação para comissionamento nativo.
[Guia oficial](https://help.shopee.com.br/portal/10/article/165030).
A comissão informada na API de afiliados é usada para seleção; não é uma garantia da comissão no Shopee Vídeo.

`data/video_queue.json` guarda o histórico e `data/video_sources.json` associa fontes aos anúncios.
Os estados são `preparing`, `ready`, `blocked` e `published`.
`ready` significa arquivos preparados; `published` só é registrado após informar uma publicação real.
A fila é independente de `data/posted.json`, usado pelas imagens no Instagram.
O CLI usa bloqueio de escrita e substituição atômica do JSON. Falhas não geram sucesso fictício,
e produtos prontos/publicados não são preparados novamente, mesmo com `--retry`.

Para recriar arquivos de um produto pronto, por exemplo após o artifact expirar:

```bash
python -m shopee_aff.videos rebuild sv-SHOP_ID-ITEM_ID
```

O rebuild reutiliza o link de afiliado já salvo. Depois de publicar pela interface nativa, registre o ID ou URL real:

```bash
python -m shopee_aff.videos mark-published sv-SHOP_ID-ITEM_ID \
  --publication-id 'ID_OU_URL_REAL_DA_PUBLICACAO'
```

Os parâmetros globais `--queue`, `--sources` e `--output` devem vir antes do subcomando.
`prepare --products-file produtos.json` permite usar um array de produtos exportado da API em vez
de buscar ofertas; esses produtos são tratados como seleção prévia e não passam novamente pelos filtros.
Para consultar um anúncio específico na API ao vivo, use:

```bash
python -m shopee_aff.videos prepare \
  --product-url 'https://shopee.com.br/product/SHOP_ID/ITEM_ID' --limit 1 --require-ready
```

A seleção explícita por `--product-url` ignora os filtros de nicho somente para esse anúncio.
Os filtros da seleção automática continuam os mesmos. `--products-file` e `--product-url` são exclusivos.
Ainda são necessárias credenciais para consultar ofertas e gerar novos links de afiliado.

Para uma validação que exija ao menos um pacote real, use `prepare --require-ready`.
Sem um pacote, o comando retorna código 2 e mantém o diagnóstico na fila e em `preparation.json`.
`verify` confere os arquivos efetivos: identidade do produto, origem, checksums, perfil do MP4,
preservação do áudio, capa, legendas e link. O resultado fica em `verification.json`.
Os arquivos locais de uma validação não significam que houve publicação na Shopee.

### GitHub Actions

O workflow `.github/workflows/videos.yml` prepara pacotes e salva os arquivos em **Actions → execução → Artifacts**,
com retenção de 14 dias. Os binários ficam fora do Git; apenas os metadados da fila são commitados.
É necessário cadastrar `SHOPEE_APP_ID` e `SHOPEE_SECRET` nos secrets do repositório.
O preparo não usa credenciais do Instagram nem o `GH_PAT` da renovação de token.

Pode ser executado manualmente em **Actions → prepare-product-videos → Run workflow**.
O input opcional `product_url` seleciona um anúncio específico, com a mesma regra do CLI.
Execuções manuais exigem um pacote real por padrão (`require_ready=true`) e falham se a fonte
de vídeo estiver indisponível. Os artifacts e a fila de diagnóstico são preservados mesmo nessa falha.
O cron de preparo só executa se a variável do repositório `VIDEO_PREPARE_ENABLED` for `true`;
os horários são 09h e 18h na Bahia. Por padrão permanece desativado.
Os workflows de imagens e vídeos compartilham uma fila de execução para evitar gravações concorrentes no Git.
Alterações locais na fila/fontes precisam ser commitadas e enviadas antes de serem usadas no Actions.

### Produto de controle da validação real

O anúncio `1372532408/22293490123` (iPhone 13) é usado como controle explícito de preparo,
fora do nicho automático. A associação com o vídeo CDN registrado vem de um
[registro público do fornecedor Zen Studio](https://apify.com/zen-studio/shopee-product-scraper),
consultado em 18/11/2026. A API de afiliados confirma a identidade do anúncio; o registro do fornecedor
associa esses IDs ao arquivo `br-11110105-6kfko-m6fv71kcdug776.default.mp4`.
A associação não foi confirmada independentemente na galeria atual, que exige login/verificação.
Não há autorização do vendedor registrada. O controle valida o preparo dos arquivos e o link real;
não representa aprovação editorial nem publicação nativa na Shopee.
O cadastro preserva `evidence_url` e deixa `rights_reference` vazio.

### Verificação

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Os testes cobrem origem do vídeo, identidade do produto, retomada de falhas, deduplicação,
links, fila e processamento real com FFmpeg. A suite de integração é pulada se FFmpeg/ffprobe não
estiverem instalados; no CI ambos são obrigatórios. Nenhum teste publica conteúdo ou acessa contas reais.
A suite de ponta a ponta executa o CLI inteiro e FFmpeg com HTTP reproduzido a partir de fixtures;
isso é separado da validação em produção, que consulta anúncios e mídias reais.

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
