"""
Painel Fundo BTC - Dashboard Streamlit
100% gratuito: Streamlit Cloud + Supabase + bitcoin-data.com
"""
import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import json as _json

st.set_page_config(page_title="Painel Fundo BTC", page_icon="btc", layout="wide")

SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", ""))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))


@st.cache_data(ttl=900)
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
        title={"text": f"Score de Fundo - {classificacao}", "font": {"size": 16}},
        gauge={
            "axis": {"range": [0, 100], "tickfont": {"size": 11}},
            "bar": {"color": cor_score(score)},
            "steps": [
                {"range": [0, 40], "color": "#3d1a1a"},
                {"range": [40, 70], "color": "#3d3a1a"},
                {"range": [70, 100], "color": "#1a3d24"},
            ],
        },
    ))
    fig.update_layout(height=300, margin=dict(l=35, r=35, t=60, b=20), autosize=True)
    return fig


def card_indicador(nome, valor, ativo, formato="{:.2f}"):
    cor = "#00c853" if ativo else "#616161"
    valor_fmt = formato.format(valor) if pd.notna(valor) else "N/D"
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


def ultimo_valido(coluna):
    """Pega o valor mais recente nao-nulo de uma coluna (alguns indicadores atrasam 1 dia na fonte)."""
    serie = df[coluna].dropna()
    return serie.iloc[-1] if not serie.empty else None

col1, col2 = st.columns([1, 2])

with col1:
    score_exibido = ultimo["score_final"] if pd.notna(ultimo["score_final"]) else 0
    classificacao_exibida = ultimo["classificacao"] if pd.notna(ultimo["classificacao"]) else "N/D"
    st.plotly_chart(velocimetro(score_exibido, classificacao_exibida), use_container_width=True)

with col2:
    st.subheader("Condicoes obrigatorias")
    st.caption(
        "Alguns indicadores on-chain tem 1 dia de atraso na fonte - quando isso acontece, "
        "mostramos o ultimo valor conhecido, mas a avaliacao da condicao usa o dado mais recente."
    )
    condicoes = ultimo["condicoes"]
    if isinstance(condicoes, str):
        condicoes = _json.loads(condicoes)

    c1, c2 = st.columns(2)
    with c1:
        card_indicador("MVRV Z-Score < 0.3", ultimo_valido("mvrv_zscore"), condicoes.get("mvrv_baixo"))
        card_indicador("Fear & Greed < 25", ultimo_valido("fear_greed"), condicoes.get("medo_extremo"), "{:.0f}")
    with c2:
        card_indicador("RSI diario < 35", ultimo_valido("rsi"), condicoes.get("rsi_sobrevendido"))
        card_indicador("Preco <= Realized Price", ultimo["preco"], condicoes.get("perto_realized_price"), "${:,.0f}")

st.divider()

st.subheader("Indicadores complementares")
st.caption(
    "Reserve Risk e RHODL Ratio sao 2 dos 9 componentes do indice CBBI "
    "(ColinTalksCrypto Bitcoin Bull Run Index), um dos indices compostos de ciclo "
    "mais usados publicamente."
)
nupl_v = ultimo_valido("nupl")
sopr_v = ultimo_valido("sopr")
puell_v = ultimo_valido("puell_multiple")
realized_v = ultimo_valido("realized_price")
stoch_k = ultimo_valido("stoch_rsi_k")
reserve_risk_v = ultimo_valido("reserve_risk")
rhodl_v = ultimo_valido("rhodl_ratio")

b1, b2, b3, b4 = st.columns(4)
b1.metric("NUPL", f"{nupl_v:.3f}" if nupl_v is not None else "N/D")
b2.metric("SOPR", f"{sopr_v:.3f}" if sopr_v is not None else "N/D")
b3.metric("Puell Multiple", f"{puell_v:.3f}" if puell_v is not None else "N/D")
b4.metric("Realized Price", f"${realized_v:,.0f}" if realized_v is not None else "N/D")

