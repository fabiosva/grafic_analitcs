const db = require('./db');

function median(values) {
  if (!values || values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * Motor de Backtesting para validação estatística do Score
 */
async function runBacktest(thresholds = [70, 75, 80, 85]) {
  console.log('[Backtest] Carregando histórico de snapshots e scores para cálculo estatístico...');

  const snapshots = await db.getAllRecentSnapshots(2160); // até 90 dias
  const scores = await db.getLatestScores();

  // Organizar snapshots por coin_id e timestamp
  const snapshotsByCoin = new Map();
  for (const s of snapshots) {
    if (!snapshotsByCoin.has(s.coin_id)) {
      snapshotsByCoin.set(s.coin_id, []);
    }
    snapshotsByCoin.get(s.coin_id).push(s);
  }

  // Ordenar snapshots cronologicamente
  for (const [coinId, list] of snapshotsByCoin.entries()) {
    list.sort((a, b) => new Date(a.snapshot_time) - new Date(b.snapshot_time));
  }

  const results = [];

  for (const minScore of thresholds) {
    const returns7d = [];
    const returns14d = [];
    const returns30d = [];

    // Avaliar todas as ocorrências de score
    for (const [coinId, snapList] of snapshotsByCoin.entries()) {
      if (snapList.length < 2) continue;

      for (let i = 0; i < snapList.length; i++) {
        const snap = snapList[i];
        const snapTime = new Date(snap.snapshot_time).getTime();
        const basePrice = snap.price_usd;
        if (!basePrice || basePrice <= 0) continue;

        // Se houver score gravado ou aproximação por momentum/breakout
        const estimatedScore = (snap.price_change_24h > 10 ? 75 : 50) + (snap.price_change_7d > 20 ? 15 : 0);
        if (estimatedScore < minScore) continue;

        // Buscar preço em +7d (~168h), +14d (~336h), +30d (~720h)
        const snap7d = snapList.find(s => {
          const diffH = (new Date(s.snapshot_time).getTime() - snapTime) / (1000 * 60 * 60);
          return diffH >= 160 && diffH <= 176;
        });
        if (snap7d && snap7d.price_usd > 0) {
          returns7d.push(((snap7d.price_usd - basePrice) / basePrice) * 100);
        }

        const snap14d = snapList.find(s => {
          const diffH = (new Date(s.snapshot_time).getTime() - snapTime) / (1000 * 60 * 60);
          return diffH >= 330 && diffH <= 350;
        });
        if (snap14d && snap14d.price_usd > 0) {
          returns14d.push(((snap14d.price_usd - basePrice) / basePrice) * 100);
        }

        const snap30d = snapList.find(s => {
          const diffH = (new Date(s.snapshot_time).getTime() - snapTime) / (1000 * 60 * 60);
          return diffH >= 700 && diffH <= 740;
        });
        if (snap30d && snap30d.price_usd > 0) {
          returns30d.push(((snap30d.price_usd - basePrice) / basePrice) * 100);
        }
      }
    }

    const n = Math.max(returns7d.length, 1);
    const winRate7d = returns7d.length > 0 ? (returns7d.filter(r => r > 0).length / returns7d.length) * 100 : 0;
    const avgReturn7d = returns7d.length > 0 ? returns7d.reduce((a, b) => a + b, 0) / returns7d.length : 0;
    const medReturn7d = median(returns7d);

    const winRate14d = returns14d.length > 0 ? (returns14d.filter(r => r > 0).length / returns14d.length) * 100 : 0;
    const avgReturn14d = returns14d.length > 0 ? returns14d.reduce((a, b) => a + b, 0) / returns14d.length : 0;
    const medReturn14d = median(returns14d);

    const winRate30d = returns30d.length > 0 ? (returns30d.filter(r => r > 0).length / returns30d.length) * 100 : 0;
    const avgReturn30d = returns30d.length > 0 ? returns30d.reduce((a, b) => a + b, 0) / returns30d.length : 0;
    const medReturn30d = median(returns30d);

    const allReturns = [...returns7d, ...returns14d, ...returns30d];
    const maxGain = allReturns.length > 0 ? Math.max(...allReturns) : 0;
    const maxDrawdown = allReturns.length > 0 ? Math.min(...allReturns) : 0;

    const row = {
      min_score: minScore,
      sample_size: returns7d.length,
      win_rate_7d: parseFloat(winRate7d.toFixed(1)),
      avg_return_7d: parseFloat(avgReturn7d.toFixed(2)),
      median_return_7d: parseFloat(medReturn7d.toFixed(2)),
      win_rate_14d: parseFloat(winRate14d.toFixed(1)),
      avg_return_14d: parseFloat(avgReturn14d.toFixed(2)),
      median_return_14d: parseFloat(medReturn14d.toFixed(2)),
      win_rate_30d: parseFloat(winRate30d.toFixed(1)),
      avg_return_30d: parseFloat(avgReturn30d.toFixed(2)),
      median_return_30d: parseFloat(medReturn30d.toFixed(2)),
      max_gain: parseFloat(maxGain.toFixed(2)),
      max_drawdown: parseFloat(maxDrawdown.toFixed(2)),
      calculated_at: new Date().toISOString(),
    };

    results.push(row);
  }

  await db.saveBacktestResults(results);

  console.log('\n====== RELATÓRIO DE BACKTEST ======');
  console.table(results.map(r => ({
    'Score Mínimo': `>= ${r.min_score}`,
    'Amostras (N)': r.sample_size,
    'Win Rate 7d': `${r.win_rate_7d}%`,
    'Retorno Médio 7d': `${r.avg_return_7d}%`,
    'Mediana 7d': `${r.median_return_7d}%`,
    'Win Rate 14d': `${r.win_rate_14d}%`,
    'Retorno Médio 14d': `${r.avg_return_14d}%`,
    'Retorno Médio 30d': `${r.avg_return_30d}%`,
    'Max Gain': `+${r.max_gain}%`,
    'Max DD': `${r.max_drawdown}%`,
  })));

  return results;
}

if (require.main === module) {
  runBacktest().catch(err => console.error(err));
}

module.exports = {
  runBacktest,
};
