const config = require('./config');

/**
 * Avalia o risco estrutural de um ativo cripto (0 a 100)
 * Quanto maior o score, maior o risco de armadilha / despejo / desidratação de liquidez
 * @param {Object} snapshot - Snapshot atual do ativo
 * @param {Object} extraData - Dados adicionais de metadados (idade, holders)
 */
function computeRisk(snapshot, extraData = {}) {
  const rules = config.riskRules;
  let riskScore = 0;
  const components = {};

  const marketCap = snapshot.market_cap || 0;
  const fdv = snapshot.fdv || marketCap;
  const volume24h = snapshot.volume_24h || 0;

  // 1. Razão FDV / Market Cap
  let fdvRatio = 1.0;
  let fdvPenalty = 0;

  if (marketCap > 0 && fdv > 0) {
    fdvRatio = fdv / marketCap;
  }

  if (fdvRatio < rules.fdvRatioThresholds.great) {
    fdvPenalty = 0; // Baixo risco de unlock
  } else if (fdvRatio <= rules.fdvRatioThresholds.normal) {
    fdvPenalty = 10;
  } else if (fdvRatio <= rules.fdvRatioThresholds.warning) {
    fdvPenalty = 25;
  } else {
    fdvPenalty = rules.fdvRatioThresholds.critical; // > 10x MCap em tokens bloqueados
  }

  riskScore += fdvPenalty;
  components.fdvRatio = parseFloat(fdvRatio.toFixed(2));
  components.fdvPenalty = fdvPenalty;

  // 2. Liquidez / Giro de Volume (Volume 24h / Market Cap)
  let liquidityRatio = 0;
  let liquidityPenalty = 0;

  if (marketCap > 0) {
    liquidityRatio = volume24h / marketCap;
  }

  if (liquidityRatio < rules.lowLiquidityRatio) {
    liquidityPenalty = rules.lowLiquidityPenalty; // Menos de 2% de volume relativo
  } else if (liquidityRatio < 0.05) {
    liquidityPenalty = 10;
  } else {
    liquidityPenalty = 0;
  }

  riskScore += liquidityPenalty;
  components.liquidityRatio = parseFloat(liquidityRatio.toFixed(4));
  components.liquidityPenalty = liquidityPenalty;

  // 3. Idade do Token (Token Age)
  let ageDays = extraData.ageDays != null ? extraData.ageDays : 180; // default safe se não fornecido
  let agePenalty = 0;

  if (ageDays < rules.tokenAgeYoungDays) {
    agePenalty = rules.tokenAgeYoungPenalty; // < 30 dias
  } else if (ageDays < rules.tokenAgeMediumDays) {
    agePenalty = rules.tokenAgeMediumPenalty; // 30 a 90 dias
  } else {
    agePenalty = 0;
  }

  riskScore += agePenalty;
  components.ageDays = ageDays;
  components.agePenalty = agePenalty;

  // 4. Concentração de Holders (reservado para Covalent/Moralis futuro)
  components.holderConcentration = extraData.holderConcentration || null;

  // Normalização final de risco (0 a 100)
  const finalRiskScore = Math.max(0, Math.min(100, riskScore));

  return {
    riskScore: finalRiskScore,
    components,
  };
}

module.exports = {
  computeRisk,
};
