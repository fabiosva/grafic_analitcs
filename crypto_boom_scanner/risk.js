const config = require('./config');

/**
 * Avalia o risco estrutural de um ativo cripto (0 a 100)
 * Adendo v3: Inclui Idade Estrutural e Dead Weight Risk (Pressão de Holders Antigos Presos)
 */
function computeRisk(snapshot, extraData = {}) {
  const rules = config.riskRules;
  let riskScore = 0;
  const components = {};

  const marketCap = snapshot.market_cap || 0;
  const volume24h = snapshot.volume_24h || 0;
  const circulating = snapshot.circulating_supply || 0;
  const total = snapshot.total_supply || snapshot.max_supply || circulating;
  const athChangePct = snapshot.ath_change_percentage != null ? snapshot.ath_change_percentage : -50;

  // 1. Razão FDV / Market Cap & Float Circulante
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

  // 2. Liquidez / Giro de Volume
  let liquidityRatio = 0;
  let liquidityPenalty = 0;

  if (marketCap > 0) {
    liquidityRatio = volume24h / marketCap;
  }

  if (liquidityRatio < rules.lowLiquidityRatio) {
    liquidityPenalty = rules.lowLiquidityPenalty; // < 2%
  } else if (liquidityRatio < 0.04) {
    liquidityPenalty = 15;
  } else if (liquidityRatio < 0.08) {
    liquidityPenalty = 5;
  } else {
    liquidityPenalty = 0;
  }

  if (volume24h < 150000 && liquidityPenalty < 20) {
    liquidityPenalty = Math.max(liquidityPenalty, 20);
  }

  riskScore += liquidityPenalty;
  components.liquidityRatio = parseFloat(liquidityRatio.toFixed(4));
  components.liquidityPenalty = liquidityPenalty;

  // 3. Idade Estrutural do Token (Adendo v3)
  const ageDays = extraData.ageDays != null ? extraData.ageDays : 60;
  let agePenalty = 0;
  let ageCategory = 'DISCOVERY'; // 'NEW', 'DISCOVERY', 'MATURING', 'VETERAN'

  if (ageDays < 30) {
    ageCategory = 'NEW';
    agePenalty = 25; // Risco de rug/falta de histórico
  } else if (ageDays <= 180) {
    ageCategory = 'DISCOVERY';
    agePenalty = 0; // Fase de descoberta (maior valorização orgânica)
  } else if (ageDays <= 730) {
    ageCategory = 'MATURING';
    agePenalty = 10; // Holders começando a acumular lucro
  } else {
    ageCategory = 'VETERAN';
    agePenalty = 15; // Moeda antiga
  }

  riskScore += agePenalty;
  components.ageDays = ageDays;
  components.ageCategory = ageCategory;
  components.agePenalty = agePenalty;

  // 4. Dead Weight Risk (Peso Morto de Holders Antigos Presos)
  let deadWeightRisk = 0;
  let isDeadWeight = false;

  if (ageDays > 730) { // > 2 anos
    // Se preço estiver muito abaixo da máxima histórica (> 80% de queda) e sem volume expressivo
    if (athChangePct <= -80.0 && liquidityRatio < 0.10) {
      deadWeightRisk = 25; // Holders presos esperando saída no zero a zero
      isDeadWeight = true;
    } else if (athChangePct >= -35.0 || liquidityRatio >= 0.20) {
      // Rejuvenescimento: perto do ATH ou volume forte
      deadWeightRisk = 0;
      isDeadWeight = false;
    } else {
      deadWeightRisk = 10;
    }
  }

  riskScore += deadWeightRisk;
  components.athChangePct = parseFloat(athChangePct.toFixed(1));
  components.deadWeightRisk = deadWeightRisk;
  components.isDeadWeight = isDeadWeight;

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
