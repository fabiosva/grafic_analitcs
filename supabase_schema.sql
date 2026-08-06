create table if not exists bottom_indicators (
    data date primary key,
    preco numeric,
    mvrv_zscore numeric,
    nupl numeric,
    sopr numeric,
    realized_price numeric,
    puell_multiple numeric,
    fear_greed integer,
    rsi numeric,
    sma50 numeric,
    sma200 numeric,
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