b5, b6, b7 = st.columns(3)
b5.metric("StochRSI %K", f"{stoch_k:.1f}" if stoch_k is not None else "N/D")
b6.metric("Reserve Risk", f"{reserve_risk_v:.5f}" if reserve_risk_v is not None else "N/D")
b7.metric("RHODL Ratio", f"{rhodl_v:,.0f}" if rhodl_v is not None else "N/D")

st.divider()

st.subheader("Ciclo de halving e previsao heuristica")
st.caption(
    "Estimativa baseada no intervalo historico entre cada halving e o fundo ciclico "
    "que se seguiu (2015, 2018, 2022). Isto NAO e recomendacao de investimento - e apenas "
    "um padrao estatistico com poucas amostras, que pode nao se repetir."
)

dias_halving = ultimo_valido("dias_desde_halving")
fundo_est = ultimo_valido("fundo_estimado")
janela_ini = ultimo_valido("janela_estimada_inicio")
janela_fim = ultimo_valido("janela_estimada_fim")
dias_ate = ultimo_valido("dias_ate_fundo_estimado")

h1, h2, h3 = st.columns(3)
h1.metric("Dias desde o ultimo halving", f"{dias_halving:.0f}" if dias_halving is not None else "N/D")
if janela_ini is not None and janela_fim is not None:
    janela_txt = f"{pd.Timestamp(janela_ini):%b/%Y} - {pd.Timestamp(janela_fim):%b/%Y}"
else:
    janela_txt = "N/D"
h2.metric("Janela estimada de fundo", janela_txt)
h3.metric(
    "Dias ate a estimativa central",
    f"{dias_ate:.0f}" if dias_ate is not None else "N/D",
    help=f"Data central estimada: {pd.Timestamp(fundo_est):%d/%m/%Y}" if fundo_est is not None else None,
)

condicoes_ativas_bonus = []
if condicoes.get("mvrv_baixo"):
    condicoes_ativas_bonus.append("MVRV Z-Score baixo")
if condicoes.get("medo_extremo"):
    condicoes_ativas_bonus.append("Medo extremo (F&G)")
if condicoes.get("rsi_sobrevendido"):
    condicoes_ativas_bonus.append("RSI sobrevendido")
if condicoes.get("perto_realized_price"):
    condicoes_ativas_bonus.append("Preco perto do Realized Price")
if stoch_k is not None and stoch_k < 20:
    condicoes_ativas_bonus.append("StochRSI sobrevendido")
if reserve_risk_v is not None and reserve_risk_v < 0.002:
    condicoes_ativas_bonus.append("Reserve Risk baixo")
if rhodl_v is not None and rhodl_v < 1000:
    condicoes_ativas_bonus.append("RHODL Ratio baixo")

if ultimo["obrigatorias_ativas"] == 4:
    st.success(
        "**Fundo estrutural confirmado agora**: as 4 condicoes obrigatorias estao ativas "
        "e o ciclo de halving tambem aponta para esta janela. Sinal forte de confluencia."
    )
elif dias_ate is not None and -60 <= dias_ate <= 60 and condicoes_ativas_bonus:
    st.warning(
        f"Estamos dentro da janela historica de fundo ciclico "
        f"({janela_txt}) e {len(condicoes_ativas_bonus)} indicador(es) ja sinalizam sobrevenda: "
        f"{', '.join(condicoes_ativas_bonus)}. Vale acompanhar de perto, mas ainda nao e "
        "fundo estrutural completo (faltam condicoes obrigatorias)."
    )
elif dias_ate is not None and dias_ate > 60:
    st.info(
        f"Ainda fora da janela historica de fundo ciclico. Com base no padrao dos 3 "
        f"ultimos ciclos, a proxima janela provavel comeca em ~{pd.Timestamp(janela_ini):%b/%Y}."
    )
else:
    st.info(
        "Estamos na janela historica de fundo ciclico, mas nenhum indicador de sobrevenda "
        "esta ativo agora. Sem confluencia suficiente para apontar fundo."
    )

