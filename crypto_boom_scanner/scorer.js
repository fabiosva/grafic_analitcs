const config = require('./config');
const indicators = require('./indicators');
const risk = require('./risk');

/**
 * Normaliza variações percentuais de preço para escala 0 a 100
 */
function normalizePct(pct, minRange = -20, maxRange = 50) {
  if (pct == null || isNaN(pct)) return 50;
  const clamped = Math.max(minRange, Math.min(maxRange, pct));
  return ((clamped - minRange) / (maxRange - minRange)) * 100;
}

/**
 * Normaliza aceleração de volume para escala 0 a 100
 */
function normalizeVolumeAccel(ratio) {
  if (ratio == null || isNaN(ratio)) return 50;
  if (ratio <= 0.5) return 20;
  if (ratio <= 1.0) return 20 + ((ratio - 0.5) / 0.5) * 30;
  if (ratio <= 2.0) return 50 + ((ratio - 1.0) / 1.0) * 30;
  if (ratio <= 3.5) return 80 + ((ratio - 2.0) / 1.5) * 20;
  return 100;
}

/**
 * Normaliza mudança de ranking com amortecimento de ruído para moedas menores
 */
function computeDampedRankScore(currentRank, prevRank) {
  if (!currentRank || !prevRank) return 50;

  const deltaRank = prevRank - currentRank;
  if (Math.abs(deltaRank) < 3) return 50;

  const rankDampener = currentRank > 200 ? 0.5 : 1.0;
  const magnitude = Math.sqrt(Math.abs(deltaRank)) * 8 * rankDampener;
  
  if (deltaRank > 0) {
    return Math.min(100, 50 + magnitude);
  } else {
    return Math.max(0, 50 - magnitude);
  }
}

/**
 * Calcula o Score completo de uma moeda
 */
