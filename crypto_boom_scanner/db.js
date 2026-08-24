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

// Arquivos locais de fallback
const LOCAL_COINS_FILE = path.join(DATA_DIR, 'coins.json');
const LOCAL_SNAPSHOTS_FILE = path.join(DATA_DIR, 'snapshots.json');
const LOCAL_SCORES_FILE = path.join(DATA_DIR, 'scores.json');
const LOCAL_RECS_FILE = path.join(DATA_DIR, 'recommendations.json');
const LOCAL_SUMMARY_FILE = path.join(DATA_DIR, 'market_summary.json');
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

// 1. Obter todas as moedas conhecidas
async function getAllKnownCoins() {
  if (supabase) {
    try {
      const { data, error } = await supabase.from('coins').select('*');
      if (!error && data) {
        const map = {};
        data.forEach(c => { map[c.id] = c; });
        return map;
      }
    } catch (e) {}
  }
  return readJsonFile(LOCAL_COINS_FILE, {});
}

// 2. Upsert Moedas
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
          image_url: c.image_url || c.image,
          genesis_date: c.genesis_date,
          first_seen_at: c.first_seen_at,
          age_days: c.age_days,
          age_source: c.age_source,
          updated_at: new Date().toISOString(),
        })),
        { onConflict: 'id' }
      );
    if (error) console.error('Erro Supabase upsertCoins:', error.message);
  }

  const current = readJsonFile(LOCAL_COINS_FILE, {});
  coinsList.forEach(c => {
    current[c.id] = {
      id: c.id,
      symbol: c.symbol.toLowerCase(),
      name: c.name,
      image_url: c.image_url || c.image,
      genesis_date: c.genesis_date,
      first_seen_at: c.first_seen_at,
      age_days: c.age_days,
      age_source: c.age_source,
      updated_at: new Date().toISOString(),
    };
  });
  writeJsonFile(LOCAL_COINS_FILE, current);
}

// 3. Inserir Snapshots
async function insertSnapshots(snapshotsList) {
  if (!snapshotsList || snapshotsList.length === 0) return;

  if (supabase) {
    const { error } = await supabase
      .from('coin_snapshots')
      .upsert(snapshotsList, { onConflict: 'coin_id,snapshot_time' });
    if (error) console.error('Erro Supabase insertSnapshots:', error.message);
  }

  const localSnapshots = readJsonFile(LOCAL_SNAPSHOTS_FILE, []);
  const combined = [...snapshotsList, ...localSnapshots].slice(0, 50000);
  writeJsonFile(LOCAL_SNAPSHOTS_FILE, combined);
}

// 4. Inserir Scores
async function insertScores(scoresList) {
  if (!scoresList || scoresList.length === 0) return;

  if (supabase) {
    const { error } = await supabase
      .from('coin_scores')
      .insert(scoresList);
    if (error) console.error('Erro Supabase insertScores:', error.message);
  }

  const localScores = readJsonFile(LOCAL_SCORES_FILE, []);
  const combined = [...scoresList, ...localScores].slice(0, 30000);
  writeJsonFile(LOCAL_SCORES_FILE, combined);
}

// 5. Inserir e Buscar Recomendações (Adendo v3)
async function insertRecommendations(recsList) {
  if (!recsList || recsList.length === 0) return;

  if (supabase) {
    const { error } = await supabase
      .from('recommendations')
      .insert(recsList.map(r => ({
        coin_id: r.coin_id,
        verdict: r.verdict,
        confidence: r.confidence,
        reasoning: r.reasoning,
        risk_flags: r.risk_flags,
        price_at_recommendation: r.price_at_recommendation,
        opportunity_score: r.opportunity_score,
        risk_score: r.risk_score,
        final_score: r.final_score,
        created_at: r.created_at || new Date().toISOString(),
      })));
    if (error) console.error('Erro Supabase insertRecommendations:', error.message);
  }

  writeJsonFile(LOCAL_RECS_FILE, recsList);
}

async function getLatestRecommendations(limit = 10) {
  if (supabase) {
    try {
      const { data, error } = await supabase
        .from('recommendations')
        .select(`
          *, coins(id, symbol, name, image_url, age_days)
        `)
        .order('created_at', { ascending: false })
        .limit(limit);

      if (!error && data && data.length > 0) return data;
    } catch (e) {}
  }
  return readJsonFile(LOCAL_RECS_FILE, []).slice(0, limit);
}

