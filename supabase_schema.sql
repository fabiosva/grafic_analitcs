create table if not exists bottom_indicators (
    data date primary key,
    preco numeric,
    mvrv_zscore numeric,
    nupl numeric,
    sopr numeric,
    realized_price numeric,
    puell_multiple numeric,
    reserve_risk numeric,
    rhodl_ratio numeric,
    fear_greed integer,
    rsi numeric,
    sma50 numeric,
    sma200 numeric,
    stoch_rsi_k numeric,
    stoch_rsi_d numeric,
    cvdd numeric,
    balanced_price numeric,
    terminal_price numeric,
    lth_realized_price numeric,
    hashribbons text,
    gm_sma350 numeric,
    gm_x16 numeric,
    gm_x2 numeric,
    gm_x2618 numeric,
    open_interest_usd numeric,
    funding_rate numeric,
    sth_mvrv numeric,
    sth_mvrv_momentum numeric,
    vdd_multiple numeric,
    aviv numeric,
    sth_lth_ratio numeric,
    sth_realized_price numeric,
    ultimo_halving date,
    dias_desde_halving integer,
    fundo_estimado date,
    janela_estimada_inicio date,
    janela_estimada_fim date,
    dias_ate_fundo_estimado integer,
    condicoes jsonb,
    obrigatorias_ativas integer,
    score_final numeric,
    classificacao text,
    atualizado_em timestamptz
);

alter table bottom_indicators enable row level security;
create policy "Leitura publica" on bottom_indicators for select using (true);
create policy "Insercao via service key" on bottom_indicators for insert with check (true);
create policy "Update via service key" on bottom_indicators for update using (true);

-- Placar de acertos: um palpite por (dia em que foi feito, prazo em dias).
-- Gravado no dia da previsao com preco_real/etc nulos; preenchido depois,
-- quando data_alvo chega, pelo proprio coletor.
create table if not exists previsoes (
    data_previsao date not null,
    prazo_dias integer not null,
    data_alvo date not null,
    direcao_prevista text,
    prob_alta numeric,
    preco_no_dia numeric,
    preco_alvo_estimado numeric,
    n_amostras integer,
    preco_real numeric,
    direcao_correta boolean,
    alvo_batido boolean,
    variacao_real_pct numeric,
    avaliado_em timestamptz,
    criado_em timestamptz,
    primary key (data_previsao, prazo_dias)
);

alter table previsoes enable row level security;
create policy "Leitura publica previsoes" on previsoes for select using (true);
create policy "Insercao previsoes" on previsoes for insert with check (true);
create policy "Update previsoes" on previsoes for update using (true);
