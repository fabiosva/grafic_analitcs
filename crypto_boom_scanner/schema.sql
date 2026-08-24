-- ==============================================================================
-- CRYPTO BOOM SCANNER (v3) - SUPABASE / POSTGRESQL SCHEMA
-- ==============================================================================

-- 1. Metadata de Moedas (com idade e ATH)
CREATE TABLE IF NOT EXISTS coins (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    image_url TEXT,
    genesis_date DATE,
    first_seen_at TIMESTAMPTZ DEFAULT now(),
    age_days INT,
    age_source TEXT DEFAULT 'estimated', -- 'confirmed' | 'estimated'
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Snapshots Históricos das Moedas (Coletados a cada hora)
CREATE TABLE IF NOT EXISTS coin_snapshots (
    id BIGSERIAL PRIMARY KEY,
    coin_id TEXT REFERENCES coins(id) ON DELETE CASCADE,
    price_usd NUMERIC,
    market_cap NUMERIC,
    fdv NUMERIC,
    volume_24h NUMERIC,
    circulating_supply NUMERIC,
    total_supply NUMERIC,
    max_supply NUMERIC,
    market_cap_rank INT,
    price_change_1h NUMERIC,
    price_change_24h NUMERIC,
    price_change_7d NUMERIC,
    price_change_30d NUMERIC,
    high_24h NUMERIC,
    low_24h NUMERIC,
    ath NUMERIC,
    ath_change_percentage NUMERIC,
    ath_date TIMESTAMPTZ,
    snapshot_time TIMESTAMPTZ DEFAULT now(),
    UNIQUE(coin_id, snapshot_time)
);

-- 3. Scores de Oportunidade e Risco por Moeda
CREATE TABLE IF NOT EXISTS coin_scores (
    id BIGSERIAL PRIMARY KEY,
    coin_id TEXT REFERENCES coins(id) ON DELETE CASCADE,
    opportunity_score NUMERIC NOT NULL,
    risk_score NUMERIC NOT NULL,
    final_score NUMERIC NOT NULL,
    signal_category TEXT NOT NULL, -- 'BOOM_WATCH', 'MOMENTUM', 'ACCUMULATION', 'HIGH_RISK', 'EXTENDED', 'NEUTRAL'
    delta_6h NUMERIC,
    delta_12h NUMERIC,
    delta_24h NUMERIC,
    components JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 4. Recomendações Automáticas & Vereditos do Sistema (v3)
CREATE TABLE IF NOT EXISTS recommendations (
    id BIGSERIAL PRIMARY KEY,
    coin_id TEXT REFERENCES coins(id) ON DELETE CASCADE,
    verdict TEXT NOT NULL, -- 'STRONG_WATCH', 'WATCH', 'TOO_EXTENDED', 'AVOID'
    confidence NUMERIC NOT NULL, -- 0 a 100
    reasoning JSONB NOT NULL, -- Array de strings em português
    risk_flags JSONB NOT NULL, -- Array de strings com alertas
    price_at_recommendation NUMERIC NOT NULL,
    opportunity_score NUMERIC,
    risk_score NUMERIC,
    final_score NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 5. Eventos Notáveis (Cruzar Thresholds, Entrada no Top 10)
CREATE TABLE IF NOT EXISTS score_events (
    id BIGSERIAL PRIMARY KEY,
    coin_id TEXT REFERENCES coins(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL, -- 'top10_enter', 'threshold_cross', 'boom_watch_trigger', 'strong_watch_trigger'
    score NUMERIC,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 6. Histórico de Alertas Disparados (Telegram / Webhooks)
CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    coin_id TEXT REFERENCES coins(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    message TEXT NOT NULL,
    sent_at TIMESTAMPTZ DEFAULT now(),
    notified BOOLEAN DEFAULT true,
    channel TEXT DEFAULT 'telegram'
);

-- 7. Resultados de Backtesting
CREATE TABLE IF NOT EXISTS backtest_results (
    id BIGSERIAL PRIMARY KEY,
    min_score INT NOT NULL,
    sample_size INT NOT NULL,
    win_rate_7d NUMERIC,
    avg_return_7d NUMERIC,
    median_return_7d NUMERIC,
    win_rate_14d NUMERIC,
    avg_return_14d NUMERIC,
    median_return_14d NUMERIC,
    win_rate_30d NUMERIC,
    avg_return_30d NUMERIC,
    median_return_30d NUMERIC,
    max_gain NUMERIC,
    max_drawdown NUMERIC,
    calculated_at TIMESTAMPTZ DEFAULT now()
);

-- Índices de Alta Performance
CREATE INDEX IF NOT EXISTS idx_snapshots_coin_time ON coin_snapshots(coin_id, snapshot_time DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_time ON coin_snapshots(snapshot_time DESC);
CREATE INDEX IF NOT EXISTS idx_coin_scores_coin_created ON coin_scores(coin_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_coin_scores_created ON coin_scores(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_coin_scores_final ON coin_scores(final_score DESC);
CREATE INDEX IF NOT EXISTS idx_recommendations_created ON recommendations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_recommendations_coin ON recommendations(coin_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_score_events_created ON score_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_coin_sent ON alerts(coin_id, sent_at DESC);

-- RLS & Políticas
ALTER TABLE coins ENABLE ROW LEVEL SECURITY;
ALTER TABLE coin_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE coin_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE score_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE backtest_results ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Public select coins') THEN
        CREATE POLICY "Public select coins" ON coins FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service write coins') THEN
        CREATE POLICY "Service write coins" ON coins FOR ALL USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Public select snapshots') THEN
        CREATE POLICY "Public select snapshots" ON coin_snapshots FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service write snapshots') THEN
        CREATE POLICY "Service write snapshots" ON coin_snapshots FOR ALL USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Public select scores') THEN
        CREATE POLICY "Public select scores" ON coin_scores FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service write scores') THEN
        CREATE POLICY "Service write scores" ON coin_scores FOR ALL USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Public select recommendations') THEN
        CREATE POLICY "Public select recommendations" ON recommendations FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service write recommendations') THEN
        CREATE POLICY "Service write recommendations" ON recommendations FOR ALL USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Public select events') THEN
        CREATE POLICY "Public select events" ON score_events FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service write events') THEN
        CREATE POLICY "Service write events" ON score_events FOR ALL USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Public select alerts') THEN
        CREATE POLICY "Public select alerts" ON alerts FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service write alerts') THEN
        CREATE POLICY "Service write alerts" ON alerts FOR ALL USING (true) WITH CHECK (true);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Public select backtests') THEN
        CREATE POLICY "Public select backtests" ON backtest_results FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Service write backtests') THEN
        CREATE POLICY "Service write backtests" ON backtest_results FOR ALL USING (true) WITH CHECK (true);
    END IF;
END $$;
