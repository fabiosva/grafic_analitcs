const assert = require('assert');
const indicators = require('./indicators');
const risk = require('./risk');
const scorer = require('./scorer');
const config = require('./config');

console.log('🧪 Iniciando testes unitários do Crypto Boom Scanner...\n');

// Teste 1: EMA
console.log('1. Testando cálculo de EMA...');
const prices = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20];
assert.strictEqual(indicators.calculateEMA(prices, 20), null, 'EMA com histórico menor que período deve retornar null');
const prices50 = Array.from({ length: 60 }, (_, i) => 100 + i);
const ema20 = indicators.calculateEMA(prices50, 20);
assert.ok(ema20 > 100, 'EMA20 deve ser calculada corretamente');
console.log('✅ Teste EMA passou com sucesso.');

// Teste 2: RSI
console.log('2. Testando cálculo de RSI e tratamento de warm-up...');
assert.strictEqual(indicators.calculateRSI([10, 11, 12], 14), null, 'RSI com menos de 15 pontos deve retornar null');
const rsiPrices = [44, 44.3, 44.1, 43.9, 44.5, 44.8, 45.2, 45.9, 46.1, 46.5, 46.8, 47.1, 47.5, 47.9, 48.2, 48.5];
const rsiVal = indicators.calculateRSI(rsiPrices, 14);
assert.ok(rsiVal > 50 && rsiVal <= 100, `RSI em tendência de alta deve ser > 50 (calculado: ${rsiVal})`);
console.log('✅ Teste RSI passou com sucesso.');

// Teste 3: Risco
console.log('3. Testando cálculo de Risco (FDV, Idade, Liquidez)...');
const safeSnapshot = {
  market_cap: 100000000,
  fdv: 120000000, // FDV ratio 1.2x (ótimo)
  volume_24h: 10000000, // Giro 10% (ótimo)
};
const safeRisk = risk.computeRisk(safeSnapshot, { ageDays: 200 });
assert.strictEqual(safeRisk.riskScore, 0, 'Ativo maduro com baixo FDV e boa liquidez deve ter risco 0');

const riskySnapshot = {
  market_cap: 5000000,
  fdv: 60000000, // FDV ratio 12x (> 10x crítico = 40 pts)
  volume_24h: 50000, // Giro 1% (< 2% = 25 pts)
};
const riskyRisk = risk.computeRisk(riskySnapshot, { ageDays: 15 }); // < 30d = 35 pts
assert.strictEqual(riskyRisk.riskScore, 100, 'Ativo novo com alto FDV e baixa liquidez deve ter risco máximo (100)');
console.log('✅ Teste Risco passou com sucesso.');

// Teste 4: Scorer e Fator de Penalidade (0.50)
console.log('4. Testando Opportunity, Risk Penalty (0.50) e Sinal BOOM WATCH...');
const boomSnapshot = {
  coin_id: 'super-gem',
  price_usd: 2.50,
  market_cap: 50000000, // $50M (< $1B)
  fdv: 60000000,
  volume_24h: 15000000,
  price_change_1h: 2.5,
  price_change_24h: 18.0,
  price_change_7d: 45.0,
  price_change_30d: 80.0,
  market_cap_rank: 180,
  snapshot_time: new Date().toISOString(),
};

const historySnapshots = [
  { price_usd: 1.80, volume_24h: 4000000, market_cap_rank: 210, snapshot_time: new Date(Date.now() - 3600000).toISOString() }
];

const scoreResult = scorer.calculateScore(boomSnapshot, historySnapshots, [], { ageDays: 180 });
console.log('Score calculado:', {
  opportunity: scoreResult.opportunity_score,
  risk: scoreResult.risk_score,
  final: scoreResult.final_score,
  signal: scoreResult.signal_category,
});

assert.ok(scoreResult.opportunity_score >= 70, 'Opportunity deve ser alto para setup de alta confluência');
assert.ok(scoreResult.final_score > 60, 'Final Score deve ser elevado');
assert.ok(['BOOM_WATCH', 'MOMENTUM'].includes(scoreResult.signal_category), 'Deve classificar como BOOM_WATCH ou MOMENTUM');
console.log('✅ Teste Scorer passou com sucesso.');

// Teste 5: Sinal de Acumulação
console.log('5. Testando detecção de Acumulação (Volume 2x + Preço Calmo)...');
const accumSnapshot = {
  coin_id: 'whale-accum',
  price_usd: 1.00,
  market_cap: 80000000,
  fdv: 90000000,
  volume_24h: 20000000, // 2x maior que histórico
  price_change_1h: 0.1,
  price_change_24h: 1.2, // preço calmo
  price_change_7d: 3.0,
  price_change_30d: 5.0,
  market_cap_rank: 150,
  snapshot_time: new Date().toISOString(),
};
const accumHistory = [
  { price_usd: 0.99, volume_24h: 9000000, market_cap_rank: 150, snapshot_time: new Date(Date.now() - 3600000).toISOString() }
];
const accumScore = scorer.calculateScore(accumSnapshot, accumHistory, [], { ageDays: 200 });
assert.strictEqual(accumScore.signal_category, 'ACCUMULATION', 'Deve detectar sinal de ACUMULAÇÃO');
console.log('✅ Teste Acumulação passou com sucesso.');

// Teste 6: Sinal Extended (+80%)
console.log('6. Testando flag EXTENDED (+85% 24h)...');
const pumpSnapshot = {
  coin_id: 'pumped-coin',
  price_usd: 10.0,
  market_cap: 30000000,
  fdv: 40000000,
  volume_24h: 50000000,
  price_change_1h: 5.0,
  price_change_24h: 88.0, // > 80%
  price_change_7d: 150.0,
  price_change_30d: 200.0,
  snapshot_time: new Date().toISOString(),
};
const pumpScore = scorer.calculateScore(pumpSnapshot, [], [], { ageDays: 100 });
assert.strictEqual(pumpScore.signal_category, 'EXTENDED', 'Deve marcar como ⚠️ EXTENDED');
console.log('✅ Teste Extended passou com sucesso.');

console.log('\n🎉 TODOS OS TESTES PASSARAM COM 100% DE SUCESSO!\n');
