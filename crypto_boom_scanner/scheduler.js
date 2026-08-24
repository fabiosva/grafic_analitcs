const cron = require('node-cron');
const config = require('./config');
const collector = require('./collector');
const scorer = require('./scorer');
const alerts = require('./alerts');
const backtest = require('./backtest');
const db = require('./db');

let isRunning = false;
let previousTop10 = [];

/**
 * Executa um ciclo completo do scanner
 */
async function executeScanCycle() {
  if (isRunning) {
    console.log('[Scheduler] Ciclo anterior ainda em execução. Pulando...');
    return;
  }

  const startTime = Date.now();
  isRunning = true;
  console.log(`\n======================================================`);
  console.log(`[Scheduler] 🚀 Iniciando ciclo de scan às ${new Date().toISOString()}`);
  console.log(`======================================================`);

  try {
    // 1. Coleta de Mercado (CoinGecko)
    const collectResult = await collector.collectTopCoins();
    const coins = collectResult.coins || [];

    if (coins.length === 0) {
      console.warn('[Scheduler] Nenhuma moeda coletada neste ciclo.');
      isRunning = false;
      return;
    }

    console.log(`[Scheduler] Processando indicadores e scores para ${coins.length} moedas...`);

    // Carregar todos os snapshots recentes para agilizar os cálculos
    const allRecentSnapshots = await db.getAllRecentSnapshots(720); // 30 dias

    // Mapear por moeda
    const snapshotsByCoin = new Map();
    for (const snap of allRecentSnapshots) {
      if (!snapshotsByCoin.has(snap.coin_id)) {
        snapshotsByCoin.set(snap.coin_id, []);
      }
      snapshotsByCoin.get(snap.coin_id).push(snap);
    }

    const calculatedScores = [];

    // 2. Calcular Score e Indicadores para cada moeda
    for (const item of coins) {
      const coinId = item.meta.id;
      const historySnapshots = snapshotsByCoin.get(coinId) || [];
      const previousScores = await db.getHistoricalScoresForCoin(coinId, 48);

      const scoreObj = scorer.calculateScore(
        item.snapshot,
        historySnapshots,
        previousScores,
        { ageDays: item.meta.ageDays }
      );

      calculatedScores.push({
        ...scoreObj,
        symbol: item.meta.symbol,
        name: item.meta.name,
        image_url: item.meta.image,
      });
    }

    // Ordenar por Final Score decrescente
    calculatedScores.sort((a, b) => b.final_score - a.final_score);

    // 3. Persistir Scores no Banco
    console.log(`[Scheduler] Salvando ${calculatedScores.length} scores no Supabase/DB...`);
    const dbScoresToInsert = calculatedScores.map(s => ({
      coin_id: s.coin_id,
      opportunity_score: s.opportunity_score,
      risk_score: s.risk_score,
      final_score: s.final_score,
      signal_category: s.signal_category,
      delta_6h: s.delta_6h,
      delta_12h: s.delta_12h,
      delta_24h: s.delta_24h,
      components: s.components,
      created_at: s.created_at,
    }));
    await db.insertScores(dbScoresToInsert);

    // 4. Processar Alertas
    console.log(`[Scheduler] Avaliando regras de alerta e notificações...`);
    const alertResults = await alerts.processAlerts(calculatedScores, previousTop10);
    previousTop10 = alertResults.currentTop10 || [];

    // 5. Exibir Resumo no Terminal
    const duration = ((Date.now() - startTime) / 1000).toFixed(1);
    console.log(`\n--- Top 10 Oportunidades do Ciclo (${duration}s) ---`);
    console.table(calculatedScores.slice(0, 10).map((s, idx) => ({
      '#': idx + 1,
      'Moeda': s.symbol.toUpperCase(),
      'Final Score': `${s.final_score}/100`,
      'Opportunity': s.opportunity_score,
      'Risk': s.risk_score,
      'Sinal': s.signal_category,
      '24h %': `${s.components?.priceChange24h?.toFixed(1)}%`,
      'Vol Accel': `${s.components?.volumeAccelVs7d}x`,
      'RSI': s.components?.rsi != null ? s.components.rsi : 'Coletando...',
    })));

  } catch (err) {
    console.error('[Scheduler ERROR]', err.stack || err.message);
  } finally {
    isRunning = false;
  }
}

/**
 * Inicialização do Agendador (Snapshots + Backtest Diário)
 */
function startScheduler() {
  const intervalMin = config.collector.snapshotIntervalMinutes;
  const cronExpr = intervalMin === 60 ? '0 * * * *' : `*/${intervalMin} * * * *`;

  console.log(`[Scheduler] ⏰ Agendador de Snapshots ativo: a cada ${intervalMin} min (${cronExpr})`);
  console.log(`[Scheduler] 📊 Agendador de Backtest ativo: diariamente à meia-noite (0 0 * * *)`);

  // Cron dos snapshots horários
  cron.schedule(cronExpr, () => {
    executeScanCycle();
  });

  // Cron diário para atualizar o Backtest histórico
  cron.schedule('0 0 * * *', () => {
    console.log('[Scheduler] Executando rotina diária de Backtest...');
    backtest.runBacktest().catch(e => console.error(e));
  });

  // Executar primeiro ciclo na inicialização
  executeScanCycle();
}

// Execução via linha de comando
if (require.main === module) {
  const args = process.argv.slice(2);
  if (args.includes('--now')) {
    executeScanCycle().then(() => {
      console.log('[Scheduler] Ciclo sob demanda finalizado.');
      process.exit(0);
    });
  } else {
    startScheduler();
  }
}

module.exports = {
  executeScanCycle,
  startScheduler,
};
