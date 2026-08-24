const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');
const path = require('path');
const config = require('./config');

const DATA_DIR = path.join(__dirname, 'data');
if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

let supabase = null;
if (config.supabase.url && config.supabase.key) {
  supabase = createClient(config.supabase.url, config.supabase.key, {
    auth: { persistSession: false },
  });
}

// Arquivos de fallback local
const LOCAL_COINS_FILE = path.join(DATA_DIR, 'coins.json');
const LOCAL_SNAPSHOTS_FILE = path.join(DATA_DIR, 'snapshots.json');
const LOCAL_SCORES_FILE = path.join(DATA_DIR, 'scores.json');
const LOCAL_EVENTS_FILE = path.join(DATA_DIR, 'events.json');
const LOCAL_ALERTS_FILE = path.join(DATA_DIR, 'alerts.json');
const LOCAL_BACKTEST_FILE = path.join(DATA_DIR, 'backtest.json');

function readJsonFile(filePath, defaultVal = []) {
  try {
    if (fs.existsSync(filePath)) {
      return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    }
  } catch (err) {
    console.error(`Erro ao ler ${filePath}:`, err.message);
  }
  return defaultVal;
}

function writeJsonFile(filePath, data) {
  try {
    fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf-8');
  } catch (err) {
    console.error(`Erro ao gravar ${filePath}:`, err.message);
  }
}

// 1. Upsert Moedas
async function upsertCoins(coinsList) {
  if (!coinsList || coinsList.length === 0) return;

  if (supabase) {
    const { error } = await supabase
      .from('coins')
      .upsert(
        coinsList.map(c => ({
          id: c.id,
          symbol: c.symbol.toLowerCase(),
          name: c.name,
          image_url: c.image,
          updated_at: new Date().toISOString(),
        })),
        { onConflict: 'id' }
      );
    if (error) console.error('Erro Supabase upsertCoins:', error.message);
  }

  // Backup local
  const current = readJsonFile(LOCAL_COINS_FILE, {});
  coinsList.forEach(c => {
    current[c.id] = {
      id: c.id,
      symbol: c.symbol.toLowerCase(),
      name: c.name,
      image_url: c.image,
      updated_at: new Date().toISOString(),
    };
  });
  writeJsonFile(LOCAL_COINS_FILE, current);
}

// 2. Inserir Snapshots
async function insertSnapshots(snapshotsList) {
  if (!snapshotsList || snapshotsList.length === 0) return;

  if (supabase) {
    const { error } = await supabase
      .from('coin_snapshots')
      .upsert(snapshotsList, { onConflict: 'coin_id,snapshot_time' });
    if (error) console.error('Erro Supabase insertSnapshots:', error.message);
  }

  // Histórico local
  const localSnapshots = readJsonFile(LOCAL_SNAPSHOTS_FILE, []);
  // Manter últimos 50.000 snapshots em arquivo local
  const combined = [...snapshotsList, ...localSnapshots].slice(0, 50000);
  writeJsonFile(LOCAL_SNAPSHOTS_FILE, combined);
}

// 3. Inserir Scores
async function insertScores(scoresList) {
  if (!scoresList || scoresList.length === 0) return;

  if (supabase) {
    const { error } = await supabase
      .from('coin_scores')
      .insert(scoresList);
    if (error) console.error('Erro Supabase insertScores:', error.message);
  }

  // Armazenamento local
  const localScores = readJsonFile(LOCAL_SCORES_FILE, []);
  const combined = [...scoresList, ...localScores].slice(0, 30000);
  writeJsonFile(LOCAL_SCORES_FILE, combined);
}

// 4. Inserir Evento
async function insertEvent(event) {
  if (supabase) {
    const { error } = await supabase.from('score_events').insert([event]);
    if (error) console.error('Erro Supabase insertEvent:', error.message);
  }

  const events = readJsonFile(LOCAL_EVENTS_FILE, []);
  events.unshift({ ...event, created_at: new Date().toISOString() });
  writeJsonFile(LOCAL_EVENTS_FILE, events.slice(0, 1000));
}

// 5. Inserir Alerta
async function insertAlert(alert) {
  if (supabase) {
    const { error } = await supabase.from('alerts').insert([alert]);
    if (error) console.error('Erro Supabase insertAlert:', error.message);
  }

  const alerts = readJsonFile(LOCAL_ALERTS_FILE, []);
  alerts.unshift({ ...alert, sent_at: new Date().toISOString() });
  writeJsonFile(LOCAL_ALERTS_FILE, alerts.slice(0, 1000));
}

