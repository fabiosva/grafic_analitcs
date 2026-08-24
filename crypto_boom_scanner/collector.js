const axios = require('axios');
const config = require('./config');
const db = require('./db');

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function isStablecoin(coin) {
  const symbol = (coin.symbol || '').toLowerCase().trim();
  const name = (coin.name || '').toLowerCase().trim();
  const id = (coin.id || '').toLowerCase().trim();

  if (config.filters.excludedSymbols.includes(symbol)) return true;
  if (config.filters.excludedSymbols.includes(id)) return true;

  if (symbol.endsWith('usd') || symbol.startsWith('usd') || symbol.includes('eur') || symbol.includes('brl')) {
    if (['usd', 'usdt', 'usdc', 'fdusd', 'busd', 'pyusd', 'usde', 'tusd', 'usdd', 'usdp'].some(s => symbol.includes(s))) {
      return true;
    }
  }

  if (name.includes('wrapped') || name.includes('liquid staked') || name.includes('peg') || name.includes('yield-bearing')) {
    if (['steth', 'weth', 'wbtc', 'wsteth', 'cbeth', 'ezeth', 'weeth'].includes(symbol)) return true;
  }

  return false;
}

/**
 * Coleta os mercados da CoinGecko com sparkline=true
 */
async function fetchMarketsPage(page = 1, perPage = 250) {
  const url = `${config.collector.apiUrl}/coins/markets`;
  const params = {
    vs_currency: 'usd',
    order: 'market_cap_desc',
    per_page: perPage,
    page: page,
    sparkline: true,
    price_change_percentage: '1h,24h,7d,30d',
  };

  const headers = {
    'Accept': 'application/json',
    'User-Agent': 'CryptoBoomScanner/3.0',
  };

  if (config.collector.apiKey) {
    headers['x-cg-demo-api-key'] = config.collector.apiKey;
    headers['x-cg-pro-api-key'] = config.collector.apiKey;
  }

  let retries = 3;
  while (retries > 0) {
    try {
      const response = await axios.get(url, { params, headers, timeout: 20000 });
      return response.data;
    } catch (err) {
      retries--;
      const status = err.response ? err.response.status : null;
      if (status === 429) {
        console.warn(`[CoinGecko Rate Limit 429] Aguardando 10s antes de tentar novamente...`);
        await sleep(10000);
      } else {
        console.error(`[Erro CoinGecko Página ${page}] ${err.message}`);
        if (retries > 0) await sleep(3000);
      }
    }
  }
  return [];
}

/**
 * Executa o ciclo completo de coleta do Top 300-500 com sparklines, ATH e cálculo de idade
 */
