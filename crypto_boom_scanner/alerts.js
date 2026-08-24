const axios = require('axios');
const config = require('./config');
const db = require('./db');

async function sendTelegramMessage(text) {
  const token = config.alerts.telegramBotToken;
  const chatId = config.alerts.telegramChatId;

  if (!token || !chatId) {
    // Modo silencioso se telegram não estiver configurado
    return false;
  }

  try {
    const url = `https://api.telegram.org/bot${token}/sendMessage`;
    await axios.post(url, {
      chat_id: chatId,
      text: text,
      parse_mode: 'HTML',
      disable_web_page_preview: true,
    }, { timeout: 10000 });
    return true;
  } catch (err) {
    console.error('[Alerts] Falha ao enviar Telegram:', err.message);
    return false;
  }
}

/**
 * Processa a lista de scores do ciclo e dispara alertas se aplicável
 */
async function processAlerts(scoresWithMeta, previousTop10CoinIds = []) {
  if (!scoresWithMeta || scoresWithMeta.length === 0) return [];

  const recentAlerts = await db.getRecentAlerts(200);
  const cooldownMs = config.alerts.cooldownHours * 60 * 60 * 1000;
  const nowMs = Date.now();

  const dispatchedAlerts = [];
  const currentTop10 = scoresWithMeta.slice(0, 10).map(s => s.coin_id);

  for (let rank = 0; rank < scoresWithMeta.length; rank++) {
    const item = scoresWithMeta[rank];
    const coinId = item.coin_id;
    const symbol = (item.symbol || item.coin_id).toUpperCase();
    const name = item.name || symbol;
    const finalScore = item.final_score;
    const oppScore = item.opportunity_score;
    const riskScore = item.risk_score;
    const signal = item.signal_category;
    const price = item.components?.priceUsd ? `$${item.components.priceUsd.toLocaleString()}` : '';
    const p24h = item.components?.priceChange24h ? `${item.components.priceChange24h > 0 ? '+' : ''}${item.components.priceChange24h.toFixed(2)}%` : '';
    const volAccel = item.components?.volumeAccelVs7d ? `${item.components.volumeAccelVs7d}x` : '';

    // Verificar se já enviamos alerta recente para essa moeda
    const lastAlert = recentAlerts.find(a => a.coin_id === coinId);
    const inCooldown = lastAlert && (nowMs - new Date(lastAlert.sent_at).getTime() < cooldownMs);

    let shouldAlert = false;
    let alertType = '';
    let messageTitle = '';

    // 1. Condição BOOM WATCH
    if (signal === 'BOOM_WATCH') {
      shouldAlert = true;
      alertType = 'boom_watch';
      messageTitle = `🚀 <b>[BOOM WATCH] ${symbol} (${name})</b>`;
    }
    // 2. Condição ACCUMULATION
    else if (signal === 'ACCUMULATION') {
      shouldAlert = true;
      alertType = 'accumulation';
      messageTitle = `🐋 <b>[ACUMULAÇÃO DETECTADA] ${symbol} (${name})</b>`;
    }
    // 3. Cruzamento de Threshold (ex: Score >= 80)
    else if (finalScore >= config.alerts.alertThresholdScore) {
      shouldAlert = true;
      alertType = 'threshold_cross';
      messageTitle = `🔥 <b>[ALTO SCORE DETECTADO] ${symbol} (${name})</b>`;
    }
    // 4. Entrada no Top 10
    else if (rank < 10 && previousTop10CoinIds.length > 0 && !previousTop10CoinIds.includes(coinId)) {
      shouldAlert = true;
      alertType = 'top10_enter';
      messageTitle = `⭐ <b>[NOVO NO TOP 10] ${symbol} (${name})</b>`;
      await db.insertEvent({
        coin_id: coinId,
        event_type: 'top10_enter',
        score: finalScore,
        details: { rank: rank + 1, oppScore, riskScore },
      });
    }

    if (shouldAlert && !inCooldown) {
      const message = [
        messageTitle,
        `📊 <b>Final Score:</b> ${finalScore}/100`,
        `🎯 <b>Opportunity:</b> ${oppScore} | 🛡️ <b>Risco:</b> ${riskScore}`,
        `💰 <b>Preço:</b> ${price} (${p24h} 24h)`,
        `⚡ <b>Vol Accel 7d:</b> ${volAccel} | 📈 <b>RSI:</b> ${item.components?.rsi || 'N/A'}`,
        item.delta_24h ? `🔄 <b>Delta 24h:</b> ${item.delta_24h > 0 ? '+' : ''}${item.delta_24h} pts` : '',
        `🔗 <a href="https://www.coingecko.com/en/coins/${coinId}">Ver no CoinGecko</a>`,
      ].filter(Boolean).join('\n');

      console.log(`[Alerts] Disparando alerta para ${symbol} (${alertType})...`);
      const sent = await sendTelegramMessage(message);

      const alertRecord = {
        coin_id: coinId,
        type: alertType,
        message: message,
        sent_at: new Date().toISOString(),
        notified: sent,
        channel: 'telegram',
      };

      await db.insertAlert(alertRecord);
      dispatchedAlerts.push(alertRecord);
    }
  }

  return {
    dispatchedAlerts,
    currentTop10,
  };
}

module.exports = {
  sendTelegramMessage,
  processAlerts,
};
