const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs');
const config = require('./config');
const db = require('./db');
const backtest = require('./backtest');
const scheduler = require('./scheduler');

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

const BTC_DATA_DIR = path.join(__dirname, '..', 'collector', 'data');
const BTC_LATEST_FILE = path.join(BTC_DATA_DIR, 'latest.json');
const BTC_HISTORY_FILE = path.join(BTC_DATA_DIR, 'history.json');

// 1. API: Listagem de Rankings e Scores
app.get('/api/scanner/rankings', async (req, res) => {
  try {
    const scores = await db.getLatestScores();
    res.json({
      success: true,
      count: scores.length,
      timestamp: new Date().toISOString(),
      data: scores,
    });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// 2. API: Recomendações Automáticas (Adendo v3)
app.get('/api/scanner/recommendations', async (req, res) => {
  try {
    const recommendations = await db.getLatestRecommendations(20);
    const summary = await db.getMarketSummary();
    res.json({
      success: true,
      summary,
      count: recommendations.length,
      data: recommendations,
    });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// 3. API: Detalhes e Histórico de uma Moeda
app.get('/api/scanner/coin/:id', async (req, res) => {
  try {
    const coinId = req.params.id;
    const snapshots = await db.getCoinSnapshots(coinId, 168);
    const scoreHistory = await db.getHistoricalScoresForCoin(coinId, 72);
    res.json({
      success: true,
      coinId,
      snapshots,
      scoreHistory,
    });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// 4. API: Resultados de Backtest
app.get('/api/scanner/backtest', async (req, res) => {
  try {
    let results = await db.getBacktestResults();
    if (!results || results.length === 0) {
      results = await backtest.runBacktest();
    }
    res.json({ success: true, data: results });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

app.post('/api/scanner/backtest/recalculate', async (req, res) => {
  try {
    const results = await backtest.runBacktest();
    res.json({ success: true, message: 'Backtest recalculado com sucesso!', data: results });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// 5. API: Alertas Recentes
app.get('/api/scanner/alerts', async (req, res) => {
  try {
    const alerts = await db.getRecentAlerts(50);
    res.json({ success: true, data: alerts });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// 6. API: Disparo Manual de Coleta
app.post('/api/scanner/trigger', async (req, res) => {
  try {
    scheduler.executeScanCycle().catch(e => console.error(e));
    res.json({ success: true, message: 'Ciclo de scan disparado com sucesso!' });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// 7. API: Status do Sistema
app.get('/api/scanner/status', async (req, res) => {
  try {
    const scores = await db.getLatestScores();
    const lastUpdate = scores.length > 0 ? scores[0].created_at : null;
    const boomCount = scores.filter(s => s.signal_category === 'BOOM_WATCH').length;
    const momentumCount = scores.filter(s => s.signal_category === 'MOMENTUM').length;
    const accumCount = scores.filter(s => s.signal_category === 'ACCUMULATION').length;

    res.json({
      success: true,
      status: 'online',
      coinsTracked: scores.length,
      lastUpdate,
      signalsSummary: {
        boomWatch: boomCount,
        momentum: momentumCount,
        accumulation: accumCount,
      },
    });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

// 8. API: Integração BTC
app.get('/api/btc/latest', async (req, res) => {
  try {
    if (db.supabase) {
      const { data, error } = await db.supabase
        .from('bottom_indicators')
        .select('*')
        .order('data', { ascending: false })
        .limit(1);
      if (!error && data && data.length > 0) {
        return res.json({ success: true, source: 'supabase', data: data[0] });
      }
    }

    if (fs.existsSync(BTC_LATEST_FILE)) {
      const row = JSON.parse(fs.readFileSync(BTC_LATEST_FILE, 'utf-8'));
      return res.json({ success: true, source: 'local', data: row });
    }

    res.status(404).json({ success: false, error: 'Dados do BTC não encontrados.' });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

app.get('/api/btc/history', async (req, res) => {
  try {
    if (db.supabase) {
      const { data, error } = await db.supabase
        .from('bottom_indicators')
        .select('*')
        .order('data', { ascending: true });
      if (!error && data && data.length > 0) {
        return res.json({ success: true, source: 'supabase', data });
      }
    }

    if (fs.existsSync(BTC_HISTORY_FILE)) {
      const history = JSON.parse(fs.readFileSync(BTC_HISTORY_FILE, 'utf-8'));
      return res.json({ success: true, source: 'local', data: history });
    }

    res.status(404).json({ success: false, error: 'Histórico do BTC não encontrado.' });
  } catch (err) {
    res.status(500).json({ success: false, error: err.message });
  }
});

app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

const PORT = config.server.port;
if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`[Dashboard] 🚀 Painel Unificado Node.js (v3) rodando em http://localhost:${PORT}`);
  });
}

module.exports = app;