st.divider()

st.subheader("Cruzamento SMA 50/200")
sma_df = df.dropna(subset=["sma50", "sma200"]).tail(30)
if len(sma_df) >= 5:
    gap_atual = sma_df["sma50"].iloc[-1] - sma_df["sma200"].iloc[-1]
    gap_anterior = sma_df["sma50"].iloc[0] - sma_df["sma200"].iloc[0]
    dias_janela = (sma_df["data"].iloc[-1] - sma_df["data"].iloc[0]).days
    variacao_dia = (gap_atual - gap_anterior) / dias_janela if dias_janela else 0

    estado = "SMA50 acima da SMA200 (golden cross ativo)" if gap_atual > 0 else "SMA50 abaixo da SMA200 (death cross ativo)"
    s1, s2, s3 = st.columns(3)
    s1.metric("Estado atual", "Golden cross" if gap_atual > 0 else "Death cross")
    s2.metric("Distancia entre as medias", f"${abs(gap_atual):,.0f}")

    if variacao_dia != 0 and (gap_atual > 0) != (variacao_dia > 0):
        dias_para_cruzar = abs(gap_atual / variacao_dia)
        data_cruzamento = pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=dias_para_cruzar)
        s3.metric("Projecao de cruzamento", f"~{data_cruzamento:%b/%Y}")
        st.caption(
            f"{estado}. Pelo ritmo de convergencia dos ultimos {dias_janela} dias, as medias "
            f"cruzariam em aproximadamente {dias_para_cruzar:.0f} dias "
            f"({data_cruzamento:%d/%m/%Y}) - projecao simples por extrapolacao linear, "
            "nao e garantia de nada."
        )
    else:
        s3.metric("Projecao de cruzamento", "Divergindo")
        st.caption(f"{estado}, e a distancia entre as medias esta aumentando, nao diminuindo.")
else:
    st.caption("Dados insuficientes de SMA50/SMA200 para esta analise.")

st.divider()

st.subheader("Historico - Preco, Score de Fundo e StochRSI")

fig = make_subplots(
    rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3],
    vertical_spacing=0.04, specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
)

fig.add_trace(
    go.Scatter(x=df["data"], y=df["preco"], name="Preco BTC", line=dict(color="#f7931a")),
    row=1, col=1, secondary_y=False,
)
fig.add_trace(
    go.Scatter(x=df["data"], y=df["realized_price"], name="Realized Price",
               line=dict(color="#888", dash="dot")),
    row=1, col=1, secondary_y=False,
)
if "sma200" in df.columns:
    fig.add_trace(
        go.Scatter(x=df["data"], y=df["sma200"], name="SMA 200", line=dict(color="#42a5f5", dash="dash")),
        row=1, col=1, secondary_y=False,
    )
fig.add_trace(
    go.Scatter(x=df["data"], y=df["score_final"], name="Score de Fundo", line=dict(color="#00c853")),
    row=1, col=1, secondary_y=True,
)

if "stoch_rsi_k" in df.columns:
    fig.add_trace(
        go.Scatter(x=df["data"], y=df["stoch_rsi_k"], name="StochRSI %K", line=dict(color="#ab47bc")),
        row=2, col=1,
    )
    fig.add_trace(
        go.Scatter(x=df["data"], y=df["stoch_rsi_d"], name="StochRSI %D", line=dict(color="#ffca28")),
        row=2, col=1,
    )
    fig.add_hline(y=20, line_dash="dot", line_color="#666", row=2, col=1)
    fig.add_hline(y=80, line_dash="dot", line_color="#666", row=2, col=1)

fig.update_yaxes(title_text="Preco (USD)", row=1, col=1, secondary_y=False)
fig.update_yaxes(title_text="Score (0-100)", range=[0, 100], row=1, col=1, secondary_y=True)
fig.update_yaxes(title_text="StochRSI", range=[0, 100], row=2, col=1)
fig.update_layout(height=600, legend=dict(orientation="h", y=1.08))
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