async function collectTopCoins() {
  console.log(`[Collector] Iniciando coleta de mercado CoinGecko (v3) às ${new Date().toISOString()}...`);
  const snapshotTime = new Date().toISOString();
  const totalTarget = config.collector.totalCoins;
  const perPage = config.collector.perPage;
  const pagesCount = Math.ceil(totalTarget / perPage);

  // Carregar moedas conhecidas para determinar first_seen_at
  const knownCoins = await db.getAllKnownCoins();
  const nowMs = Date.now();

  let rawCoins = [];

  for (let page = 1; page <= pagesCount; page++) {
    console.log(`[Collector] Buscando página ${page}/${pagesCount}...`);
    const pageData = await fetchMarketsPage(page, perPage);
    if (pageData && Array.isArray(pageData)) {
      rawCoins = rawCoins.concat(pageData);
    }
    if (page < pagesCount) {
      await sleep(config.collector.requestDelayMs);
    }
  }

  console.log(`[Collector] Total de moedas brutas obtidas: ${rawCoins.length}`);

  const filteredCoins = [];
  const snapshots = [];
  const coinsMeta = [];

  for (const item of rawCoins) {
    if (!item || !item.id || !item.symbol) continue;

    if (isStablecoin(item)) continue;

    const marketCap = parseFloat(item.market_cap) || 0;
    const volume24h = parseFloat(item.total_volume) || 0;
    const priceUsd = parseFloat(item.current_price) || 0;

    if (marketCap < config.filters.minMarketCapUsd && marketCap > 0) continue;
    if (volume24h < config.filters.minVolume24hUsd) continue;
    if (priceUsd <= 0) continue;

    const circulatingSupply = parseFloat(item.circulating_supply) || null;
    const totalSupply = parseFloat(item.total_supply) || null;
    const maxSupply = parseFloat(item.max_supply) || null;

    let fdv = parseFloat(item.fully_diluted_valuation) || null;
    if (!fdv && priceUsd > 0) {
      const targetSupply = maxSupply || totalSupply;
      if (targetSupply && targetSupply > 0) {
        fdv = priceUsd * targetSupply;
      } else if (marketCap > 0) {
        fdv = marketCap;
      }
    }

    const p1h = parseFloat(item.price_change_percentage_1h_in_currency) || 0;
    const p24h = parseFloat(item.price_change_percentage_24h_in_currency || item.price_change_percentage_24h) || 0;
    const p7d = parseFloat(item.price_change_percentage_7d_in_currency) || 0;
    const p30d = parseFloat(item.price_change_percentage_30d_in_currency) || 0;

    const ath = parseFloat(item.ath) || null;
    const athChangePct = parseFloat(item.ath_change_percentage) || null;
    const athDate = item.ath_date || null;

    // Cálculo de idade do token (Adendo v3)
    let ageDays = null;
    let ageSource = 'estimated';
    let firstSeenAt = snapshotTime;
    let genesisDate = item.genesis_date || null;

    if (genesisDate) {
      ageDays = Math.max(1, Math.floor((nowMs - new Date(genesisDate).getTime()) / (1000 * 60 * 60 * 24)));
      ageSource = 'confirmed';
    } else {
      const existing = knownCoins[item.id];
      if (existing && existing.first_seen_at) {
        firstSeenAt = existing.first_seen_at;
        ageDays = Math.max(1, Math.floor((nowMs - new Date(firstSeenAt).getTime()) / (1000 * 60 * 60 * 24)));
      } else if (item.atl_date) {
        // Se temos a data de ATL ou ATH antiga, usamos como piso de idade
        const refDate = item.atl_date || item.ath_date;
        if (refDate) {
          ageDays = Math.max(1, Math.floor((nowMs - new Date(refDate).getTime()) / (1000 * 60 * 60 * 24)));
        } else {
          ageDays = 45; // default fase de descoberta se novo no monitor
        }
      } else {
        ageDays = 45;
      }
    }

    const sparklinePrices = Array.isArray(item.sparkline_in_7d?.price) 
      ? item.sparkline_in_7d.price.filter(p => p != null && !isNaN(p) && p > 0)
      : [];

    const coinData = {
      id: item.id,
      symbol: item.symbol.toLowerCase(),
      name: item.name,
      image_url: item.image,
      genesis_date: genesisDate,
      first_seen_at: firstSeenAt,
      age_days: ageDays,
      age_source: ageSource,
    };

    const snapshotData = {
      coin_id: item.id,
      price_usd: priceUsd,
      market_cap: marketCap,
      fdv: fdv,
      volume_24h: volume24h,
      circulating_supply: circulatingSupply,
      total_supply: totalSupply,
      max_supply: maxSupply,
      market_cap_rank: parseInt(item.market_cap_rank, 10) || null,
      price_change_1h: p1h,
      price_change_24h: p24h,
      price_change_7d: p7d,
      price_change_30d: p30d,
      high_24h: parseFloat(item.high_24h) || null,
      low_24h: parseFloat(item.low_24h) || null,
      ath: ath,
      ath_change_percentage: athChangePct,
      ath_date: athDate,
      snapshot_time: snapshotTime,
      sparkline_prices: sparklinePrices,
    };

    filteredCoins.push({ meta: coinData, snapshot: snapshotData, raw: item });
    coinsMeta.push(coinData);
    snapshots.push(snapshotData);
  }

  console.log(`[Collector] Moedas processadas e validadas: ${filteredCoins.length}`);

  await db.upsertCoins(coinsMeta);
  await db.insertSnapshots(snapshots.map(({ sparkline_prices, ...s }) => s));

  return {
    snapshotTime,
    coins: filteredCoins,
    totalCollected: rawCoins.length,
    totalValid: filteredCoins.length,
  };
}

module.exports = {
  collectTopCoins,
  isStablecoin,
};
