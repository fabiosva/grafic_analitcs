"""
Módulo da aba Crypto Boom Scanner (v2) para o Streamlit
Filtros avançados estilo CoinMarketCap: Market Cap, Volume, Supply Circulante, RSI, Sinais e Cotações em Tempo Real
"""
from pathlib import Path
import json
import subprocess
import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
LOCAL_SCORES_FILE = ROOT / "crypto_boom_scanner" / "data" / "scores.json"
LOCAL_COINS_FILE = ROOT / "crypto_boom_scanner" / "data" / "coins.json"
LOCAL_BACKTEST_FILE = ROOT / "crypto_boom_scanner" / "data" / "backtest.json"


@st.cache_data(ttl=60)
def load_scanner_scores(supabase_url, supabase_key):
    """Carrega os scores do Supabase ou histórico local"""
    if supabase_url and supabase_key:
        headers = {"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}
        try:
            url = f"{supabase_url}/rest/v1/coin_scores?select=*,coins(id,symbol,name,image_url)&order=created_at.desc&limit=1000"
            res = requests.get(url, headers=headers, timeout=12)
            if res.status_code == 200 and res.json():
                data = res.json()
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
    """Renderiza a interface com filtros estilo CoinMarketCap e scanner em tempo real"""
    
    # Cabeçalho e Botão de Atualização em Tempo Real
    h_col1, h_col2 = st.columns([3, 1])
    with h_col1:
        st.markdown("""
        <div style="margin-bottom:10px;">
            <span style="color:#10b981; font-weight:800; font-size:0.75rem; letter-spacing:0.1em; text-transform:uppercase;">● TRIAGEM ESTATÍSTICA DE ALTCOINS</span>
            <h2 style="margin:2px 0; color:#fff; font-size:1.8rem; font-weight:800;">🚀 Crypto Boom Scanner & Screener</h2>
            <p style="color:#94a3b8; margin:0; font-size:0.85rem;">Screener completo estilo CoinMarketCap com cálculo de Momentum, Volume, Breakout e Desconto de Risco.</p>
        </div>
        """, unsafe_allow_html=True)
    with h_col2:
        if st.button("🔄 Atualizar Cotações Agora", use_container_width=True, help="Executa uma varredura em tempo real na CoinGecko"):
            with st.spinner("Buscando preços e calculando indicadores..."):
                try:
                    subprocess.run(["node", str(ROOT / "crypto_boom_scanner" / "scheduler.js"), "--now"], check=True, timeout=30)
                    st.cache_data.clear()
                    st.success("Atualizado com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao disparar coleta: {e}")

    df_scores, source = load_scanner_scores(supabase_url, supabase_key)

    if df_scores.empty:
        st.warning("⚠️ Nenhum dado de mercado encontrado. Clique em 'Atualizar Cotações Agora' acima.")
        return

    # Extrair e normalizar campos dos componentes
    for idx, row in df_scores.iterrows():
        comp = row.get("components") or {}
        if isinstance(comp, dict):
            df_scores.at[idx, "price_usd"] = comp.get("priceUsd", 0)
            df_scores.at[idx, "price_change_24h"] = comp.get("priceChange24h", 0)
            df_scores.at[idx, "price_change_7d"] = comp.get("priceChange7d", 0)
            df_scores.at[idx, "market_cap"] = comp.get("marketCap", 0)
            df_scores.at[idx, "volume_24h"] = comp.get("volume24h", 0)
            df_scores.at[idx, "circulating_supply"] = comp.get("circulatingSupply")
            df_scores.at[idx, "total_supply"] = comp.get("totalSupply")
            df_scores.at[idx, "max_supply"] = comp.get("maxSupply")
            df_scores.at[idx, "vol_accel"] = comp.get("volumeAccelVs7d")
            df_scores.at[idx, "rsi"] = comp.get("rsi")
            
            risk_comp = comp.get("riskComponents") or {}
            df_scores.at[idx, "fdv_ratio"] = risk_comp.get("fdvRatio", 1.0)
            df_scores.at[idx, "float_pct"] = risk_comp.get("floatPct", 100.0)
            df_scores.at[idx, "is_breakout"] = comp.get("isBreakout", False)

    # Top Cards
    boom_count = len(df_scores[df_scores["signal_category"] == "BOOM_WATCH"])
    accum_count = len(df_scores[df_scores["signal_category"] == "ACCUMULATION"])
    mom_count = len(df_scores[df_scores["signal_category"] == "MOMENTUM"])
    top_score = df_scores.iloc[0]["final_score"] if not df_scores.empty else 0
    top_symbol = df_scores.iloc[0]["symbol"] if not df_scores.empty else "--"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🚀 Boom Watch", f"{boom_count}", "Confluência técnica forte")
    c2.metric("🐋 Acumulação", f"{accum_count}", "Volume subindo + Preço calmo")
    c3.metric("🔥 Momentum", f"{mom_count}", "Preço e volume acelerados")
    c4.metric("⭐ Score Líder", f"{top_score}/100", f"{top_symbol}")

    st.markdown("<hr style='border-color:#1f2d47; margin:16px 0;'>", unsafe_allow_html=True)

    # ==========================================
    # FILTROS ESTILO COINMARKETCAP
    # ==========================================
    with st.expander("🛠️ Filtros de Mercado Avançados (Market Cap, Volume, Supply, RSI, Variação)", expanded=True):
        f_row1_col1, f_row1_col2, f_row1_col3 = st.columns([1.5, 1.5, 1])
        with f_row1_col1:
            categoria_filtro = st.selectbox(
                "Categoria de Sinal:",
                ["Todas", "🚀 BOOM_WATCH", "🐋 ACCUMULATION", "🔥 MOMENTUM", "⚠️ HIGH_RISK", "⚠️ EXTENDED", "NEUTRAL"],
            )
        with f_row1_col2:
            preset_mcap = st.selectbox(
                "Faixa de Market Cap:",
                [
                    "Todos os Tamanhos",
                    "Micro Cap (< $50M)",
                    "Small Cap ($50M - $300M)",
                    "Mid Cap ($300M - $2B)",
                    "Large Cap (> $2B)",
                ]
            )
        with f_row1_col3:
            busca_termo = st.text_input("🔍 Buscar Ativo:", placeholder="Ex: NPC, SOL, DOG...")

        f_row2_col1, f_row2_col2, f_row2_col3, f_row2_col4 = st.columns(4)
        with f_row2_col1:
            min_vol = st.number_input("Volume 24h Mínimo ($)", min_value=0, value=50000, step=50000)
        with f_row2_col2:
            min_p24h = st.slider("Variação 24h Mínima (%)", min_value=-30.0, max_value=100.0, value=-30.0, step=1.0)
        with f_row2_col3:
            max_risk = st.slider("Risco Máximo Permitido (0-100)", min_value=0, max_value=100, value=100, step=5)
        with f_row2_col4:
            min_float = st.slider("Supply Circulante Mínimo (%)", min_value=0, max_value=100, value=0, step=5, help="% de moedas já liberadas no mercado")

    # Aplicar filtros
    filtered_df = df_scores.copy()

    if categoria_filtro != "Todas":
        cat_code = categoria_filtro.split(" ")[-1]
        filtered_df = filtered_df[filtered_df["signal_category"] == cat_code]

    if preset_mcap == "Micro Cap (< $50M)":
        filtered_df = filtered_df[filtered_df["market_cap"] < 50_000_000]
    elif preset_mcap == "Small Cap ($50M - $300M)":
        filtered_df = filtered_df[(filtered_df["market_cap"] >= 50_000_000) & (filtered_df["market_cap"] < 300_000_000)]
    elif preset_mcap == "Mid Cap ($300M - $2B)":
        filtered_df = filtered_df[(filtered_df["market_cap"] >= 300_000_000) & (filtered_df["market_cap"] < 2_000_000_000)]
    elif preset_mcap == "Large Cap (> $2B)":
        filtered_df = filtered_df[filtered_df["market_cap"] >= 2_000_000_000]

    if min_vol > 0:
        filtered_df = filtered_df[filtered_df["volume_24h"] >= min_vol]

    filtered_df = filtered_df[filtered_df["price_change_24h"] >= min_p24h]
    filtered_df = filtered_df[filtered_df["risk_score"] <= max_risk]
    
    if min_float > 0:
        filtered_df = filtered_df[filtered_df["float_pct"] >= min_float]

    if busca_termo:
        termo = busca_termo.lower().strip()
        filtered_df = filtered_df[
            filtered_df["symbol"].str.lower().str.contains(termo, na=False) |
            filtered_df["name"].str.lower().str.contains(termo, na=False)
        ]

    # Ordenação decrescente por Final Score
    filtered_df = filtered_df.sort_values("final_score", ascending=False).reset_index(drop=True)

    # Tabela formatada
    st.subheader(f"📋 Screener de Mercado em Tempo Real ({len(filtered_df)} ativos)")

    display_df = pd.DataFrame()
    display_df["# Rank"] = range(1, len(filtered_df) + 1)
    display_df["Ativo"] = filtered_df["symbol"]
    display_df["Nome"] = filtered_df["name"]
    display_df["Final Score"] = filtered_df["final_score"].apply(lambda x: f"{x:.1f}")
    display_df["Opportunity"] = filtered_df["opportunity_score"].apply(lambda x: f"{x:.1f}")
    display_df["Risco"] = filtered_df["risk_score"].apply(lambda x: f"{x}")
    display_df["Sinal"] = filtered_df["signal_category"]
    display_df["Preço (USD)"] = filtered_df["price_usd"].apply(lambda x: f"${x:,.4f}" if x < 1 else f"${x:,.2f}")
    display_df["24h %"] = filtered_df["price_change_24h"].apply(lambda x: f"{x:+.2f}%")
    display_df["7d %"] = filtered_df["price_change_7d"].apply(lambda x: f"{x:+.2f}%")
    display_df["Market Cap"] = filtered_df["market_cap"].apply(lambda x: f"${x:,.0f}" if x > 0 else "N/A")
    display_df["Volume 24h"] = filtered_df["volume_24h"].apply(lambda x: f"${x:,.0f}")
    display_df["RSI (14)"] = filtered_df["rsi"].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    display_df["Vol Accel 7d"] = filtered_df["vol_accel"].apply(lambda x: f"{x:.2f}x" if pd.notna(x) else "N/A")
    display_df["FDV / MCap"] = filtered_df["fdv_ratio"].apply(lambda x: f"{x:.2f}x" if pd.notna(x) else "N/A")
    display_df["Supply Circulando"] = filtered_df["float_pct"].apply(lambda x: f"{x:.1f}%")
    display_df["Delta 24h"] = filtered_df["delta_24h"].apply(lambda x: f"{x:+.1f}" if pd.notna(x) else "N/A")

    st.dataframe(display_df, use_container_width=True, height=480, hide_index=True)

    # Raio-X Detalhado do Ativo Selecionado
    st.markdown("<hr style='border-color:#1f2d47; margin:25px 0;'>", unsafe_allow_html=True)
    st.subheader("🔍 Raio-X & Estrutura de Mercado")

    coin_options = [f"{row['symbol']} - {row['name']} (Score: {row['final_score']})" for _, row in filtered_df.iterrows()]
    if coin_options:
        selected_option = st.selectbox("Selecione um ativo para analisar em detalhes:", coin_options)
        if selected_option:
            selected_symbol = selected_option.split(" ")[0]
            coin_row = filtered_df[filtered_df["symbol"] == selected_symbol].iloc[0]
            comp = coin_row.get("components") or {}

            d_col1, d_col2, d_col3, d_col4 = st.columns(4)
            d_col1.metric("Final Score", f"{coin_row['final_score']}/100", f"Sinal: {coin_row['signal_category']}")
            d_col2.metric("Opportunity Score", f"{coin_row['opportunity_score']}/100", "Potencial")
            risk_val = coin_row['risk_score']
            penalty_pts = risk_val * 0.5
            d_col3.metric("Risk Score", f"{risk_val}/100", f"-{penalty_pts:.1f} pts descontados")
            d_col4.metric("Preço Atual", f"${coin_row['price_usd']:,.4f}" if coin_row['price_usd'] < 1 else f"${coin_row['price_usd']:,.2f}", f"{coin_row['price_change_24h']:+.2f}% 24h")

            st.markdown("#### Indicadores On-Chain e Técnicos")
            m1, m2, m3, m4 = st.columns(4)
            m1.info(f"**RSI (14)**: {comp.get('rsi') if comp.get('rsi') is not None else 'N/A'}")
            m2.info(f"**Vol Accel vs 7d**: {comp.get('volumeAccelVs7d', 'N/A')}x" if comp.get('volumeAccelVs7d') is not None else "**Vol Accel vs 7d**: N/A (coletando)")
            m3.info(f"**FDV / MCap Ratio**: {comp.get('riskComponents', {}).get('fdvRatio', 1.0)}x")
            m4.info(f"**Supply Circulante**: {comp.get('riskComponents', {}).get('floatPct', 100.0)}%")

            c_sup1, c_sup2, c_sup3 = st.columns(3)
            circ = comp.get('circulatingSupply')
            tot = comp.get('totalSupply')
            max_s = comp.get('maxSupply')
            c_sup1.caption(f"Circulante: {f'{circ:,.0f}' if circ else 'N/A'}")
            c_sup2.caption(f"Total Supply: {f'{tot:,.0f}' if tot else 'N/A'}")
            c_sup3.caption(f"Max Supply: {f'{max_s:,.0f}' if max_s else 'Ilimitado / N/A'}")

    # Backtesting
    with st.expander("📊 Validação Estatística de Sinais (Backtesting)"):
        df_backtest = load_backtest_data(supabase_url, supabase_key)
        if not df_backtest.empty:
            st.dataframe(df_backtest, use_container_width=True)
        else:
            st.info("O histórico de snapshots está sendo construído para apurar win rates e retornos em 7d/14d/30d.")
