-- ==============================================================================
-- 1. PAINEL FUNDO BTC (ORIGINAL)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS bottom_indicators (
    data DATE PRIMARY KEY,
    preco NUMERIC,
    mvrv_zscore NUMERIC,
    nupl NUMERIC,
    sopr NUMERIC,
    realized_price NUMERIC,
    puell_multiple NUMERIC,
    reserve_risk NUMERIC,
    rhodl_ratio NUMERIC,
    fear_greed INTEGER,
    rsi NUMERIC,
    sma50 NUMERIC,
    sma200 NUMERIC,
    stoch_rsi_k NUMERIC,
    stoch_rsi_d NUMERIC,
    cvdd NUMERIC,
    balanced_price NUMERIC,
    terminal_price NUMERIC,
    lth_realized_price NUMERIC,
    hashribbons TEXT,
    gm_sma350 NUMERIC,
    gm_x16 NUMERIC,
    gm_x2 NUMERIC,
    gm_x2618 NUMERIC,
    open_interest_usd NUMERIC,
    funding_rate NUMERIC,
    sth_mvrv NUMERIC,
    lth_mvrv NUMERIC,
    sth_mvrv_momentum NUMERIC,
    vdd_multiple NUMERIC,
    aviv NUMERIC,
    sth_lth_ratio NUMERIC,
    sth_realized_price NUMERIC,
    percent_lth_in_profit NUMERIC,
    lth_sopr NUMERIC,
    sth_sopr NUMERIC,
    short_term_hodler_supply_btc NUMERIC,
    supply_current NUMERIC,
    supply_in_profit_pct NUMERIC,
    etf_btc_total NUMERIC,
    etf_flow_btc NUMERIC,
    btc_issued NUMERIC,
    thermo_cap NUMERIC,
    ultimo_halving DATE,
    dias_desde_halving INTEGER,
    fundo_estimado DATE,
    janela_estimada_inicio DATE,
    janela_estimada_fim DATE,
    dias_ate_fundo_estimado INTEGER,
    condicoes JSONB,
    obrigatorias_ativas INTEGER,
    score_final NUMERIC,
    classificacao TEXT,
    atualizado_em TIMESTAMPTZ
);

-- Migração idempotente para instalações que já possuem a tabela.
ALTER TABLE bottom_indicators ADD COLUMN IF NOT EXISTS lth_mvrv NUMERIC;
ALTER TABLE bottom_indicators ADD COLUMN IF NOT EXISTS supply_in_profit_pct NUMERIC;
ALTER TABLE bottom_indicators ADD COLUMN IF NOT EXISTS etf_btc_total NUMERIC;
ALTER TABLE bottom_indicators ADD COLUMN IF NOT EXISTS etf_flow_btc NUMERIC;
ALTER TABLE bottom_indicators ADD COLUMN IF NOT EXISTS btc_issued NUMERIC;
ALTER TABLE bottom_indicators ADD COLUMN IF NOT EXISTS thermo_cap NUMERIC;

ALTER TABLE bottom_indicators ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Leitura publica') THEN
        CREATE POLICY "Leitura publica" ON bottom_indicators FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Insercao via service key') THEN
        CREATE POLICY "Insercao via service key" ON bottom_indicators FOR ALL USING (true) WITH CHECK (true);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS previsoes (
    data_previsao DATE NOT NULL,
    prazo_dias INTEGER NOT NULL,
    data_alvo DATE NOT NULL,
    direcao_prevista TEXT,
    prob_alta NUMERIC,
    preco_no_dia NUMERIC,
    preco_alvo_estimado NUMERIC,
    n_amostras INTEGER,
    preco_real NUMERIC,
    direcao_correta BOOLEAN,
    alvo_batido BOOLEAN,
    variacao_real_pct NUMERIC,
    avaliado_em TIMESTAMPTZ,
    criado_em TIMESTAMPTZ,
    PRIMARY KEY (data_previsao, prazo_dias)
);

ALTER TABLE previsoes ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Leitura publica previsoes') THEN
        CREATE POLICY "Leitura publica previsoes" ON previsoes FOR SELECT USING (true);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'Insercao previsoes') THEN
        CREATE POLICY "Insercao previsoes" ON previsoes FOR ALL USING (true) WITH CHECK (true);
    END IF;
END $$;

-- ==============================================================================
-- 2. CRYPTO BOOM SCANNER (v3)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS coins (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    image_url TEXT,
    genesis_date DATE,
    first_seen_at TIMESTAMPTZ DEFAULT now(),
    age_days INT,
    age_source TEXT DEFAULT 'estimated',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

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

CREATE TABLE IF NOT EXISTS coin_scores (
    id BIGSERIAL PRIMARY KEY,
    coin_id TEXT REFERENCES coins(id) ON DELETE CASCADE,
    opportunity_score NUMERIC NOT NULL,
    risk_score NUMERIC NOT NULL,
    final_score NUMERIC NOT NULL,
    signal_category TEXT NOT NULL,
    delta_6h NUMERIC,
    delta_12h NUMERIC,
    delta_24h NUMERIC,
    components JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recommendations (
    id BIGSERIAL PRIMARY KEY,
    coin_id TEXT REFERENCES coins(id) ON DELETE CASCADE,
    verdict TEXT NOT NULL, -- 'STRONG_WATCH', 'WATCH', 'TOO_EXTENDED', 'AVOID'
    confidence NUMERIC NOT NULL,
    reasoning JSONB NOT NULL,
    risk_flags JSONB NOT NULL,
    price_at_recommendation NUMERIC NOT NULL,
    opportunity_score NUMERIC,
    risk_score NUMERIC,
    final_score NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS score_events (
    id BIGSERIAL PRIMARY KEY,
    coin_id TEXT REFERENCES coins(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    score NUMERIC,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    coin_id TEXT REFERENCES coins(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    message TEXT NOT NULL,
    sent_at TIMESTAMPTZ DEFAULT now(),
    notified BOOLEAN DEFAULT true,
    channel TEXT DEFAULT 'telegram'
);

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

-- Políticas RLS
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