// 6. Obter Últimos Scores (para Dashboard e Ranking)
async function getLatestScores() {
  if (supabase) {
    try {
      // Buscar scores mais recentes
      const { data, error } = await supabase
        .from('coin_scores')
        .select(`
          id, coin_id, opportunity_score, risk_score, final_score, 
          signal_category, delta_6h, delta_12h, delta_24h, components, created_at,
          coins (id, symbol, name, image_url)
        `)
        .order('created_at', { ascending: false })
        .limit(1000);

      if (!error && data && data.length > 0) {
        // Obter apenas o score mais recente por moeda
        const map = new Map();
        for (const item of data) {
          if (!map.has(item.coin_id)) {
            map.set(item.coin_id, item);
          }
        }
        return Array.from(map.values()).sort((a, b) => b.final_score - a.final_score);
      }
    } catch (err) {
      console.warn('Fallback para dados locais de scores:', err.message);
    }
  }

  // Fallback Local
  const localScores = readJsonFile(LOCAL_SCORES_FILE, []);
  const localCoins = readJsonFile(LOCAL_COINS_FILE, {});
  const map = new Map();

  for (const item of localScores) {
    if (!map.has(item.coin_id)) {
      const coinInfo = localCoins[item.coin_id] || {
        id: item.coin_id,
        symbol: item.coin_id,
        name: item.coin_id,
      };
      map.set(item.coin_id, {
        ...item,
        coins: coinInfo,
      });
    }
  }
  return Array.from(map.values()).sort((a, b) => b.final_score - a.final_score);
}

// 7. Obter Histórico de Snapshots de uma Moeda
async function getCoinSnapshots(coinId, limit = 168) { // 168 = 7 dias a 1h
  if (supabase) {
    try {
      const { data, error } = await supabase
        .from('coin_snapshots')
        .select('*')
        .eq('coin_id', coinId)
        .order('snapshot_time', { ascending: false })
        .limit(limit);

      if (!error && data) return data.reverse();
    } catch (err) {
      console.warn('Erro buscando snapshots no Supabase:', err.message);
    }
  }

  const local = readJsonFile(LOCAL_SNAPSHOTS_FILE, []);
  return local
    .filter(s => s.coin_id === coinId)
    .sort((a, b) => new Date(a.snapshot_time) - new Date(b.snapshot_time))
    .slice(-limit);
}

// 8. Obter Histórico de Todos os Snapshots Recentes (para cálculo em lote de RSI/EMA)
async function getAllRecentSnapshots(hoursLimit = 720) { // 30 dias a 1h
  if (supabase) {
    try {
      const sinceDate = new Date(Date.now() - hoursLimit * 60 * 60 * 1000).toISOString();
      const { data, error } = await supabase
        .from('coin_snapshots')
        .select('*')
        .gte('snapshot_time', sinceDate)
        .order('snapshot_time', { ascending: true });

      if (!error && data) return data;
    } catch (err) {
      console.warn('Erro ao carregar snapshots recentes:', err.message);
    }
  }

  const local = readJsonFile(LOCAL_SNAPSHOTS_FILE, []);
  const sinceMs = Date.now() - hoursLimit * 60 * 60 * 1000;
  return local
    .filter(s => new Date(s.snapshot_time).getTime() >= sinceMs)
    .sort((a, b) => new Date(a.snapshot_time) - new Date(b.snapshot_time));
}

// 9. Obter Deltas de Score Históricos
async function getHistoricalScoresForCoin(coinId, hoursLimit = 48) {
  if (supabase) {
    try {
      const sinceDate = new Date(Date.now() - hoursLimit * 60 * 60 * 1000).toISOString();
      const { data, error } = await supabase
        .from('coin_scores')
        .select('*')
        .eq('coin_id', coinId)
        .gte('created_at', sinceDate)
        .order('created_at', { ascending: false });

      if (!error && data) return data;
    } catch (err) {}
  }

  const local = readJsonFile(LOCAL_SCORES_FILE, []);
  const sinceMs = Date.now() - hoursLimit * 60 * 60 * 1000;
  return local
    .filter(s => s.coin_id === coinId && new Date(s.created_at).getTime() >= sinceMs)
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
}

// 10. Salvar e Obter Backtests
async function saveBacktestResults(results) {
  if (supabase) {
    await supabase.from('backtest_results').insert(results);
  }
  writeJsonFile(LOCAL_BACKTEST_FILE, results);
}

async function getBacktestResults() {
  if (supabase) {
    const { data } = await supabase
      .from('backtest_results')
      .select('*')
      .order('calculated_at', { ascending: false })
      .limit(20);
    if (data && data.length > 0) return data;
  }
  return readJsonFile(LOCAL_BACKTEST_FILE, []);
}

// 11. Obter Últimos Alertas
async function getRecentAlerts(limit = 50) {
  if (supabase) {
    const { data } = await supabase
      .from('alerts')
      .select('*')
      .order('sent_at', { ascending: false })
      .limit(limit);
    if (data) return data;
  }
  return readJsonFile(LOCAL_ALERTS_FILE, []).slice(0, limit);
}

module.exports = {
  supabase,
  upsertCoins,
  insertSnapshots,
  insertScores,
  insertEvent,
  insertAlert,
  getLatestScores,
  getCoinSnapshots,
  getAllRecentSnapshots,
  getHistoricalScoresForCoin,
  saveBacktestResults,
  getBacktestResults,
  getRecentAlerts,
};
