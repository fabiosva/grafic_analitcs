# Painel Fundo BTC

Dashboard pessoal de monitoramento de "fundo" do Bitcoin. Nao e um bot de trading, e apenas visualizacao de indicadores on-chain e tecnicos. Projeto independente do CryptoBot AI.

## Arquitetura

```
GitHub Actions (cron diario, gratis)
  -> coleta indicadores on-chain + tecnicos
  -> calcula score de fundo (0-100)
  -> salva no Supabase

Streamlit Cloud (dashboard, gratis)
  -> le Supabase
  -> mostra velocimetro + cards + grafico historico
```

100% gratuito, sem custo de infra.

## Fontes de dados

- Preco: `https://api.coinbase.com/v2/prices/BTC-USD/spot`
- On-chain (MVRV Z-Score, NUPL, SOPR, Realized Price, Puell Multiple, RSI/MACD/SMA): [bitcoin-data.com](https://bitcoin-data.com)
- Fear & Greed Index: `https://api.alternative.me/fng/?limit=1`

Limitacao conhecida: o free tier do bitcoin-data.com cobre apenas ~4 anos de historico (desde 2022-08), sem paginacao por data. Nao cobre os fundos de 2015/2018 para backtest completo.

## Logica do score

`collector/collector.py` calcula o score com base em 4 condicoes obrigatorias de "fundo estrutural":

1. MVRV Z-Score < 0.3
2. Fear & Greed < 25
3. RSI diario < 35
4. Preco <= Realized Price x 1.05

Se as 4 estiverem ativas, a classificacao e "FUNDO ESTRUTURAL". Bonus de +10 pontos cada para: NUPL negativo, SOPR < 1, Puell Multiple < 0.5.

`score_final = (condicoes obrigatorias ativas / 4 x 70) + bonus`, capado em 100.

## Setup

1. Rode o schema em `supabase_schema.sql` no seu projeto Supabase (SQL Editor).
2. Configure `SUPABASE_URL` e `SUPABASE_KEY` (service key) em GitHub Secrets: Settings -> Secrets and variables -> Actions.
3. Rode o workflow manualmente uma vez: Actions -> "Coletor Diario BTC" -> Run workflow (para popular a tabela).
4. Deploy do dashboard no [Streamlit Cloud](https://share.streamlit.io) apontando para `dashboard/app.py`, com os mesmos secrets (`SUPABASE_URL`, `SUPABASE_KEY`) configurados em Settings -> Secrets do app.

## Estrutura

```
collector/
  collector.py         # coleta dados, calcula score, salva no Supabase
  requirements.txt
dashboard/
  app.py                # dashboard Streamlit
  requirements.txt
.github/workflows/
  collector.yml         # cron diario as 12h UTC
supabase_schema.sql      # schema da tabela bottom_indicators
```
