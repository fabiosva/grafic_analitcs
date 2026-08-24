# 🚀 Crypto Boom Scanner (v2)

Sistema de alta performance para monitoramento de criptomoedas (Top 300–500 por Market Cap / Volume via CoinGecko), cálculo estatístico de confluência de **Momentum, Volume, Breakout Técnico e Risco**, alertas automatizados no Telegram e motor de validação por **Backtesting histórico**.

---

## 🏛️ 1. Arquitetura do Sistema

```
                      CoinGecko API (Throttled Free/Pro Tier)
                                         │
                                         ▼
                               ┌───────────────────┐
                               │   collector.js    │ (Top 300-500, paginação, filtros)
                               └─────────┬─────────┘
                                         │
                                         ▼
                             ┌───────────────────────┐
                             │  Supabase (Postgres)  │
                             │ (coins, coin_snapshots│
                             └───────────┬───────────┘
                                         │
                 ┌───────────────────────┴───────────────────────┐
                 ▼                                               ▼
     ┌───────────────────────┐                       ┌───────────────────────┐
     │     indicators.js     │                       │        risk.js        │
     │ (EMA20/50, RSI,       │                       │ (FDV/MCap, Token Age, │
     │  Vol Accel, Breakout) │                       │  Liquidez, Risco)     │
     └───────────┬───────────┘                       └───────────┬───────────┘
                 │                                               │
                 └───────────────────────┬───────────────────────┘
                                         ▼
                             ┌───────────────────────┐
                             │       scorer.js       │
                             │ Opportunity & Risk    │
                             │ Delta 6h/12h/24h      │
                             │ Classificação Sinais  │
                             └───────────┬───────────┘
                                         │
                ┌────────────────────────┼────────────────────────┐
                ▼                        ▼                        ▼
    ┌───────────────────────┐┌───────────────────────┐┌───────────────────────┐
    │      alerts.js        ││      backtest.js      ││     dashboard.js      │
    │ (Telegram Webhook,    ││ (Win rate, retorno    ││ (Node.js / Express    │
    │  Anti-spam cooldown)  ││  7d/14d/30d pós-sinal)││  Dashboard Unificado) │
    └───────────────────────┘└───────────────────────┘└───────────────────────┘
                                         │
                                         ▼
                             ┌───────────────────────┐
                             │     scheduler.js      │ (Orquestrador / Cron / PM2)
                             └───────────────────────┘
```

---

## 🧮 2. Explicação Detalhada de Cada Peso e Fórmula do Score

O sistema avalia cada ativo através de **dois eixos independentes**:
1. **Opportunity Score (0 a 100)**: Mede o potencial e a aceleração de alta.
2. **Risk Score (0 a 100)**: Mede armadilhas estruturais, diluição e baixa liquidez.

### 2.1. Opportunity Score (Pesos Configuráveis em `config.js`)

| Componente | Peso Default | Descrição e Lógica |
| :--- | :---: | :--- |
| **Momentum Composto** | `30%` (0.30) | Combina a variação de preço em 1h (10%), 24h (30%), 7d (40%) e 30d (20%). Penaliza em `-20 pts` caso haja **divergência de exaustão** (preço subindo com volume caindo). |
| **Volume Acceleration** | `30%` (0.30) | Avalia a injeção de volume recente: 50% baseado em `volume_24h / volume_24h_anterior` e 50% baseado em `volume_24h / media_volume_7d`. |
| **Breakout Score** | `30%` (0.30) | Mede rompimentos estruturais e confluência técnica (detalhado abaixo). |
| **Rank Velocity** | `10%` (0.10) | Bonifica moedas que estão ganhando posições no ranking de Market Cap. Possui **filtro de ruído** (ignora oscilações < 3 posições) e amortecimento para moedas além do rank 200. |

#### Subcomponentes do Breakout Score:
- `+20 pts`: Preço rompe a máxima dos últimos 30 dias (`price_usd >= max_30d_price`).
- `+15 pts`: Volume atual é mais que o dobro da média de 7 dias (`volume_24h >= 2x avg_7d`).
- `+15 pts`: EMA 20 > EMA 50 (Golden Cross de momentum).
- `+10 pts`: Preço acima da EMA 20.
- `+10 pts`: Preço acima da EMA 50.
- `+10 pts`: Variação de 7 dias positiva (`price_change_7d > 0`).
- `-10 pts`: Penalidade se `RSI > 80` (condição extrema de sobrecompra).
> **Tratamento de Warm-up**: Se o histórico de snapshots ainda for curto (< 50 horas de coleta), as condições de EMA e RSI ficam nulas e o Breakout Score se auto-calibra proporcionalmente apenas sobre as regras ativas sem inventar dados.

---

### 2.2. Risk Score (0 a 100)