function calculateScore(currentSnapshot, historySnapshots = [], previousScores = [], extraMeta = {}) {
  // 1. Indicadores Técnicos
  const tech = indicators.computeIndicators(currentSnapshot, historySnapshots);

  // 2. Risco Estrutural
  const riskResult = risk.computeRisk(currentSnapshot, extraMeta);
  const riskScore = riskResult.riskScore;

  // 3. Componente 1: Momentum de Preço (0 a 100)
  const p1h = currentSnapshot.price_change_1h || 0;
  const p24h = currentSnapshot.price_change_24h || 0;
  const p7d = currentSnapshot.price_change_7d || 0;
  const p30d = currentSnapshot.price_change_30d || 0;

  const score1h = normalizePct(p1h, -5, 10);
  const score24h = normalizePct(p24h, -15, 30);
  const score7d = normalizePct(p7d, -25, 60);
  const score30d = normalizePct(p30d, -40, 100);

  let rawMomentum = (score1h * 0.10) + (score24h * 0.30) + (score7d * 0.40) + (score30d * 0.20);
  if (tech.isExhaustionDivergence) {
    rawMomentum = Math.max(0, rawMomentum - 20);
  }
  const momentumScore = Math.max(0, Math.min(100, rawMomentum));

  // 4. Componente 2: Volume Acceleration (0 a 100)
  const accelPrevScore = normalizeVolumeAccel(tech.volumeAccelVsPrev);
  const accel7dScore = normalizeVolumeAccel(tech.volumeAccelVs7d);
  const volumeAccelScore = (accelPrevScore * 0.5) + (accel7dScore * 0.5);

  // 5. Componente 3: Breakout Score
  const breakoutScore = tech.breakoutScore;

  // 6. Componente 4: Rank Velocity
  let rankVelocityScore = 50;
  if (historySnapshots.length > 0) {
    const prevRank = historySnapshots[historySnapshots.length - 1].market_cap_rank;
    const currRank = currentSnapshot.market_cap_rank;
    rankVelocityScore = computeDampedRankScore(currRank, prevRank);
  }

  // 7. Opportunity Score Composto
  const weights = config.opportunityWeights;
  const opportunityScore = (momentumScore * weights.momentumWeight) +
                           (volumeAccelScore * weights.volumeAccelWeight) +
                           (breakoutScore * weights.breakoutWeight) +
                           (rankVelocityScore * weights.rankVelocityWeight);

  const roundedOpportunity = parseFloat(Math.max(0, Math.min(100, opportunityScore)).toFixed(1));

  // 8. Final Score = Opportunity - (Risk * RISK_PENALTY_WEIGHT)
  const penaltyFactor = config.riskRules.riskPenaltyFactor || 0.50;
  const riskPenalty = riskScore * penaltyFactor;
  let finalScore = roundedOpportunity - riskPenalty;
  finalScore = parseFloat(Math.max(0, Math.min(100, finalScore)).toFixed(1));

  // 9. Deltas Históricos de Score
  let delta6h = 0;
  let delta12h = 0;
  let delta24h = 0;

  if (previousScores && previousScores.length > 0) {
    const nowMs = new Date(currentSnapshot.snapshot_time || Date.now()).getTime();

    const score6hItem = previousScores.find(s => {
      const diffHours = (nowMs - new Date(s.created_at).getTime()) / (1000 * 60 * 60);
      return diffHours >= 5.5 && diffHours <= 7.5;
    });
    if (score6hItem) delta6h = parseFloat((finalScore - score6hItem.final_score).toFixed(1));

    const score12hItem = previousScores.find(s => {
      const diffHours = (nowMs - new Date(s.created_at).getTime()) / (1000 * 60 * 60);
      return diffHours >= 11.0 && diffHours <= 13.5;
    });
    if (score12hItem) delta12h = parseFloat((finalScore - score12hItem.final_score).toFixed(1));

    const score24hItem = previousScores.find(s => {
      const diffHours = (nowMs - new Date(s.created_at).getTime()) / (1000 * 60 * 60);
      return diffHours >= 22.0 && diffHours <= 26.0;
    });
    if (score24hItem) delta24h = parseFloat((finalScore - score24hItem.final_score).toFixed(1));
  }

  // 10. Classificação de Sinais (Ordem de especificidade)
  let signalCategory = 'NEUTRAL';
  const mcap = currentSnapshot.market_cap || 0;

  if (tech.isExtended) {
    signalCategory = 'EXTENDED';
  } else if (riskScore >= config.signals.highRiskThreshold && roundedOpportunity >= 60) {
    signalCategory = 'HIGH_RISK';
  } else if (
    tech.volumeAccelVs7d >= config.signals.accumulation.minVolumeAccel7d &&
    p24h >= config.signals.accumulation.minPriceChange24h &&
    p24h <= config.signals.accumulation.maxPriceChange24h
  ) {
    // Acumulação: Volume forte com preço calmo/lateral
    signalCategory = 'ACCUMULATION';
  } else if (
    roundedOpportunity >= config.signals.boomWatch.minOpportunity &&
    breakoutScore >= config.signals.boomWatch.minBreakout &&
    riskScore <= config.signals.boomWatch.maxRisk &&
    (mcap <= config.signals.boomWatch.maxMarketCapUsd || mcap === 0)
  ) {
    signalCategory = 'BOOM_WATCH';
  } else if (
    roundedOpportunity >= config.signals.momentum.minOpportunity &&
    p24h >= config.signals.momentum.minPriceChange24h &&
    (tech.rsi === null || tech.rsi <= config.signals.momentum.maxRsi)
  ) {
    signalCategory = 'MOMENTUM';
  }

  const components = {
    priceUsd: currentSnapshot.price_usd,
    marketCap: mcap,
    volume24h: currentSnapshot.volume_24h,
    priceChange1h: p1h,
    priceChange24h: p24h,
    priceChange7d: p7d,
    priceChange30d: p30d,
    rsi: tech.rsi !== null ? parseFloat(tech.rsi.toFixed(1)) : null,
    ema20: tech.ema20 !== null ? parseFloat(tech.ema20.toFixed(4)) : null,
    ema50: tech.ema50 !== null ? parseFloat(tech.ema50.toFixed(4)) : null,
    volumeAccelVs7d: parseFloat(tech.volumeAccelVs7d.toFixed(2)),
    volumeAccelVsPrev: parseFloat(tech.volumeAccelVsPrev.toFixed(2)),
    isBreakout30d: tech.isBreakout30d,
    isWarmedUp: tech.isWarmedUp,
    historyLength: tech.historyLength,
    momentumSubScore: parseFloat(momentumScore.toFixed(1)),
    volumeAccelSubScore: parseFloat(volumeAccelScore.toFixed(1)),
    breakoutSubScore: parseFloat(breakoutScore.toFixed(1)),
    rankVelocitySubScore: parseFloat(rankVelocityScore.toFixed(1)),
    riskPenaltyApplied: parseFloat(riskPenalty.toFixed(1)),
    riskComponents: riskResult.components,
  };

  return {
    coin_id: currentSnapshot.coin_id,
    opportunity_score: roundedOpportunity,
    risk_score: riskScore,
    final_score: finalScore,
    signal_category: signalCategory,
    delta_6h: delta6h,
    delta_12h: delta12h,
    delta_24h: delta24h,
    components,
    created_at: currentSnapshot.snapshot_time || new Date().toISOString(),
  };
}

module.exports = {
  calculateScore,
  computeDampedRankScore,
  normalizePct,
  normalizeVolumeAccel,
};
