const db = require('./db');

/**
 * Gera reasoning determinístico baseado nos fatores numéricos do score
 */
function buildReasoning(item) {
  const reasoning = [];
  const comp = item.components || {};
  const riskComp = comp.riskComponents || {};

  // 1. Breakout & Médias
  if (comp.isBreakout) {
    const rsiStr = comp.rsi != null ? ` (RSI: ${comp.rsi})` : '';
    reasoning.push(`🚀 Breakout confirmado: ativo rompeu máxima recente com momentum comprador${rsiStr}.`);
  } else if (comp.priceChange24h > 5) {
    reasoning.push(`🔥 Momentum 24h positivo (+${comp.priceChange24h.toFixed(1)}%) com estrutura altista.`);
  }

  // 2. Volume Acceleration
  if (comp.volumeAccelVs7d && comp.volumeAccelVs7d >= 1.5) {
    reasoning.push(`⚡ Injeção de volume: ${comp.volumeAccelVs7d.toFixed(1)}x acima da média móvel dos últimos 7 dias.`);
  }

  // 3. Fase de Idade e Descoberta
  const ageDays = riskComp.ageDays || 60;
  if (ageDays >= 30 && ageDays <= 180) {
    reasoning.push(`🌱 Token com ~${ageDays} dias (Fase de Descoberta): baixa pressão vendedora de holders antigos.`);
  } else if (ageDays > 730 && riskComp.athChangePct >= -35) {
    reasoning.push(`⭐ Ativo consolidado (~${Math.round(ageDays/365)} anos) operando próximo ao topo histórico (${riskComp.athChangePct}% do ATH).`);
  }

  // 4. Diluição e FDV
  const fdvRatio = riskComp.fdvRatio || 1.0;
  const floatPct = riskComp.floatPct || 100;
  if (fdvRatio <= 1.5 && floatPct >= 70) {
    reasoning.push(`🛡️ Baixo risco de diluição: FDV/MCap de ${fdvRatio}x com ${floatPct.toFixed(0)}% do supply já em circulação.`);
  }

  // 5. RSI Saudável
  if (comp.rsi != null && comp.rsi >= 45 && comp.rsi <= 75) {
    reasoning.push(`📈 RSI equilibrado em ${comp.rsi} (sem sobrecompra extrema).`);
  }

  if (reasoning.length === 0) {
    reasoning.push(`📊 Score de oportunidade consolidado em ${item.opportunity_score}/100.`);
  }

  return reasoning.slice(0, 4);
}

/**
 * Gera alertas de risco (risk_flags) específicos
 */
function buildRiskFlags(item) {
  const flags = [];
  const comp = item.components || {};
  const riskComp = comp.riskComponents || {};

  // 1. Estiramento / Extended
  if (item.signal_category === 'EXTENDED' || comp.priceChange24h >= 75) {
    flags.push(`⚠️ Preço esticado (+${comp.priceChange24h.toFixed(1)}% em 24h) — risco alto de compra no topo de euforia.`);
  }

  // 2. Dead Weight Risk
  if (riskComp.isDeadWeight) {
    flags.push(`⚠️ Dead Weight Risk: moeda antiga com ${riskComp.athChangePct}% de queda do ATH — forte pressão de holders querendo sair no zero a zero.`);
  }

  // 3. Diluição de FDV
  if (riskComp.fdvRatio > 3.0) {
    flags.push(`⚠️ FDV/MCap alto (${riskComp.fdvRatio}x): tokens bloqueados representam risco de despejo futuro.`);
  }

  // 4. Liquidez Baixa
  if (riskComp.liquidityRatio < 0.03) {
    flags.push(`⚠️ Giro de liquidez baixo (${(riskComp.liquidityRatio * 100).toFixed(1)}% de volume/MCap) — risco de derrapagem (slippage).`);
  }

  // 5. Token Recém-Lançado
  if (riskComp.ageDays < 30) {
    flags.push(`⚠️ Token muito novo (< 30 dias) — histórico insuficiente e risco de volatilidade extrema.`);
  }

  // 6. RSI Sobrecomprado
  if (comp.rsi != null && comp.rsi > 80) {
    flags.push(`⚠️ RSI em ${comp.rsi} (sobrecompra extrema).`);
  }

  return flags;
}

/**
 * Motor de Recomendação (Buy Signal Engine)
 */
