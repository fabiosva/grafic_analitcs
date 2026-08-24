const config = require('./config');

/**
 * Calcula Média Móvel Exponencial (EMA)
 */
function calculateEMA(prices, period) {
  if (!prices || prices.length < period) return null;
  
  const k = 2 / (period + 1);
  let ema = prices.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < prices.length; i++) {
    ema = prices[i] * k + ema * (1 - k);
  }
  return ema;
}

/**
 * Calcula RSI (14 períodos)
 */
function calculateRSI(prices, period = 14) {
  if (!prices || prices.length < period + 1) return null;

  let gains = 0;
  let losses = 0;
  for (let i = 1; i <= period; i++) {
    const change = prices[i] - prices[i - 1];
    if (change > 0) gains += change;
    else losses += Math.abs(change);
  }

  let avgGain = gains / period;
  let avgLoss = losses / period;

  for (let i = period + 1; i < prices.length; i++) {
    const change = prices[i] - prices[i - 1];
    if (change > 0) {
      avgGain = (avgGain * (period - 1) + change) / period;
      avgLoss = (avgLoss * (period - 1)) / period;
    } else {
      avgGain = (avgGain * (period - 1)) / period;
      avgLoss = (avgLoss * (period - 1) + Math.abs(change)) / period;
    }
  }

  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

/**
 * Analisa os indicadores técnicos e métricas de volume de uma moeda
 */
function computeIndicators(currentSnapshot, historySnapshots = []) {
  const price = currentSnapshot.price_usd;
  const vol24h = currentSnapshot.volume_24h;
  const p1h = currentSnapshot.price_change_1h || 0;
  const p24h = currentSnapshot.price_change_24h || 0;
  const p7d = currentSnapshot.price_change_7d || 0;
  const p30d = currentSnapshot.price_change_30d || 0;

  // 1. Obter série de preços históricos
  // Prioriza sparkline horária de 7 dias (168 pontos) da CoinGecko
  let prices = [];
  if (Array.isArray(currentSnapshot.sparkline_prices) && currentSnapshot.sparkline_prices.length >= 15) {
    prices = [...currentSnapshot.sparkline_prices];
    // Garante que o preço atual seja o último ponto
    if (prices[prices.length - 1] !== price) {
      prices.push(price);
    }
  } else if (historySnapshots.length > 0) {
    prices = historySnapshots.map(s => s.price_usd).filter(p => p > 0);
    prices.push(price);
  } else {
    prices = [price];
  }

  // 2. EMA 20 e EMA 50
  const ema20 = calculateEMA(prices, 20);
  const ema50 = calculateEMA(prices, 50);

  // 3. RSI 14
  const rsi = calculateRSI(prices, 14);

  // 4. Aceleração de Volume
  // Se não houver histórico de snapshots anteriores no banco, retorna null (N/A explícito)
  let volumeAccelVsPrev = null;
  let volumeAccelVs7d = null;

  if (historySnapshots.length > 0) {
    const prevVol = historySnapshots[historySnapshots.length - 1].volume_24h;
    if (prevVol && prevVol > 0) {
      volumeAccelVsPrev = vol24h / prevVol;
    }

    const histVols = historySnapshots.map(s => s.volume_24h).filter(v => v > 0).slice(-168);
    if (histVols.length >= 1) {
      const avg7d = histVols.reduce((a, b) => a + b, 0) / histVols.length;
      if (avg7d > 0) {
        volumeAccelVs7d = vol24h / avg7d;
      }
    }
  }

  // 5. Máxima de 7d/30d e Breakout
  let maxPrice = price;
  if (prices.length > 1) {
    maxPrice = Math.max(...prices);
  } else if (p30d < 0) {
    maxPrice = price / (1 + p30d / 100);
  }

  const isBreakout = (price >= maxPrice * 0.985);
  const isVolume2xAvg = (volumeAccelVs7d !== null && volumeAccelVs7d >= 2.0);
  const isEma20Above50 = (ema20 != null && ema50 != null) ? (ema20 > ema50) : null;
  const isPriceAboveEma20 = (ema20 != null) ? (price > ema20) : null;
  const isPriceAboveEma50 = (ema50 != null) ? (price > ema50) : null;
  const isMomentum7dPos = (p7d > 0);

  // 6. Breakout Score Adaptativo
  let earnedBreakout = 0;
  let maxPossibleBreakout = 0;
  const rules = config.breakoutRules;

  earnedBreakout += isBreakout ? rules.breakout30dHigh : 0;
  maxPossibleBreakout += rules.breakout30dHigh;

  if (volumeAccelVs7d !== null) {
    earnedBreakout += isVolume2xAvg ? rules.volumeOver2xAvg7d : 0;
    maxPossibleBreakout += rules.volumeOver2xAvg7d;
  }

  earnedBreakout += isMomentum7dPos ? rules.momentum7dPositive : 0;
  maxPossibleBreakout += rules.momentum7dPositive;

  if (isEma20Above50 !== null) {
    earnedBreakout += isEma20Above50 ? rules.ema20AboveEma50 : 0;
    maxPossibleBreakout += rules.ema20AboveEma50;
  }
  if (isPriceAboveEma20 !== null) {
    earnedBreakout += isPriceAboveEma20 ? rules.priceAboveEma20 : 0;
    maxPossibleBreakout += rules.priceAboveEma20;
  }
  if (isPriceAboveEma50 !== null) {
    earnedBreakout += isPriceAboveEma50 ? rules.priceAboveEma50 : 0;
    maxPossibleBreakout += rules.priceAboveEma50;
  }

  if (rsi !== null && rsi > 80) {
    earnedBreakout = Math.max(0, earnedBreakout + rules.rsiOverboughtPenalty);
  }

  const breakoutScore = maxPossibleBreakout > 0 
    ? Math.max(0, Math.min(100, (earnedBreakout / maxPossibleBreakout) * 100))
    : 50;

  const isExhaustionDivergence = (volumeAccelVs7d !== null && p24h > 4.0 && volumeAccelVs7d < 0.8);
  const isExtended = (p24h >= config.signals.extended24hThresholdPct);
  const isWarmedUp = (prices.length >= 20);

  return {
    price,
    ema20,
    ema50,
    rsi,
    volumeAccelVsPrev,
    volumeAccelVs7d,
    maxPrice,
    isBreakout,
    isVolume2xAvg,
    isEma20Above50,
    isPriceAboveEma20,
    isPriceAboveEma50,
    isMomentum7dPos,
    breakoutScore,
    isExhaustionDivergence,
    isExtended,
    isWarmedUp,
    historyLength: prices.length,
  };
}

module.exports = {
  calculateEMA,
  calculateRSI,
  computeIndicators,
};
