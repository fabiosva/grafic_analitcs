const assert = require('assert');
const indicators = require('./indicators');
const risk = require('./risk');
const scorer = require('./scorer');
const recommender = require('./recommender');

console.log('🧪 Iniciando testes unitários do Crypto Boom Scanner (v3)...\n');

// 1. EMA
console.log('1. Testando EMA com sparkline histórica...');
const prices = Array.from({ length: 60 }, (_, i) => 100 + i);
const ema20 = indicators.calculateEMA(prices, 20);
assert.ok(ema20 > 100, 'EMA20 deve ser calculada');
console.log('✅ Teste EMA passou com sucesso.');

// 2. RSI
console.log('2. Testando cálculo de RSI (14)...');
const rsiPrices = [44, 44.3, 44.1, 43.9, 44.5, 44.8, 45.2, 45.9, 46.1, 46.5, 46.8, 47.1, 47.5, 47.9, 48.2, 48.5];
const rsiVal = indicators.calculateRSI(rsiPrices, 14);
assert.ok(rsiVal > 50 && rsiVal <= 100, `RSI calculado: ${rsiVal}`);
console.log('✅ Teste RSI passou com sucesso.');

// 3. Risco: Fase de Descoberta vs Dead Weight Risk
console.log('3. Testando Idade do Token e Dead Weight Risk...');
const discoverySnapshot = {
  market_cap: 100000000,
  fdv: 120000000,
  volume_24h: 15000000,
  ath_change_percentage: -15.0,
};
const discoveryRisk = risk.computeRisk(discoverySnapshot, { ageDays: 45 }); // Fase de descoberta
assert.strictEqual(discoveryRisk.components.ageCategory, 'DISCOVERY');
assert.strictEqual(discoveryRisk.riskScore, 0, 'Ativo na fase de descoberta (45d) com baixo FDV deve ter risco 0');

const deadWeightSnapshot = {
  market_cap: 30000000,
  fdv: 30000000,
  volume_24h: 500000, // giro 1.6%
  ath_change_percentage: -92.0, // -92% do topo
};
const deadWeightRisk = risk.computeRisk(deadWeightSnapshot, { ageDays: 1100 }); // > 2 anos
assert.strictEqual(deadWeightRisk.components.isDeadWeight, true, 'Deve identificar Dead Weight Risk');
assert.ok(deadWeightRisk.riskScore >= 50, 'Dead Weight com baixa liquidez deve ter risco alto');
console.log('✅ Teste Risco & Dead Weight passou com sucesso.');

// 4. Scorer e Sinal BOOM WATCH
console.log('4. Testando Opportunity e Sinal BOOM WATCH...');
const boomSnapshot = {
  coin_id: 'super-gem',
  price_usd: 2.50,
  market_cap: 50000000,
  fdv: 60000000,
  volume_24h: 15000000,
  price_change_1h: 2.5,
  price_change_24h: 18.0,
  price_change_7d: 45.0,
  price_change_30d: 80.0,
  market_cap_rank: 180,
  snapshot_time: new Date().toISOString(),
  sparkline_prices: Array.from({ length: 50 }, (_, i) => 1.5 + (i * 0.02)),
};
const historySnapshots = [
  { price_usd: 1.80, volume_24h: 4000000, market_cap_rank: 210, snapshot_time: new Date(Date.now() - 3600000).toISOString() }
];
const scoreResult = scorer.calculateScore(boomSnapshot, historySnapshots, [], { ageDays: 60 });
console.log('Score calculado:', {
  opportunity: scoreResult.opportunity_score,
  risk: scoreResult.risk_score,
  final: scoreResult.final_score,
  signal: scoreResult.signal_category,
});
assert.ok(scoreResult.opportunity_score >= 70, 'Opportunity deve ser alto');
assert.strictEqual(scoreResult.signal_category, 'BOOM_WATCH');
console.log('✅ Teste Scorer passou com sucesso.');

// 5. Motor de Recomendação (recommender.js)
console.log('5. Testando Motor de Recomendação Automática (recommender.js)...');
const recs = recommender.generateRecommendations([{
  ...scoreResult,
  symbol: 'GEM',
  name: 'Super Gem',
}], 5);

assert.strictEqual(recs.length, 1);
assert.strictEqual(recs[0].verdict, 'STRONG_WATCH', 'Deve recomendar STRONG_WATCH');
assert.ok(recs[0].confidence >= 80, 'Confiança deve ser alta');
assert.ok(recs[0].reasoning.length >= 2, 'Deve gerar tópicos de reasoning em português');
console.log('Recomendação gerada:', {
  symbol: recs[0].symbol,
  verdict: recs[0].verdict,
  confidence: recs[0].confidence,
  reasoning: recs[0].reasoning,
});
console.log('✅ Teste Recommender passou com sucesso.');

// 6. Resumo de Mercado
console.log('6. Testando Resumo de Mercado...');
const summary = recommender.buildMarketSummary([scoreResult], recs);
assert.ok(summary.regime.length > 0);
assert.strictEqual(summary.strongWatchCount, 1);
console.log('Resumo do Mercado:', summary.regime, summary.summaryText);
console.log('✅ Teste Resumo de Mercado passou com sucesso.');

console.log('\n🎉 TODOS OS TESTES PASSARAM COM 100% DE SUCESSO!\n');
