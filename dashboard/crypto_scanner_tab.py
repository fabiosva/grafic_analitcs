"""
Módulo da aba Crypto Boom Scanner (v3) para o Streamlit
Inclui Análise Automática do Mercado, Vereditos do Sistema (STRONG_WATCH),
Filtro de Idade, Dead Weight Risk e Filtros Avançados estilo CoinMarketCap
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
LOCAL_RECS_FILE = ROOT / "crypto_boom_scanner" / "data" / "recommendations.json"
LOCAL_SUMMARY_FILE = ROOT / "crypto_boom_scanner" / "data" / "market_summary.json"
LOCAL_BACKTEST_FILE = ROOT / "crypto_boom_scanner" / "data" / "backtest.json"


@st.cache_data(ttl=60)
def load_scanner_data(supabase_url, supabase_key):
    """Carrega scores e recomendações do Supabase ou histórico local"""
    df_scores = pd.DataFrame()
    recs = []
    summary = None

    if supabase_url and supabase_key:
        headers = {"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}
        try:
            url = f"{supabase_url}/rest/v1/coin_scores?select=*,coins(id,symbol,name,image_url,age_days,age_source)&order=created_at.desc&limit=1000"
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
                        item["age_days"] = cinfo.get("age_days", 60)
                        item["age_source"] = cinfo.get("age_source", "estimated")
                        dedup.append(item)
                df_scores = pd.DataFrame(dedup)
        except Exception:
            pass

        try:
            url_recs = f"{supabase_url}/rest/v1/recommendations?select=*,coins(id,symbol,name,image_url)&order=created_at.desc&limit=10"
            res_r = requests.get(url_recs, headers=headers, timeout=10)
            if res_r.status_code == 200 and res_r.json():
                recs = res_r.json()
        except Exception:
            pass

    if df_scores.empty and LOCAL_SCORES_FILE.exists():
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
                    item["age_days"] = cinfo.get("age_days", 60)
                    item["age_source"] = cinfo.get("age_source", "estimated")
                    dedup.append(item)
            df_scores = pd.DataFrame(dedup)
        except Exception:
            pass

    if not recs and LOCAL_RECS_FILE.exists():
        try:
            recs = json.loads(LOCAL_RECS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    if LOCAL_SUMMARY_FILE.exists():
        try:
            summary = json.loads(LOCAL_SUMMARY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    return df_scores, recs, summary


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
    """Renderiza a interface v3 com Análise de Mercado e Recomendações Automáticas"""

    # Top Header & Botão de Atualização
    h_col1, h_col2 = st.columns([3, 1])
    with h_col1:
        st.markdown("""
        <div style="margin-bottom:12px;">
            <span style="color:#10b981; font-weight:800; font-size:0.75rem; letter-spacing:0.1em; text-transform:uppercase;">● TRIAGEM ESTATÍSTICA & MOTOR DE RECOMENDAÇÃO (v3)</span>
            <h2 style="margin:2px 0; color:#fff; font-size:1.8rem; font-weight:800;">🚀 Crypto Boom Scanner & Screener</h2>
            <p style="color:#94a3b8; margin:0; font-size:0.85rem;">Identificação pré-pump baseada em Momentum, Volume, Breakout, Filtro de Idade e Dead Weight Risk.</p>
        </div>
        """, unsafe_allow_html=True)
    with h_col2:
        if st.button("🔄 Atualizar Cotações Agora", use_container_width=True, help="Executa varredura com sparklines na CoinGecko"):
            with st.spinner("Buscando preços e gerando recomendações..."):
                try:
                    subprocess.run(["node", str(ROOT / "crypto_boom_scanner" / "scheduler.js"), "--now"], check=True, timeout=40)
                    st.cache_data.clear()
                    st.success("Atualizado com sucesso!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao disparar coleta: {e}")

    df_scores, recs, summary = load_scanner_data(supabase_url, supabase_key)

    if df_scores.empty:
        st.warning("⚠️ Nenhum dado de mercado encontrado. Clique em 'Atualizar Cotações Agora' acima.")
        return

    # Extrair e normalizar campos
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
            df_scores.at[idx, "age_days"] = risk_comp.get("ageDays", row.get("age_days", 60))
            df_scores.at[idx, "ath_change_pct"] = risk_comp.get("athChangePct", -50.0)
            df_scores.at[idx, "is_dead_weight"] = risk_comp.get("isDeadWeight", False)
            df_scores.at[idx, "is_breakout"] = comp.get("isBreakout", False)

    # =========================================================================
    # SEÇÃO 1: ANÁLISE AUTOMÁTICA DO MERCADO & TOP RECOMENDAÇÕES (ADENDO v3)
    # =========================================================================
    st.markdown("""
    <div style="background:linear-gradient(135deg,#111e38,#0b1326); padding:18px 22px; border-radius:16px; border:1px solid #1e3a8a; margin-bottom:20px;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
            <div>
                <span style="color:#38bdf8; font-weight:800; font-size:0.75rem; text-transform:uppercase; letter-spacing:0.1em;">🧠 INTELIGÊNCIA DE MERCADO</span>
                <h3 style="margin:2px 0; color:#fff; font-size:1.35rem; font-weight:800;">Análise Automática do Ciclo</h3>
                <p style="color:#cbd5e1; font-size:0.85rem; margin:0;">{summary_text}</p>
            </div>
            <div style="text-align:right;">
                <span style="background:{regime_color}22; color:{regime_color}; padding:8px 16px; border-radius:12px; font-size:0.9rem; font-weight:800; border:1px solid {regime_color}44;">
                    {regime_title}
                </span>
            </div>
        </div>
    </div>
    """.format(
        summary_text=summary.get("summaryText") if summary else "Análise do ciclo gerada pelo motor de regras.",
        regime_title=summary.get("regime") if summary else "MERCADO ATIVO",
        regime_color=summary.get("regimeColor") if summary else "#22c55e",
    ), unsafe_allow_html=True)

    # Cards dos Top 5 Recomendados pelo Motor
    st.markdown("### 🏆 Top 5 Recomendações do Sistema (Buy Signal Engine)")
    top_recs = recs[:5] if recs else []
    
    if top_recs:
        rec_cols = st.columns(min(len(top_recs), 5))
        for idx, r in enumerate(top_recs):
            with rec_cols[idx]:
                verdict = r.get("verdict", "WATCH")
                v_color = "#22c55e" if verdict == "STRONG_WATCH" else ("#38bdf8" if verdict == "WATCH" else ("#f59e0b" if verdict == "TOO_EXTENDED" else "#ef4444"))
                v_badge = "🚀 STRONG WATCH" if verdict == "STRONG_WATCH" else ("👀 WATCH" if verdict == "WATCH" else ("⚠️ ESTENDIDO" if verdict == "TOO_EXTENDED" else "⛔ EVITAR"))
                conf = r.get("confidence", 80)
                price = r.get("price_at_recommendation", 0)
                p_str = f"${price:,.4f}" if price < 1 else f"${price:,.2f}"

                st.markdown(f"""
                <div style="background:#0f172a; padding:14px; border-radius:14px; border:1px solid {v_color}55; min-height:220px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:900; font-size:1.1rem; color:#fff;">{r.get('symbol')}</span>
                        <span style="font-size:0.7rem; font-weight:800; color:{v_color}; background:{v_color}22; padding:3px 8px; border-radius:8px;">{v_badge}</span>
                    </div>
                    <div style="font-size:0.8rem; color:#94a3b8; margin-top:2px;">{r.get('name', '')[:14]}</div>
                    <div style="font-size:1.2rem; font-weight:900; color:#e2e8f0; margin:6px 0 2px 0;">{p_str}</div>
                    <div style="font-size:0.75rem; color:#10b981; font-weight:700;">Score: {r.get('final_score', 0)}/100 · Confiança: {conf}%</div>
                    <hr style="border-color:#1e293b; margin:8px 0;">
                    <div style="font-size:0.72rem; color:#cbd5e1; line-height:1.35;">
                        {'<br>'.join(['• ' + item for item in r.get('reasoning', [])[:2]])}
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("Nenhuma recomendação processada. Clique em 'Atualizar Cotações Agora' para gerar os vereditos.")

    st.markdown("<hr style='border-color:#1f2d47; margin:20px 0;'>", unsafe_allow_html=True)

    # =========================================================================
    # SEÇÃO 2: FILTROS AVANÇADOS ESTILO COINMARKETCAP COM IDADE E ATH
    # =========================================================================
    with st.expander("🛠️ Filtros Avançados (Market Cap, Idade do Token, ATH, Volume, Supply, RSI)", expanded=True):
        f1, f2, f3 = st.columns([1.5, 1.5, 1])
        with f1:
            categoria_filtro = st.selectbox(
                "Filtrar por Categoria de Sinal:",
                ["Todas", "🚀 BOOM_WATCH", "🐋 ACCUMULATION", "🔥 MOMENTUM", "⚠️ HIGH_RISK", "⚠️ EXTENDED", "NEUTRAL"],
            )
        with f2:
            preset_mcap = st.selectbox(
                "Faixa de Market Cap:",
                ["Todos os Tamanhos", "Micro Cap (< $50M)", "Small Cap ($50M - $300M)", "Mid Cap ($300M - $2B)", "Large Cap (> $2B)"]
            )
        with f3:
            busca_termo = st.text_input("🔍 Buscar Ativo:", placeholder="Ex: NPC, POL, DOG...")

        f4, f5, f6, f7 = st.columns(4)
        with f4:
            filtro_idade = st.selectbox(
                "Fase de Idade do Token:",
                ["Qualquer Idade", "🌱 Fase de Descoberta (30 - 180 dias)", "⚡ Novos (< 30 dias)", "🛡️ Menos de 1 ano (< 365d)", "🏛️ Veteranas (> 2 anos)"]
            )
        with f5:
            dist_ath_max = st.slider("Distância Máxima do ATH (%)", min_value=-100.0, max_value=0.0, value=0.0, step=5.0, help="Filtra apenas moedas que estão a no máximo X% de distância do topo histórico")
        with f6:
            min_vol = st.number_input("Volume 24h Mínimo ($)", min_value=0, value=50000, step=50000)
        with f7:
            ocultar_dead_weight = st.checkbox("Ocultar Dead Weight (>2 anos sem ATH)", value=False, help="Remove moedas antigas que caíram > 80% do ATH e possuem forte peso morto de holders presos")

    # Aplicar Filtros
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

    if filtro_idade == "🌱 Fase de Descoberta (30 - 180 dias)":
        filtered_df = filtered_df[(filtered_df["age_days"] >= 30) & (filtered_df["age_days"] <= 180)]
    elif filtro_idade == "⚡ Novos (< 30 dias)":
        filtered_df = filtered_df[filtered_df["age_days"] < 30]
    elif filtro_idade == "🛡️ Menos de 1 ano (< 365d)":
        filtered_df = filtered_df[filtered_df["age_days"] < 365]
    elif filtro_idade == "🏛️ Veteranas (> 2 anos)":
        filtered_df = filtered_df[filtered_df["age_days"] > 730]

    if dist_ath_max < 0:
        filtered_df = filtered_df[filtered_df["ath_change_pct"] >= dist_ath_max]

    if ocultar_dead_weight:
        filtered_df = filtered_df[filtered_df["is_dead_weight"] == False]

    if min_vol > 0:
        filtered_df = filtered_df[filtered_df["volume_24h"] >= min_vol]

    if busca_termo:
        termo = busca_termo.lower().strip()
        filtered_df = filtered_df[
            filtered_df["symbol"].str.lower().str.contains(termo, na=False) |
            filtered_df["name"].str.lower().str.contains(termo, na=False)
        ]

    # Ordenar por Final Score
    filtered_df = filtered_df.sort_values("final_score", ascending=False).reset_index(drop=True)

    # Tabela Formatada
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
    display_df["RSI (14)"] = filtered_df["rsi"].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
    display_df["Vol Accel 7d"] = filtered_df["vol_accel"].apply(lambda x: f"{x:.2f}x" if pd.notna(x) else "N/A")
    display_df["Idade (Dias)"] = filtered_df["age_days"].apply(lambda x: f"~{x}d" if pd.notna(x) else "N/A")
    display_df["Distância ATH"] = filtered_df["ath_change_pct"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A")
    display_df["FDV / MCap"] = filtered_df["fdv_ratio"].apply(lambda x: f"{x:.2f}x" if pd.notna(x) else "N/A")
    display_df["Supply Float"] = filtered_df["float_pct"].apply(lambda x: f"{x:.1f}%")
    display_df["Market Cap"] = filtered_df["market_cap"].apply(lambda x: f"${x:,.0f}" if x > 0 else "N/A")

    st.dataframe(display_df, use_container_width=True, height=480, hide_index=True)

    # Raio-X Detalhado
    st.markdown("<hr style='border-color:#1f2d47; margin:25px 0;'>", unsafe_allow_html=True)
    st.subheader("🔍 Raio-X, Idade Estrutural & Veredito do Ativo")

    coin_options = [f"{row['symbol']} - {row['name']} (Score: {row['final_score']})" for _, row in filtered_df.iterrows()]
    if coin_options:
        selected_option = st.selectbox("Selecione um ativo para analisar em detalhes:", coin_options)
        if selected_option:
            selected_symbol = selected_option.split(" ")[0]
            coin_row = filtered_df[filtered_df["symbol"] == selected_symbol].iloc[0]
            comp = coin_row.get("components") or {}
            risk_comp = comp.get("riskComponents") or {}

            d_col1, d_col2, d_col3, d_col4 = st.columns(4)
            d_col1.metric("Final Score", f"{coin_row['final_score']}/100", f"Sinal: {coin_row['signal_category']}")
            d_col2.metric("Opportunity Score", f"{coin_row['opportunity_score']}/100", "Potencial de Alta")
            risk_val = coin_row['risk_score']
            d_col3.metric("Risk Score", f"{risk_val}/100", f"-{risk_val * 0.5:.1f} pts no score final")
            d_col4.metric("Preço Atual", f"${coin_row['price_usd']:,.4f}" if coin_row['price_usd'] < 1 else f"${coin_row['price_usd']:,.2f}", f"{coin_row['price_change_24h']:+.2f}% 24h")

            st.markdown("#### Métricas Estruturais & Idade")
            m1, m2, m3, m4 = st.columns(4)
            m1.info(f"**RSI (14)**: {comp.get('rsi') if comp.get('rsi') is not None else 'N/A'}")
            m2.info(f"**Idade do Token**: ~{risk_comp.get('ageDays', 60)} dias ({risk_comp.get('ageCategory', 'DISCOVERY')})")
            m3.info(f"**Distância do Topo (ATH)**: {risk_comp.get('athChangePct', -50.0)}%")
            dead_w_str = "⚠️ SIM (+25 risco)" if risk_comp.get('isDeadWeight') else "✅ NÃO (Livre)"
            m4.info(f"**Dead Weight Risk**: {dead_w_str}")

    # Backtesting
    with st.expander("📊 Validação Estatística de Sinais & Recomendações (Backtesting)"):
        df_backtest = load_backtest_data(supabase_url, supabase_key)
        if not df_backtest.empty:
            st.dataframe(df_backtest, use_container_width=True)
        else:
            st.info("O histórico de snapshots está sendo construído para apurar win rates e retornos em 7d/14d/30d.")
