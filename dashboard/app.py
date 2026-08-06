"""
Painel Fundo BTC - Dashboard Streamlit
100% gratuito: Streamlit Cloud + Supabase + bitcoin-data.com
"""
import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
import os
import json as _json

st.set_page_config(page_title="Painel Fundo BTC", page_icon="btc", layout="wide")

SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))


@st.cache_data(ttl=3600)
def carregar_historico():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return pd.DataFrame()
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    url = f"{SUPABASE_URL}/rest/v1/bottom_indicators?select=*&order=data.asc"
    r = requests.get(url, headers=headers, timeout=15)
    if r.status_code != 200:
        return pd.DataFrame()
    return pd.DataFrame(r.json())


def cor_score(score):
    if score >= 70:
        return "#00c853"
    elif score >= 40:
        return "#ffd600"
    else:
        return "#ff5252"


def velocimetro(score, classificacao):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title={"text": f"Score de Fundo - {classificacao}", "font": {"size": 20}},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": cor_score(score)},
            "steps": [
                {"range": [0, 40], "color": "#3d1a1a"},
                {"range": [40, 70], "color": "#3d3a1a"},
                {"range": [70, 100], "color": "#1a3d24"},
            ],
        },
    ))
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=60, b=20))
    return fig


def card_indicador(nome, valor, ativo, formato="{:.2f}"):
    cor = "#00c853" if ativo else "#616161"
    valor_fmt = formato.format(valor) if valor is not None else "N/D"
    st.markdown(
        f"""
        <div style="background-color:{cor}22; border-left:4px solid {cor};
                    padding:12px; border-radius:6px; margin-bottom:8px;">
            <div style="font-size:13px; color:#aaa;">{nome}</div>
            <div style="font-size:22px; font-weight:bold;">{valor_fmt}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.title("Painel de Fundo - BTC")
st.caption("Monitoramento pessoal - dados on-chain + tecnicos - 100% gratuito")

df = carregar_historico()

if df.empty:
    st.warning(
        "Sem dados ainda. Rode o workflow do GitHub Actions manualmente uma vez "
        "(Actions -> Coletor Diario BTC -> Run workflow), depois recarregue esta pagina."
    )
    st.stop()

df["data"] = pd.to_datetime(df["data"])
df = df.sort_values("data")
ultimo = df.iloc[-1]

col1, col2 = st.columns([1, 2])

with col1:
    st.plotly_chart(velocimetro(ultimo["score_final"], ultimo["classificacao"]), use_container_width=True)

with col2:
    st.subheader("Condicoes obrigatorias")
    condicoes = ultimo["condicoes"]
    if isinstance(condicoes, str):
        condicoes = _json.loads(condicoes)

    c1, c2 = st.columns(2)
    with c1:
        card_indicador("MVRV Z-Score < 0.3", ultimo["mvrv_zscore"], condicoes.get("mvrv_baixo"))
        card_indicador("Fear & Greed < 25", ultimo["fear_greed"], condicoes.get("medo_extremo"), "{:.0f}")
    with c2:
        card_indicador("RSI diario < 35", ultimo["rsi"], condicoes.get("rsi_sobrevendido"))
        card_indicador("Preco <= Realized Price", ultimo["preco"], condicoes.get("perto_realized_price"), "${:,.0f}")

st.divider()

st.subheader("Indicadores complementares")
b1, b2, b3, b4 = st.columns(4)
b1.metric("NUPL", f"{ultimo['nupl']:.3f}" if pd.notna(ultimo['nupl']) else "N/D")
b2.metric("SOPR", f"{ultimo['sopr']:.3f}" if pd.notna(ultimo['sopr']) else "N/D")
b3.metric("Puell Multiple", f"{ultimo['puell_multiple']:.3f}" if pd.notna(ultimo['puell_multiple']) else "N/D")
b4.metric("Realized Price", f"${ultimo['realized_price']:,.0f}" if pd.notna(ultimo['realized_price']) else "N/D")

st.divider()

st.subheader("Historico - Preco vs Score de Fundo")

fig = go.Figure()
fig.add_trace(go.Scatter(x=df["data"], y=df["preco"], name="Preco BTC", yaxis="y1", line=dict(color="#f7931a")))
fig.add_trace(go.Scatter(x=df["data"], y=df["realized_price"], name="Realized Price", yaxis="y1",
                          line=dict(color="#888", dash="dot")))
fig.add_trace(go.Scatter(x=df["data"], y=df["score_final"], name="Score de Fundo", yaxis="y2",
                          line=dict(color="#00c853")))

fig.update_layout(
    yaxis=dict(title="Preco (USD)", side="left"),
    yaxis2=dict(title="Score (0-100)", side="right", overlaying="y", range=[0, 100]),
    height=450,
    legend=dict(orientation="h", y=1.1),
)
st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("Sua leitura manual do grafico")
st.text_area(
    "Registre padroes que voce identificou (suporte, engolfo, divergencia StochRSI, etc.)",
    placeholder="Ex: possivel fundo, padrao de 46 barras se repetindo...",
    height=100,
)
st.caption("Este campo ainda nao persiste entre sessoes.")

st.divider()
st.caption(f"Ultima atualizacao: {ultimo['atualizado_em']}")