| Fator de Risco | Pontuação | Critério |
| :--- | :---: | :--- |
| **Idade do Token (Token Age)** | `0 a 35 pts` | `< 30 dias` = 35 pts de risco (sem histórico). `30 a 90 dias` = 15 pts. `> 90 dias` = 0 pts. |
| **Razão FDV / Market Cap** | `0 a 40 pts` | `< 1.5x` = 0 pts (ótimo). `1.5x a 3.0x` = 10 pts. `3.0x a 10.0x` = 25 pts. `> 10.0x` = 40 pts (risco crítico de despejo por unlock futuro). |
| **Liquidez / Giro de Volume** | `0 a 25 pts` | `volume_24h / market_cap < 2%` = 25 pts de risco de iliquidez e derrapagem (slippage). |

---

### 2.3. Final Score & Fator de Penalidade de Risco (`RISK_PENALTY_WEIGHT`)

$$\text{Final Score} = \max(0, \min(100, \text{Opportunity Score} - (\text{Risk Score} \times \text{RISK\_PENALTY\_FACTOR})))$$

- **Valor Padrão**: `RISK_PENALTY_FACTOR = 0.50` (50%). Faixa recomendada: `[0.30, 0.70]`.
- **Por que 0.50?**:
  - Uma moeda com **Opportunity 85** e **Risco 20 (baixo)** fica com `85 - (20 * 0.5) = 75` (Sinal forte mantido).
  - Uma moeda com **Opportunity 85** e **Risco 80 (altíssimo)** é reduzida para `85 - (80 * 0.5) = 45` (Eliminada do topo do ranking, evitando armadilhas).

---

### 2.4. Categorias de Sinal Automáticas

- 🚀 **BOOM WATCH**: Opportunity $\ge 70$, Breakout $\ge 18$, Market Cap $< \$1\text{B}$, Risk $\le 40$.
- 🔥 **MOMENTUM**: Opportunity $\ge 65$, Variação 24h $\ge +5\%$, RSI $\le 78$.
- 🐋 **ACCUMULATION**: Volume 24h / Média 7d $\ge 1.8\text{x}$, Preço 24h lateralizado (entre $-3\%$ e $+6\%$).
- ⚠️ **EXTENDED**: Subida nas últimas 24h $\ge +80\%$ (alerta contra compras tardias no topo).
- ⚠️ **HIGH RISK**: Opportunity $\ge 60$ mas Risk Score $\ge 60$.

---

## 📊 3. Motor de Backtesting e Validação

O motor estatístico (`backtest.js`) avalia o que aconteceu após o ativo atingir faixas de score ($\ge 70, \ge 75, \ge 80, \ge 85$):
- **Win Rate 7d, 14d, 30d**: Porcentagem de ocorrências com retorno positivo.
- **Retorno Médio e Mediana**: Média ponderada de valorização nos horizontes temporais.
- **Max Gain / Max Drawdown**: Maior pico de ganho e pior queda registrada no período.

### Gatilhos de Execução do Backtest:
1. **Automático Diário**: Executado à meia-noite pelo `scheduler.js` via cron (`0 0 * * *`).
2. **Sob Demanda no Dashboard**: Botão "Recalcular Backtest" na aba de Backtest.
3. **Via Linha de Comando**: `npm run backtest`.

---

## 🚀 4. Instalação e Execução Local

### Pré-requisitos
- Node.js v18+ (recomendado Node 20 ou superior)
- Conta no [Supabase](https://supabase.com) (gratuito)

### Passo a Passo:

1. **Instalar as dependências**:
   ```bash
   cd crypto_boom_scanner
   npm install
   ```

2. **Configurar o Banco de Dados no Supabase**:
   - Abra o seu projeto no Supabase -> **SQL Editor**.
   - Copie e execute o script contido em `schema.sql`.

3. **Configurar as Variáveis de Ambiente**:
   - Copie o template: `cp .env.example .env`
   - Preencha com sua `SUPABASE_URL` e `SUPABASE_KEY` (service_role).
   - Opcionalmente, adicione o `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` para alertas.

4. **Rodar os Testes Automatizados**:
   ```bash
   npm test
   ```

5. **Executar a Coleta Manual / Teste Imediato**:
   ```bash
   npm run collect
   ```

6. **Iniciar o Dashboard Web Unificado**:
   ```bash
   npm run dashboard
   ```
   Acesse no navegador: `http://localhost:3000`

---

## 🛡️ 5. Gerenciamento em Produção com PM2

Para manter o coletor agendado e o dashboard rodando 24/7 com auto-restart em caso de falhas:

1. **Instalar o PM2 globalmente**:
   ```bash
   npm install -g pm2
   ```

2. **Iniciar os Processos via Ecosystem**:
   ```bash
   pm2 start ecosystem.config.js
   ```

3. **Comandos Úteis do PM2**:
   ```bash
   pm2 status          # Visualizar status do scheduler e dashboard
   pm2 logs            # Ver logs em tempo real
   pm2 restart all     # Reiniciar todos os processos
   pm2 stop all        # Parar os processos
   ```
