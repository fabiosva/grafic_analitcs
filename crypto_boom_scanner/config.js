require('dotenv').config();

module.exports = {
  // Configurações do Coletor
  collector: {
    apiUrl: process.env.COINGECKO_API_URL || 'https://api.coingecko.com/api/v3',
    apiKey: process.env.COINGECKO_API_KEY || '', // Opcional (Pro / Demo API Key)
    totalCoins: parseInt(process.env.TOTAL_COINS_TO_TRACK || '350', 10), // Top 300-500
    perPage: 250,
    requestDelayMs: parseInt(process.env.COINGECKO_RATE_LIMIT_DELAY_MS || '2500', 10), // Free tier ~30 req/min
    snapshotIntervalMinutes: parseInt(process.env.SNAPSHOT_INTERVAL_MINUTES || '60', 10),
  },

  // Filtros Básicos de Exclusão
  filters: {
    minMarketCapUsd: parseFloat(process.env.MIN_MARKET_CAP_USD || '1000000'), // $1M
    minVolume24hUsd: parseFloat(process.env.MIN_VOLUME_24H_USD || '50000'),   // $50k
    excludedSymbols: [
      'usdt', 'usdc', 'dai', 'fdusd', 'usde', 'tusd', 'pyusd', 'usdd', 
      'usdp', 'busd', 'frax', 'lusd', 'gusd', 'crvusd', 'gho', 'wbtc', 
      'weth', 'steth', 'wsteth', 'reth', 'cbeth', 'weeth', 'ezeth'
    ],
  },

  // Pesos do Opportunity Score (Total = 100)
  opportunityWeights: {
    momentumWeight: 0.30,        // Momentum de preço (1h, 24h, 7d, 30d)
    volumeAccelWeight: 0.30,     // Aceleração de volume (vs 24h anterior e média 7d)
    breakoutWeight: 0.30,        // Sinais de breakout técnico (métrica composta)
    rankVelocityWeight: 0.10,    // Subida no ranking de market cap com amortecimento
  },

  // Regras de Breakout
  breakoutRules: {
    breakout30dHigh: 20,         // Rompe máxima de 30 dias
    volumeOver2xAvg7d: 15,       // Volume > 2x média 7d
    ema20AboveEma50: 15,         // EMA20 > EMA50 (Golden Cross momentum)
    priceAboveEma20: 10,         // Preço > EMA20
    priceAboveEma50: 10,         // Preço > EMA50
    momentum7dPositive: 10,      // Preço 7d positivo
    rsiOverboughtPenalty: -10,   // Penalidade se RSI > 80
  },

  // Regras e Pesos de Risco (Risk Score 0 - 100)
  riskRules: {
    tokenAgeYoungDays: 30,       // Menos de 30 dias = Risco Alto
    tokenAgeYoungPenalty: 35,
    tokenAgeMediumDays: 90,      // 30 a 90 dias = Risco Moderado
    tokenAgeMediumPenalty: 15,
    fdvRatioThresholds: {
      great: 1.5,                // < 1.5 -> 0 risco
      normal: 3.0,               // 1.5 - 3.0 -> 10 risco
      warning: 10.0,             // 3.0 - 10.0 -> 25 risco
      critical: 40,              // > 10.0 -> 40 risco
    },
    lowLiquidityRatio: 0.02,     // Volume24h / MarketCap < 2% -> 25 risco
    lowLiquidityPenalty: 25,
    
    // RISK_PENALTY_WEIGHT: Fator de desconto do risco no Score Final
    // Valor inicial calibrado: 0.50 (50%). Faixa recomendada: [0.30, 0.70]
    // Exemplo: Opportunity 80, Risco 60 -> Final Score = 80 - (60 * 0.5) = 50 pts
    riskPenaltyFactor: parseFloat(process.env.RISK_PENALTY_FACTOR || '0.50'),
  },

  // Thresholds de Classificação de Sinais
  signals: {
    extended24hThresholdPct: parseFloat(process.env.EXTENDED_THRESHOLD_PCT || '80.0'), // > +80% 24h = EXTENDED
    boomWatch: {
      minOpportunity: 70,
      minBreakout: 18,
      maxRisk: 40,
      maxMarketCapUsd: 1000000000, // < $1B (teto para potencial de Boom explosivo)
    },
    momentum: {
      minOpportunity: 65,
      minPriceChange24h: 5.0,
      maxRsi: 78,
    },
    accumulation: {
      minVolumeAccel7d: 1.8,      // Volume > 1.8x média
      minPriceChange24h: -3.0,    // Preço lateralizado
      maxPriceChange24h: 6.0,
    },
    highRiskThreshold: 60,        // Risk Score >= 60
  },

  // Configurações de Alertas (Telegram)
  alerts: {
    telegramBotToken: process.env.TELEGRAM_BOT_TOKEN || '',
    telegramChatId: process.env.TELEGRAM_CHAT_ID || '',
    alertThresholdScore: parseFloat(process.env.ALERT_THRESHOLD_SCORE || '80.0'),
    cooldownHours: parseInt(process.env.ALERT_COOLDOWN_HOURS || '8', 10),
  },

  // Banco de Dados / Supabase
  supabase: {
    url: process.env.SUPABASE_URL || '',
    key: process.env.SUPABASE_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY || '',
    dbUrl: process.env.DATABASE_URL || '',
  },

  // Servidor Web Dashboard
  server: {
    port: parseInt(process.env.PORT || '3000', 10),
    corsOrigin: process.env.CORS_ORIGIN || '*',
  }
};
