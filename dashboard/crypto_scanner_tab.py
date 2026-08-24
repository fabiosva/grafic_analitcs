"""
Módulo da aba Crypto Boom Scanner (v2) para o Streamlit
Triagem em tempo real de altcoins: Momentum, Volume, Breakout e Risco
"""
from pathlib import Path
import json
import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
LOCAL_SCORES_FILE = ROOT / "crypto_boom_scanner" / "data" / "scores.json"
LOCAL_COINS_FILE = ROOT / "crypto_boom_scanner" / "data" / "coins.json"
LOCAL_BACKTEST_FILE = ROOT / "crypto_boom_scanner" / "data" / "backtest.json"
LOCAL_ALERTS_FILE = ROOT / "crypto_boom_scanner" / "data" / "alerts.json"


@st.cache_data(ttl=120)
def load_scanner_scores(supabase_url, supabase_key):
    """Carrega os scores mais recentes do Supabase ou fallback local"""
    if supabase_url and supabase_key:
        headers = {"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}
        try:
            url = f"{supabase_url}/rest/v1/coin_scores?select=*,coins(id,symbol,name,image_url)&order=created_at.desc&limit=1000"
            res = requests.get(url, headers=headers, timeout=12)
            if res.status_code == 200 and res.json():
                data = res.json()
                # Deduplicar mantendo o score mais recente por moeda
                seen = set()
                dedup = []
                for item in data:
                    cid = item.get("coin_id")
                    if cid not in seen:
                        seen.add(cid)
                        cinfo = item.get("coins") or {}
                        item["symbol"] = (cinfo.get("symbol") or cid).upper()
                        item["name"] = cinfo.get("name") or item["symbol"]
                        item["image_url"] = cinfo.get("image_url") or ""
                        dedup.append(item)
                return pd.DataFrame(dedup), "Supabase"
        except Exception:
            pass

    # Fallback local
    if LOCAL_SCORES_FILE.exists():
        try:
            scores_data = json.loads(LOCAL_SCORES_FILE.read_text(encoding="utf-8"))
            coins_data = {}
            if LOCAL_COINS_FILE.exists():
                coins_data = json.loads(LOCAL_COINS_FILE.read_text(encoding="utf-8"))

            seen = set()
            dedup = []
            for item in scores_data:
                cid = item.get("coin_id")
                if cid not in seen:
                    seen.add(cid)
                    cinfo = coins_data.get(cid, {})
                    item["symbol"] = (cinfo.get("symbol") or cid).upper()
                    item["name"] = cinfo.get("name") or item["symbol"]
                    item["image_url"] = cinfo.get("image_url") or ""
                    dedup.append(item)
            return pd.DataFrame(dedup), "histórico local"
        except Exception:
            pass

    return pd.DataFrame(), "indisponível"


@st.cache_data(ttl=300)
def load_backtest_data(supabase_url, supabase_key):
    """Carrega resultados do backtest"""
    if supabase_url and supabase_key:
        headers = {"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}
        try:
            url = f"{supabase_url}/rest/v1/backtest_results?select=*&order=calculated_at.desc&limit=10"
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200 and res.json():
                return pd.DataFrame(res.json())
        except Exception:
            pass

    if LOCAL_BACKTEST_FILE.exists():
        try:
            return pd.DataFrame(json.loads(LOCAL_BACKTEST_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return pd.DataFrame()


def render_crypto_scanner_tab(supabase_url, supabase_key):
    """Renderiza a interface do Crypto Boom Scanner dentro do Streamlit"""
    df_scores, source = load_scanner_scores(supabase_url, supabase_key)

    st.markdown("""
    <div style="background:linear-gradient(135deg,#0d1527,#080d1a); padding:20px 24px; border-radius:16px; border:1px solid #1f2d47; margin-bottom:20px;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
            <div>
                <span style="color:#10b981; font-weight:800; font-size:0.75rem; letter-spacing:0.1em; text-transform:uppercase;">● TRIAGEM ESTATÍSTICA DE ALTCOINS</span>
                <h2 style="margin:4px 0 2px 0; color:#fff; font-size:1.8rem; font-weight:800;">🚀 Crypto Boom Scanner</h2>
                <p style="color:#94a3b8; margin:0; font-size:0.85rem;">Identificação pré-pump baseada em Momentum, Injeção de Volume, Breakout e Desconto de Risco.</p>
            </div>
            <div style="text-align:right;">
                <span style="background:#13233c; color:#38bdf8; padding:6px 12px; border-radius:20px; font-size:0.8rem; font-weight:700; border:1px solid #1e3a8a;">
                    Fonte: {source}
                </span>
            </div>
        </div>
    </div>
    """.format(source=source), unsafe_allow_html=True)

    if df_scores.empty:
        st.warning("⚠️ Nenhum score de moedas encontrado. Execute o coletor Node.js (`npm run collect` ou configure o cron).")
        return

    # Extrair campos aninhados de components se necessário
    if "components" in df_scores.columns:
        for idx, row in df_scores.iterrows():
            comp = row.get("components") or {}
            if isinstance(comp, dict):
                df_scores.at[idx, "price_usd"] = comp.get("priceUsd", 0)
                df_scores.at[idx, "price_change_24h"] = comp.get("priceChange24h", 0)
                df_scores.at[idx, "vol_accel"] = comp.get("volumeAccelVs7d", 1.0)
                df_scores.at[idx, "rsi"] = comp.get("rsi")
                risk_comp = comp.get("riskComponents") or {}
                df_scores.at[idx, "fdv_ratio"] = risk_comp.get("fdvRatio", 1.0)
                df_scores.at[idx, "is_breakout"] = comp.get("isBreakout30d", False)

    # Contagens de sinais
    boom_count = len(df_scores[df_scores["signal_category"] == "BOOM_WATCH"])
    accum_count = len(df_scores[df_scores["signal_category"] == "ACCUMULATION"])
    mom_count = len(df_scores[df_scores["signal_category"] == "MOMENTUM"])
    top_score = df_scores.iloc[0]["final_score"] if not df_scores.empty else 0
    top_symbol = df_scores.iloc[0]["symbol"] if not df_scores.empty else "--"

    # Cards de Métricas
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🚀 Boom Watch", f"{boom_count}", help="Breakout técnico + Volume acelerando + Baixo risco")
    with col2:
        st.metric("🐋 Acumulação", f"{accum_count}", help="Volume subindo fortemente com preço calmo")
    with col3:
        st.metric("🔥 Momentum Forte", f"{mom_count}", help="Preço e volume em alta acelerada")
    with col4:
        st.metric("⭐ Score Líder", f"{top_score}/100", f"{top_symbol}")

    st.markdown("<hr style='border-color:#1f2d47; margin:20px 0;'>", unsafe_allow_html=True)

    # Filtros e Busca
    f_col1, f_col2 = st.columns([2, 1])
    with f_col1:
        categoria_filtro = st.radio(
            "Filtrar por Categoria de Sinal:",
            ["Todas", "🚀 BOOM_WATCH", "🐋 ACCUMULATION", "🔥 MOMENTUM", "⚠️ HIGH_RISK", "⚠️ EXTENDED"],
            horizontal=True,
        )
    with f_col2:
        busca_termo = st.text_input("🔍 Buscar Ativo:", placeholder="Ex: SOL, NPC, AAVE...")

    # Aplicar filtros
    filtered_df = df_scores.copy()
    if categoria_filtro != "Todas":
        cat_code = categoria_filtro.split(" ")[-1]
        filtered_df = filtered_df[filtered_df["signal_category"] == cat_code]

    if busca_termo:
        termo = busca_termo.lower().strip()
        filtered_df = filtered_df[
            filtered_df["symbol"].str.lower().str.contains(termo, na=False) |
            filtered_df["name"].str.lower().str.contains(termo, na=False)
        ]

    # Ordenação
    filtered_df = filtered_df.sort_values("final_score", ascending=False).reset_index(drop=True)

    # Tabela Principal
    st.subheader(f"📋 Ranking de Oportunidades ({len(filtered_df)} ativos encontrados)")

    display_cols = []
    col_mapping = {
        "symbol": "Símbolo",
        "name": "Nome",
        "final_score": "Final Score",
        "opportunity_score": "Opportunity",
        "risk_score": "Risco",
        "signal_category": "Sinal",
        "price_usd": "Preço (USD)",
        "price_change_24h": "24h %",
        "vol_accel": "Vol Accel 7d",
        "delta_24h": "Delta 24h",
        "rsi": "RSI (14)",
    }

    avail_cols = [c for c in col_mapping.keys() if c in filtered_df.columns]
    table_df = filtered_df[avail_cols].rename(columns=col_mapping)

    # Formatação amigável
    if "Preço (USD)" in table_df.columns:
        table_df["Preço (USD)"] = table_df["Preço (USD)"].apply(
            lambda x: f"${x:,.4f}" if x < 1 else f"${x:,.2f}" if pd.notna(x) else "$0.00"
        )
    if "24h %" in table_df.columns:
        table_df["24h %"] = table_df["24h %"].apply(lambda x: f"{x:+.2f}%" if pd.notna(x) else "0.00%")
    if "Vol Accel 7d" in table_df.columns:
        table_df["Vol Accel 7d"] = table_df["Vol Accel 7d"].apply(lambda x: f"{x:.2f}x" if pd.notna(x) else "1.0x")
    if "Delta 24h" in table_df.columns:
        table_df["Delta 24h"] = table_df["Delta 24h"].apply(lambda x: f"{x:+.1f}" if pd.notna(x) else "0.0")

    st.dataframe(table_df, use_container_width=True, height=450)

    # Seção de Inspeção Detalhada da Moeda
    st.markdown("<hr style='border-color:#1f2d47; margin:25px 0;'>", unsafe_allow_html=True)
    st.subheader("🔍 Raio-X Detalhado do Ativo")

    coin_options = [f"{row['symbol']} - {row['name']} (Score: {row['final_score']})" for _, row in df_scores.iterrows()]
    selected_option = st.selectbox("Selecione um ativo para analisar:", coin_options)

    if selected_option:
        selected_symbol = selected_option.split(" ")[0]
        coin_row = df_scores[df_scores["symbol"] == selected_symbol].iloc[0]
        comp = coin_row.get("components") or {}

        d_col1, d_col2, d_col3 = st.columns([1, 1, 1])
        with d_col1:
            st.metric("Final Score", f"{coin_row['final_score']}/100", f"Sinal: {coin_row['signal_category']}")
        with d_col2:
            st.metric("Opportunity Score", f"{coin_row['opportunity_score']}/100", "Potencial de Alta")
        with d_col3:
            st.metric("Risk Score", f"{coin_row['risk_score']}/100", "Penalidade aplicada (-50%)")

        st.markdown("#### Métricas Técnicas & Fundamentais")
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.info(f"**RSI (14)**: {comp.get('rsi') if comp.get('rsi') is not None else 'Aquecendo...'}")
        with m2:
            st.info(f"**Vol Accel vs 7d**: {comp.get('volumeAccelVs7d', 1.0)}x")
        with m3:
            fdv_r = comp.get('riskComponents', {}).get('fdvRatio', 1.0)
            st.info(f"**Razão FDV / MCap**: {fdv_r}x")
        with m4:
            breakout_txt = "✅ Sim" if comp.get('isBreakout30d') else "❌ Não"
            st.info(f"**Rompeu Máxima 30d**: {breakout_txt}")

        st.markdown("#### Histórico de Aceleração (Deltas)")
        c_d6, c_d12, c_d24 = st.columns(3)
        c_d6.metric("Delta 6h", f"{coin_row.get('delta_6h', 0):+.1f} pts")
        c_d12.metric("Delta 12h", f"{coin_row.get('delta_12h', 0):+.1f} pts")
        c_d24.metric("Delta 24h", f"{coin_row.get('delta_24h', 0):+.1f} pts")

    # Seção de Backtest Estatístico
    with st.expander("📊 Validação Estatística de Sinais (Backtesting Histórico)"):
        df_backtest = load_backtest_data(supabase_url, supabase_key)
        if not df_backtest.empty:
            st.write("Desempenho histórico de retorno em 7, 14 e 30 dias após cada faixa de score:")
            st.dataframe(df_backtest, use_container_width=True)
        else:
            st.info("Aguardando acúmulo de snapshots horários para cálculo estatístico de retorno (7d/14d/30d).")
