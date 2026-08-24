const config = require('./config');

/**
 * Avalia o risco estrutural de um ativo cripto (0 a 100)
 * Baseado em Razão FDV/MCap, Float Circulante, Liquidez e Idade
 */
function computeRisk(snapshot, extraData = {}) {
  const rules = config.riskRules;
  let riskScore = 0;
  const components = {};

  const marketCap = snapshot.market_cap || 0;
  const volume24h = snapshot.volume_24h || 0;
  const circulating = snapshot.circulating_supply || 0;
  const total = snapshot.total_supply || snapshot.max_supply || circulating;
  const price = snapshot.price_usd || 0;

  // 1. Razão FDV / Market Cap (Diluição de Tokens Bloqueados)
  let fdvRatio = 1.0;
  let fdvPenalty = 0;

  if (snapshot.fdv && marketCap > 0) {
    fdvRatio = snapshot.fdv / marketCap;
  } else if (total > 0 && circulating > 0) {
    fdvRatio = total / circulating;
  }

  if (fdvRatio < rules.fdvRatioThresholds.great) {
    fdvPenalty = 0;
  } else if (fdvRatio <= rules.fdvRatioThresholds.normal) {
    fdvPenalty = 10;
  } else if (fdvRatio <= rules.fdvRatioThresholds.warning) {
    fdvPenalty = 25;
  } else {
    fdvPenalty = rules.fdvRatioThresholds.critical; // > 10x
  }

  // Float Circulante Crítico (Menos de 25% das moedas no mercado = risco de despejo)
  let floatPct = 100;
  if (total > 0 && circulating > 0) {
    floatPct = (circulating / total) * 100;
    if (floatPct < 25 && fdvPenalty < 30) {
      fdvPenalty = Math.max(fdvPenalty, 30);
    }
  }

  riskScore += fdvPenalty;
  components.fdvRatio = parseFloat(fdvRatio.toFixed(2));
  components.floatPct = parseFloat(floatPct.toFixed(1));
  components.fdvPenalty = fdvPenalty;

  // 2. Liquidez / Giro de Volume (Volume 24h / Market Cap)
  let liquidityRatio = 0;
  let liquidityPenalty = 0;

  if (marketCap > 0) {
    liquidityRatio = volume24h / marketCap;
  }

  if (liquidityRatio < rules.lowLiquidityRatio) {
    liquidityPenalty = rules.lowLiquidityPenalty; // Giro < 2%
  } else if (liquidityRatio < 0.04) {
    liquidityPenalty = 15; // Giro < 4%
  } else if (liquidityRatio < 0.08) {
    liquidityPenalty = 5;
  } else {
    liquidityPenalty = 0;
  }

  // Volume absoluto muito baixo (< $150k)
  if (volume24h < 150000 && liquidityPenalty < 20) {
    liquidityPenalty = Math.max(liquidityPenalty, 20);
  }

  riskScore += liquidityPenalty;
  components.liquidityRatio = parseFloat(liquidityRatio.toFixed(4));
  components.liquidityPenalty = liquidityPenalty;

  // 3. Idade do Token
  let ageDays = extraData.ageDays != null ? extraData.ageDays : 180;
  let agePenalty = 0;

  if (ageDays < rules.tokenAgeYoungDays) {
    agePenalty = rules.tokenAgeYoungPenalty;
  } else if (ageDays < rules.tokenAgeMediumDays) {
    agePenalty = rules.tokenAgeMediumPenalty;
  } else {
    agePenalty = 0;
  }

  riskScore += agePenalty;
  components.ageDays = ageDays;
  components.agePenalty = agePenalty;

  // Normalização final (0 a 100)
  const finalRiskScore = Math.max(0, Math.min(100, riskScore));

  return {
    riskScore: finalRiskScore,
    components,
  };
}

module.exports = {
  computeRisk,
};