// 6. Resumo de Mercado (Market Summary)
async function saveMarketSummary(summary) {
  writeJsonFile(LOCAL_SUMMARY_FILE, summary);
}

async function getMarketSummary() {
  return readJsonFile(LOCAL_SUMMARY_FILE, null);
}

// 7. Obter Últimos Scores
async function getLatestScores() {
  if (supabase) {
    try {
      const { data, error } = await supabase
        .from('coin_scores')
        .select(`
          id, coin_id, opportunity_score, risk_score, final_score, 
          signal_category, delta_6h, delta_12h, delta_24h, components, created_at,
          coins (id, symbol, name, image_url, age_days, age_source)
        `)
        .order('created_at', { ascending: false })
        .limit(1000);

      if (!error && data && data.length > 0) {
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

// 8. Obter Histórico de Snapshots de uma Moeda
async function getCoinSnapshots(coinId, limit = 168) {
  if (supabase) {
    try {
      const { data, error } = await supabase
        .from('coin_snapshots')
        .select('*')
        .eq('coin_id', coinId)
        .order('snapshot_time', { ascending: false })
        .limit(limit);

      if (!error && data) return data.reverse();
    } catch (err) {}
  }

  const local = readJsonFile(LOCAL_SNAPSHOTS_FILE, []);
  return local
    .filter(s => s.coin_id === coinId)
    .sort((a, b) => new Date(a.snapshot_time) - new Date(b.snapshot_time))
    .slice(-limit);
}

// 9. Obter Histórico de Snapshots Recentes
async function getAllRecentSnapshots(hoursLimit = 720) {
  if (supabase) {
    try {
      const sinceDate = new Date(Date.now() - hoursLimit * 60 * 60 * 1000).toISOString();
      const { data, error } = await supabase
        .from('coin_snapshots')
        .select('*')
        .gte('snapshot_time', sinceDate)
        .order('snapshot_time', { ascending: true });

      if (!error && data) return data;
    } catch (err) {}
  }

  const local = readJsonFile(LOCAL_SNAPSHOTS_FILE, []);
  const sinceMs = Date.now() - hoursLimit * 60 * 60 * 1000;
  return local
    .filter(s => new Date(s.snapshot_time).getTime() >= sinceMs)
    .sort((a, b) => new Date(a.snapshot_time) - new Date(b.snapshot_time));
}

// 10. Obter Histórico de Scores de uma Moeda
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

// 11. Eventos e Alertas
async function insertEvent(event) {
  if (supabase) {
    await supabase.from('score_events').insert([event]);
  }
  const events = readJsonFile(LOCAL_EVENTS_FILE, []);
  events.unshift({ ...event, created_at: new Date().toISOString() });
  writeJsonFile(LOCAL_EVENTS_FILE, events.slice(0, 1000));
}

async function insertAlert(alert) {
  if (supabase) {
    await supabase.from('alerts').insert([alert]);
  }
  const alerts = readJsonFile(LOCAL_ALERTS_FILE, []);
  alerts.unshift({ ...alert, sent_at: new Date().toISOString() });
  writeJsonFile(LOCAL_ALERTS_FILE, alerts.slice(0, 1000));
}

async function getRecentAlerts(limit = 50) {
  if (supabase) {
    const { data } = await supabase.from('alerts').select('*').order('sent_at', { ascending: false }).limit(limit);
    if (data) return data;
  }
  return readJsonFile(LOCAL_ALERTS_FILE, []).slice(0, limit);
}

// 12. Backtests
async function saveBacktestResults(results) {
  if (supabase) {
    await supabase.from('backtest_results').insert(results);
  }
  writeJsonFile(LOCAL_BACKTEST_FILE, results);
}

async function getBacktestResults() {
  if (supabase) {
    const { data } = await supabase.from('backtest_results').select('*').order('calculated_at', { ascending: false }).limit(20);
    if (data && data.length > 0) return data;
  }
  return readJsonFile(LOCAL_BACKTEST_FILE, []);
}

module.exports = {
  supabase,
  getAllKnownCoins,
  upsertCoins,
  insertSnapshots,
  insertScores,
  insertRecommendations,
  getLatestRecommendations,
  saveMarketSummary,
  getMarketSummary,
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