function generateRecommendations(scoresWithMeta, topN = 25) {
  if (!scoresWithMeta || scoresWithMeta.length === 0) return [];

  const candidates = scoresWithMeta.slice(0, topN);
  const recommendations = [];

  for (const item of candidates) {
    const opp = item.opportunity_score;
    const risk = item.risk_score;
    const signal = item.signal_category;
    const comp = item.components || {};
    const riskComp = comp.riskComponents || {};
    const ageDays = riskComp.ageDays || 60;
    const isDeadWeight = riskComp.isDeadWeight || false;

    let verdict = 'WATCH';
    let confidence = 70;

    // Regras de Veredito
    if (signal === 'EXTENDED' || comp.priceChange24h >= 80) {
      verdict = 'TOO_EXTENDED';
      confidence = 90;
    } else if (risk >= 65 || isDeadWeight || riskComp.liquidityRatio < 0.02) {
      verdict = 'AVOID';
      confidence = 85;
    } else if (
      opp >= 70 && 
      risk <= 35 && 
      ( (ageDays >= 30 && ageDays <= 180) || riskComp.athChangePct >= -35 )
    ) {
      verdict = 'STRONG_WATCH';
      confidence = Math.min(95, Math.round(opp * 0.7 + (100 - risk) * 0.3));
    } else if (opp >= 58 && risk <= 50) {
      verdict = 'WATCH';
      confidence = Math.min(80, Math.round(opp * 0.6 + (100 - risk) * 0.4));
    } else {
      verdict = 'WATCH';
      confidence = 60;
    }

    const reasoning = buildReasoning(item);
    const riskFlags = buildRiskFlags(item);

    recommendations.push({
      coin_id: item.coin_id,
      symbol: (item.symbol || item.coin_id).toUpperCase(),
      name: item.name || item.coin_id,
      image_url: item.image_url || '',
      verdict,
      confidence,
      reasoning,
      risk_flags: riskFlags,
      price_at_recommendation: comp.priceUsd || 0,
      price_change_24h: comp.priceChange24h || 0,
      opportunity_score: opp,
      risk_score: risk,
      final_score: item.final_score,
      created_at: new Date().toISOString(),
    });
  }

  return recommendations;
}

/**
 * Gera o resumo do ciclo de mercado geral
 */
function buildMarketSummary(scoresWithMeta, recommendations) {
  if (!scoresWithMeta || scoresWithMeta.length === 0) {
    return {
      regime: 'INDISPONÍVEL',
      summaryText: 'Aguardando dados de mercado.',
      strongWatchCount: 0,
      boomWatchCount: 0,
      accumulationCount: 0,
      extendedCount: 0,
      avgChange24h: 0,
    };
  }

  const strongWatchCount = recommendations.filter(r => r.verdict === 'STRONG_WATCH').length;
  const boomWatchCount = scoresWithMeta.filter(s => s.signal_category === 'BOOM_WATCH').length;
  const accumulationCount = scoresWithMeta.filter(s => s.signal_category === 'ACCUMULATION').length;
  const extendedCount = scoresWithMeta.filter(s => s.signal_category === 'EXTENDED').length;

  const validChanges = scoresWithMeta.map(s => s.components?.priceChange24h).filter(p => p != null && !isNaN(p));
  const avgChange24h = validChanges.length > 0 ? (validChanges.reduce((a, b) => a + b, 0) / validChanges.length) : 0;

  let regime = 'MERCADO EQUILIBRADO';
  let regimeColor = '#38bdf8';

  if (avgChange24h >= 4.0 && boomWatchCount >= 3) {
    regime = '🚀 RISCO-ON (Aceleração Altista)';
    regimeColor = '#22c55e';
  } else if (accumulationCount >= 5 && avgChange24h >= -1.0) {
    regime = '🐋 ACUMULAÇÃO GERAL (Baleias Ativas)';
    regimeColor = '#06b6d4';
  } else if (avgChange24h <= -3.0) {
    regime = '⚠️ RISCO-OFF (Pressão Vendedora)';
    regimeColor = '#ef4444';
  } else if (extendedCount >= 5) {
    regime = '⚠️ MERCADO ESTICADO (Cuidado com Topos)';
    regimeColor = '#f59e0b';
  }

  const summaryText = `No ciclo atual, ${strongWatchCount} ativos receberam veredito STRONG_WATCH e ${boomWatchCount} estão em BOOM WATCH. A variação média do top ${scoresWithMeta.length} é de ${avgChange24h >= 0 ? '+' : ''}${avgChange24h.toFixed(2)}% em 24h.`;

  return {
    regime,
    regimeColor,
    summaryText,
    strongWatchCount,
    boomWatchCount,
    accumulationCount,
    extendedCount,
    avgChange24h: parseFloat(avgChange24h.toFixed(2)),
    updatedAt: new Date().toISOString(),
  };
}

module.exports = {
  generateRecommendations,
  buildMarketSummary,
  buildReasoning,
  buildRiskFlags,
};
