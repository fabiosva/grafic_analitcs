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

## Logica dos indices

`collector/collector.py` calcula o score com base em 4 condicoes obrigatorias de "fundo estrutural":

1. MVRV Z-Score < 0.3
2. Fear & Greed < 25
3. RSI diario < 35
4. Preco <= Realized Price x 1.05

Se as 4 estiverem ativas, a classificacao do coletor e "FUNDO ESTRUTURAL". O coletor tambem considera bonus de NUPL, SOPR, Puell Multiple, StochRSI, SMA 200, Reserve Risk e RHODL.

`score_final = (condicoes obrigatorias ativas / 4 x 70) + bonus`, capado em 100. Com menos de 3 condicoes obrigatorias disponiveis, o resultado e `Dados insuficientes` e o score fica nulo.

O dashboard usa um indice mais informativo para visualizacao: converte 15 indicadores em sinais graduais de 0 a 100 e calcula uma media ponderada. Alem dos dados coletados, deriva do historico o drawdown anual, retorno de 30 dias, Z-Score do preco em 90 dias e MACD normalizado. Ele exibe tambem a cobertura dos dados e oculta o indice quando menos de 45% dos sinais estao disponiveis. Esse indice mede confluencia heuristica; nao representa probabilidade de fundo.

Para evitar confundir contexto com timing, a interface separa tres leituras: estrutura lenta (on-chain e valuation), confirmacao atual (momentum e sentimento) e janela temporal (halving/topo). Indicadores estruturais podem permanecer favoraveis por meses; o painel so chama o dia atual de candidato a fundo quando estrutura e confirmacao atual superam 70 pontos. A janela temporal nunca bloqueia uma confirmacao que aconteca antes ou depois.

## Setup

### Acesso local ao painel

```bash
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

Abra `http://localhost:8501`. Sem credenciais, o painel usa `collector/data/history.json` gerado pelo backfill (ou `latest.json` como fallback); com `SUPABASE_URL` e `SUPABASE_KEY`, carrega todo o historico remoto.

O painel inclui um cenario de repeticao dos ultimos 1.458 dias, o Pi Cycle Top (SMA 111 dias contra 2x SMA 350 dias), o Investor Tool (SMA de 730 dias e seu multiplo x5) e um corredor Power Law recalculado por regressao log-log. A media de 2 anos e a posicao no Power Law entram na leitura estrutural de fundo; o Pi Cycle e um alerta de topo e nao entra na nota de fundo.

O relogio 1064/365 aparece como contexto temporal: cerca de 1.064 dias do fundo ao topo e 365 dias do topo ao fundo seguinte. Ele nao recebe peso adicional no score para evitar duplicar a mesma informacao de calendario ja usada pela janela pos-topo.

### Deploy

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
