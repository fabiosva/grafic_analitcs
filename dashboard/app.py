"""Painel de Fundo do BTC: uma leitura diária, em português simples, de quão perto estamos de um fundo."""
from pathlib import Path
import json
import os

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from analytics import (
    INDICATORS, NEXT_HALVING_ESTIMATE, NEXT_TOP_WINDOW, build_cycle_projection,
    build_signals, latest_value, purchase_readiness, simulate_dca, simulate_exits,
)


st.set_page_config(page_title="Painel de Fundo do BTC", page_icon="₿", layout="wide")
st.markdown("""
<style>
  .stApp { background:#080c14; color:#e5e7eb; }
  .block-container { max-width:1320px; padding-top:1.5rem; }
  .hero { padding:25px 28px; border:1px solid #273449; border-radius:18px; background:linear-gradient(135deg,#111827,#0b1220); }
  .eyebrow { color:#f59e0b; font-size:.75rem; font-weight:800; letter-spacing:.13em; text-transform:uppercase; }
  .hero-grid { display:grid; grid-template-columns:1fr auto; align-items:end; gap:20px; }
  .hero h1 { margin:.45rem 0 .2rem; font-size:2.15rem; }
  .big-score { font-size:3.1rem; line-height:1; font-weight:800; color:#eab308; white-space:nowrap; }
  .muted { color:#94a3b8; }
  .score-track { height:9px; border-radius:9px; margin-top:18px; overflow:hidden; background:linear-gradient(90deg,#7f1d1d 0 35%,#9a3412 35% 55%,#a16207 55% 75%,#166534 75%); }
  .score-marker { width:3px; height:16px; background:#fff; position:relative; top:-3px; box-shadow:0 0 8px #fff; }
  .lens { border:1px solid #273449; background:#101827; border-radius:13px; padding:15px; min-height:126px; }
  .lens-title { font-size:.82rem; color:#94a3b8; }
  .lens-score { font-size:1.65rem; font-weight:800; margin:.25rem 0; }
  .lens-text { color:#cbd5e1; font-size:.84rem; line-height:1.35; }
  .window-card { border:1px solid #1d4ed8; background:linear-gradient(135deg,#111d3b,#0e1729); border-radius:15px; padding:20px; }
  .window-date { font-size:1.65rem; font-weight:800; margin:.35rem 0; }
  .bucket { border:1px solid #273449; border-radius:14px; padding:15px; background:#0f172a; min-height:215px; }
  .bucket h4 { margin:0 0 12px; }
  .indicator-row { display:flex; justify-content:space-between; gap:10px; padding:8px 0; border-bottom:1px solid #202b3d; font-size:.88rem; }
  .indicator-row:last-child { border-bottom:0; }
  .pill { font-weight:800; }
  [data-testid="stMetric"] { border:1px solid #273449; border-radius:12px; background:#101827; padding:12px; }
  @media (max-width:700px) { .hero-grid { grid-template-columns:1fr; } .big-score { font-size:2.4rem; } }
</style>
""", unsafe_allow_html=True)


def get_config(name):
    try:
        return st.secrets.get(name, os.environ.get(name, ""))
    except (FileNotFoundError, KeyError):
        return os.environ.get(name, "")


ROOT = Path(__file__).resolve().parents[1]
LOCAL_DATA = ROOT / "collector" / "data" / "latest.json"
LOCAL_HISTORY = ROOT / "collector" / "data" / "history.json"
LOCAL_PRICE_HISTORY = ROOT / "collector" / "data" / "price_history.json"
SUPABASE_URL = get_config("SUPABASE_URL")
SUPABASE_KEY = get_config("SUPABASE_KEY")


@st.cache_data(ttl=900)
def load_history():
    if SUPABASE_URL and SUPABASE_KEY:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        try:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/bottom_indicators?select=*&order=data.asc",
                headers=headers, timeout=15,
            )
            response.raise_for_status()
            return pd.DataFrame(response.json()), "Supabase"
        except requests.RequestException:
            pass
    if LOCAL_HISTORY.exists():
        rows = json.loads(LOCAL_HISTORY.read_text(encoding="utf-8"))
        return pd.DataFrame(rows), "histórico local"
    if LOCAL_DATA.exists():
        row = json.loads(LOCAL_DATA.read_text(encoding="utf-8"))
        return pd.DataFrame([row]), "arquivo local"
    return pd.DataFrame(), "indisponível"


@st.cache_data(ttl=900)
def load_cycle_prices():
    if LOCAL_PRICE_HISTORY.exists():
        return pd.DataFrame(json.loads(LOCAL_PRICE_HISTORY.read_text(encoding="utf-8")))
    return pd.DataFrame()


@st.cache_data(ttl=3600)
def load_usd_brl():
    try:
        response = requests.get("https://api.coinbase.com/v2/exchange-rates?currency=USD", timeout=10)
        response.raise_for_status()
        return float(response.json()["data"]["rates"]["BRL"]), "Coinbase"
    except (requests.RequestException, KeyError, ValueError):
        return 5.50, "valor de segurança"


# Nome tecnico -> como explicariamos para alguem que nunca viu o indicador.
PLAIN = {
    "MVRV Z-Score": "Preço vs o que o mercado pagou (MVRV)",
    "NUPL": "Lucro no papel de quem tem BTC (NUPL)",
    "SOPR": "Quem vende, vende no lucro? (SOPR)",
    "Puell Multiple": "Quanto os mineradores ganham (Puell)",
    "Fear & Greed": "Medo e ganância do mercado",
    "RSI diário": "Força do preço no dia (RSI)",
    "Preço / Realized": "Preço vs preço médio pago",
    "StochRSI": "Força do preço, versão rápida",
    "Preço / SMA 200": "Preço vs média dos 200 dias",
    "Reserve Risk": "Confiança de quem segura há anos",
    "RHODL Ratio": "Moedas antigas vs moedas novas",
    "Drawdown anual": "Queda desde a máxima do ano",
    "Retorno 30 dias": "Quanto subiu ou caiu em 30 dias",
    "Z-Score preço 90d": "Preço vs média dos 90 dias",
    "MACD normalizado": "A tendência está virando? (MACD)",
}


def plain(name):
    return PLAIN.get(name, name)


def score_state(value):
    if pd.isna(value): return "Sem dados", "#94a3b8"
    if value >= 75: return "Bom", "#22c55e"
    if value >= 55: return "Melhorando", "#eab308"
    if value >= 40: return "Mais ou menos", "#f97316"
    return "Ruim", "#ef4444"


def main_read(value):
    if pd.isna(value): return "Faltam dados para dizer", "#94a3b8"
    if value >= 75: return "Pode ser o fundo — sinais confirmando", "#22c55e"
    if value >= 55: return "Sinais começando a bater", "#eab308"
    if value >= 35: return "Ainda não deu sinal", "#f97316"
    return "Longe de parecer fundo", "#ef4444"


def indicator_bucket(title, icon, items, color):
    rows = "".join(
        f'<div class="indicator-row"><span>{plain(name)}</span><span class="pill" style="color:{color}">{value:.0f}</span></div>'
        for name, value in items
    ) or '<div class="muted">Nenhum indicador nesta faixa.</div>'
    st.markdown(f'<div class="bucket"><h4>{icon} {title}</h4>{rows}</div>', unsafe_allow_html=True)


def brl(value):
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


df, source = load_history()
if df.empty:
    st.error("Nenhum dado disponível. Execute o coletor e o backfill.")
    st.stop()

df["data"] = pd.to_datetime(df["data"], errors="coerce")
df = df.dropna(subset=["data"]).sort_values("data").reset_index(drop=True)
for column in {"preco", "realized_price", "sma200", *INDICATORS.keys()}.intersection(df.columns):
    df[column] = pd.to_numeric(df[column], errors="coerce")

signals, composite, coverage = build_signals(df)
df["confluencia"] = composite
df["cobertura"] = coverage
last = df.iloc[-1]
score = float(composite.iloc[-1]) if pd.notna(composite.iloc[-1]) else float("nan")
coverage_now = float(coverage.iloc[-1])

STRUCTURAL = ["MVRV Z-Score", "Preço / Realized", "Puell Multiple", "Reserve Risk", "RHODL Ratio", "NUPL", "SOPR", "Preço / SMA 200", "Drawdown anual"]
TACTICAL = ["RSI diário", "StochRSI", "Retorno 30 dias", "Z-Score preço 90d", "MACD normalizado"]
structural_series = signals.reindex(columns=STRUCTURAL).mean(axis=1)
tactical_series = signals.reindex(columns=TACTICAL).mean(axis=1)
sentiment_series = signals["Fear & Greed"]
confirmation_series = tactical_series * 0.65 + sentiment_series * 0.35
structural_score = float(structural_series.iloc[-1])
tactical_score = float(tactical_series.iloc[-1])
sentiment_score = float(sentiment_series.iloc[-1])
confirmation_today = float(confirmation_series.iloc[-1])
previous_confirmation = confirmation_series.dropna().iloc[-2] if confirmation_series.notna().sum() > 1 else confirmation_today
daily_delta = confirmation_today - previous_confirmation

cycle_prices = load_cycle_prices()
try:
    projection = build_cycle_projection(cycle_prices if not cycle_prices.empty else df)
except ValueError:
    st.error(
        "Faltou histórico de preço para calcular o período provável do fundo. "
        "Essa parte precisa de uns 4 anos de cotação e o arquivo "
        "`collector/data/price_history.json` não chegou até aqui. "
        "Rode o backfill de novo para gerar esse arquivo."
    )
    st.stop()
window_start, window_end = projection["consensus_start"], projection["consensus_end"]
as_of = pd.Timestamp(last["data"])
days_to_window = (window_start.normalize() - as_of.normalize()).days

if structural_score >= 70 and confirmation_today >= 70:
    read = "Pode ser o fundo — os sinais estão confirmando"
elif structural_score >= 70:
    read = "Preço já está barato, mas ainda não virou"
elif structural_score >= 55:
    read = "Começando a ficar bom para comprar aos poucos"
else:
    read = "Ainda não parece fundo"

delta_text = f"{daily_delta:+.1f} desde ontem" if pd.notna(daily_delta) else "sem comparação"
st.markdown(f"""
<div class="hero">
  <div class="hero-grid">
    <div>
      <div class="eyebrow">Resumo do dia · atualizado em {as_of:%d/%m/%Y}</div>
      <h1>{read}</h1>
      <div class="muted">{coverage_now:.0f}% dos dados chegaram hoje · {delta_text}</div>
    </div>
    <div class="big-score">{confirmation_today:.0f}<span style="font-size:1.1rem;color:#94a3b8"> / 100 hoje</span></div>
  </div>
  <div class="score-track"><div class="score-marker" style="left:{max(0,min(100,confirmation_today))}%"></div></div>
</div>
""", unsafe_allow_html=True)
st.caption(
    f"Nota de hoje: {confirmation_today:.0f}/100 — o quanto os sinais dizem que a virada já começou. "
    f"Preço barato: {structural_score:.0f}/100 (muda devagar, ao longo de meses). "
    f"Já virou: {tactical_score:.0f}/100 (muda rápido, dia a dia). "
    "Preço barato sozinho não quer dizer que o menor preço já passou."
)

current = signals.iloc[-1]
LENSES = {
    "Preço está barato?": ["MVRV Z-Score", "Preço / Realized", "Puell Multiple", "Reserve Risk", "RHODL Ratio"],
    "Quem tem BTC está sofrendo?": ["NUPL", "SOPR"],
    "Queda está perdendo força?": ["RSI diário", "StochRSI", "Preço / SMA 200", "Drawdown anual", "Retorno 30 dias", "Z-Score preço 90d", "MACD normalizado"],
    "Há medo no mercado?": ["Fear & Greed"],
}
LENS_COPY = {
    "Preço está barato?": "Compara o preço de hoje com o dos fundos anteriores.",
    "Quem tem BTC está sofrendo?": "Se quem tem BTC está no lucro, no prejuízo ou vendendo.",
    "Queda está perdendo força?": "Se a queda está desacelerando e o preço se afastou das médias.",
    "Há medo no mercado?": "Medo extremo costuma aparecer perto dos fundos.",
}

st.subheader("As quatro perguntas que importam")
st.caption("Cada pergunta vira uma nota de 0 a 100. Quanto maior, mais a resposta é 'sim'.")
lens_columns = st.columns(4)
for column, (name, members) in zip(lens_columns, LENSES.items()):
    value = float(current.reindex(members).mean())
    state, color = score_state(value)
    with column:
        st.markdown(f'<div class="lens"><div class="lens-title">{name}</div><div class="lens-score" style="color:{color}">{value:.0f} · {state}</div><div class="lens-text">{LENS_COPY[name]}</div></div>', unsafe_allow_html=True)

summary_left, summary_right = st.columns([1.35, 1])
with summary_left:
    st.subheader("O que isso quer dizer")
    strongest = current.dropna().sort_values(ascending=False).head(3)
    weakest = current.dropna().sort_values().head(2)
    strong_text = ", ".join(plain(name) for name in strongest.index)
    weak_text = " e ".join(plain(name) for name in weakest.index)
    st.markdown(
        f"**Hoje ainda não dá para dizer que o fundo chegou.** O preço já está em faixa parecida com a "
        f"de fundos anteriores ({structural_score:.0f}/100), mas os sinais que mostram a virada acontecendo "
        f"ainda estão fracos ({tactical_score:.0f}/100). "
        f"O que já está a favor: **{strong_text}**. O que ainda falta: **{weak_text}**."
    )
    if len(signals) > 1:
        changes = (signals.iloc[-1] - signals.iloc[-2]).dropna().sort_values(key=abs, ascending=False).head(3)
        change_lines = []
        for name, change in changes.items():
            direction = "melhorou" if change > 0 else "piorou"
            change_lines.append(f"**{plain(name)}** {direction} ({change:+.1f})")
        st.caption("O que mudou de ontem para hoje: " + " · ".join(change_lines))

with summary_right:
    timing = f"Ainda faltam {days_to_window} dias para começar." if days_to_window > 0 else "Estamos dentro desse período agora."
    st.markdown(f"""
<div class="window-card">
  <div class="eyebrow">Período em que o fundo costuma aparecer</div>
  <div class="window-date">{window_start:%d/%m} — {window_end:%d/%m/%Y}</div>
  <div>{timing}</div>
  <div class="muted" style="margin-top:8px">Vem de duas contas: quanto tempo passou desde o último halving e quanto tempo costuma passar depois do topo. É só uma referência — o fundo pode vir antes ou depois disso.</div>
</div>
""", unsafe_allow_html=True)

st.subheader("Simulador: comprar aos poucos e vender depois")
st.caption(
    "Comprar aos poucos (o mercado chama de DCA) é dividir o dinheiro em várias compras ao longo do tempo, "
    "em vez de gastar tudo de uma vez. Isso aqui é uma simulação com as contas do painel — não é conselho de "
    "investimento. Mexa nos números e compare as possibilidades antes de decidir qualquer coisa."
)

btc_price, _ = latest_value(df, "preco")
realized_price, _ = latest_value(df, "realized_price")
usd_brl, fx_source = load_usd_brl()
market_entry_score = structural_score * 0.55 + tactical_score * 0.35 + sentiment_score * 0.10
readiness = purchase_readiness(market_entry_score, as_of, window_start, window_end)

i1, i2, i3, i4 = st.columns(4)
with i1:
    capital_brl = st.number_input("Quanto você tem para investir (R$)", min_value=100.0, value=10000.0, step=1000.0)
with i2:
    strategy = st.selectbox("Seu jeito de investir", ["Conservador", "Balanceado", "Agressivo"], index=1,
                            help="Conservador compra menos agora e guarda mais para depois. Agressivo faz o contrário.")
with i3:
    default_window_price = round(((btc_price or 0) + (realized_price or btc_price or 0)) / 2, -2)
    window_price = st.number_input("Preço que você acha que o BTC vai ter no fundo (US$)", min_value=1000.0, value=float(default_window_price), step=1000.0)
with i4:
    fee_pct = st.number_input("Taxa que a corretora cobra (%)", min_value=0.0, max_value=5.0, value=0.5, step=0.1)

dca = simulate_dca(capital_brl, btc_price, window_price, usd_brl, fee_pct, strategy, readiness["score"])
next_top_central = NEXT_TOP_WINDOW[0] + (NEXT_TOP_WINDOW[1] - NEXT_TOP_WINDOW[0]) / 2
hold_years = max(0, (next_top_central - as_of).days / 365.25)

r1, r2, r3, r4 = st.columns(4)
r1.metric("É hora de comprar?", f"{readiness['score']:.0f}/100", help="Junta as notas do painel com a proximidade do período de fundo. Nota alta não garante que o fundo chegou.")
r2.metric("O que o simulador sugere", readiness["label"])
r3.metric("Quanto de BTC você teria no fim", f"₿ {dca['btc']:.6f}")
r4.metric("Preço médio que você pagaria", f"US$ {dca['effective_entry_usd']:,.0f}")

st.markdown("#### Como dividir suas compras")
st.caption("Se a nota estiver baixa (abaixo de 60), o simulador compra menos agora e guarda mais para depois. Se estiver alta (acima de 80), compra mais agora. Entre os dois, segue o jeito de investir que você escolheu. Essa conta é refeita todo dia.")
plan_df = pd.DataFrame(dca["rows"])
st.dataframe(
    plan_df,
    hide_index=True,
    width="stretch",
    column_config={
        "%": st.column_config.NumberColumn("Quanto do total", format="%.0f%%"),
        "Aporte (R$)": st.column_config.NumberColumn("Valor a investir", format="R$ %.2f"),
        "BTC estimado": st.column_config.NumberColumn("BTC que você compra", format="%.6f"),
        "Preço assumido (US$)": st.column_config.NumberColumn("Preço usado na conta", format="US$ %.0f"),
    },
)

with st.expander("Mudar os preços de venda e o dólar"):
    e1, e2, e3, e4 = st.columns(4)
    prior_top = projection["provisional_top_price"]
    defensive_target = e1.number_input("Vender cedo, no seguro (US$)", min_value=1000.0, value=float(round(btc_price * 1.5, -3)), step=5000.0)
    retest_target = e2.number_input("BTC volta ao topo antigo (US$)", min_value=1000.0, value=float(round(prior_top, -3)), step=5000.0)
    mid_target = e3.number_input("Meio da próxima alta (US$)", min_value=1000.0, value=float(round(prior_top * 1.4, -3)), step=5000.0)
    top_target = e4.number_input("BTC faz novo topo (US$)", min_value=1000.0, value=float(round(prior_top * 2.0, -3)), step=10000.0)
    future_fx = st.number_input("Dólar na hora de vender (R$)", min_value=1.0, max_value=20.0, value=float(round(usd_brl, 2)), step=0.10)
    st.caption(f"Dólar de hoje, usado nas compras: R$ {usd_brl:.2f} ({fx_source}). Ninguém consegue prever o dólar do futuro, e ele muda bastante o resultado em reais.")

targets = [
    ("Vender cedo, no seguro", defensive_target, "quando o preço chegar lá; não dá para saber a data"),
    ("Volta ao topo antigo", retest_target, "provavelmente entre 2027 e 2028"),
    ("Meio da próxima alta", mid_target, f"por volta de {NEXT_HALVING_ESTIMATE + pd.Timedelta(days=365):%m/%Y}"),
    ("Novo topo", top_target, f"entre {NEXT_TOP_WINDOW[0]:%d/%m} e {NEXT_TOP_WINDOW[1]:%d/%m/%Y}"),
]
exit_rows = simulate_exits(dca["btc"], capital_brl, future_fx, targets)
exit_df = pd.DataFrame(exit_rows)

st.markdown("#### Quanto seu dinheiro poderia virar")
value_cols = st.columns(4)
for col, row in zip(value_cols, exit_rows):
    with col:
        st.metric(row["Cenário"], brl(row["Valor estimado (R$)"]), delta=f"{row['Retorno']:+.0f}%")
        st.caption(row["Horizonte"])

st.dataframe(
    exit_df,
    hide_index=True,
    width="stretch",
    column_config={
        "Cenário": st.column_config.TextColumn("Se acontecer isso"),
        "Preço BTC (US$)": st.column_config.NumberColumn("BTC valendo", format="US$ %.0f"),
        "Horizonte": st.column_config.TextColumn("Quando"),
        "Valor estimado (R$)": st.column_config.NumberColumn("Você teria", format="R$ %.2f"),
        "Lucro bruto (R$)": st.column_config.NumberColumn("Lucro", format="R$ %.2f"),
        "Retorno": st.column_config.NumberColumn("Ganho", format="%.1f%%"),
    },
)
st.warning(
    f"Para o cenário de novo topo, você precisaria esperar uns {hold_years:.1f} anos. "
    "As contas são simplificadas: descontam só a taxa de compra que você informou. "
    "Ainda faltaria tirar imposto, taxa de venda e diferença de preço na hora de negociar. "
    "E esses preços são possibilidades, não previsões."
)

st.subheader("Como está cada indicador hoje")
st.caption("Nota de 0 a 100 para cada um: 100 quer dizer 'bem parecido com um fundo', não '100% de certeza'. Nenhum deles sozinho confirma nada — o que importa é vários apontarem junto.")
confirmed = [(n, v) for n, v in current.sort_values(ascending=False).items() if pd.notna(v) and v >= 70]
transition = [(n, v) for n, v in current.sort_values(ascending=False).items() if pd.notna(v) and 45 <= v < 70]
not_confirmed = [(n, v) for n, v in current.sort_values(ascending=False).items() if pd.notna(v) and v < 45]
c1, c2, c3 = st.columns(3)
with c1: indicator_bucket("Já estão a favor", "●", confirmed, "#22c55e")
with c2: indicator_bucket("Mais ou menos", "●", transition, "#eab308")
with c3: indicator_bucket("Ainda contra", "●", not_confirmed, "#ef4444")

st.subheader("Onde estamos na linha do tempo")
show_smas = st.toggle("Mostrar as médias de preço no gráfico", value=False)
timeline = go.Figure()
history = projection["work"].tail(1100)
timeline.add_trace(go.Scatter(x=history["data"], y=history["preco"], name="Bitcoin", line={"color":"#e5e7eb","width":1.5}))
timeline.add_vrect(x0=projection["halving"]["start"], x1=projection["halving"]["end"], fillcolor="#7c3aed", opacity=.12, line_width=0, annotation_text="conta do halving", annotation_position="top left")
timeline.add_vrect(x0=projection["top"]["start"], x1=projection["top"]["end"], fillcolor="#ef4444", opacity=.14, line_width=0, annotation_text="conta do topo", annotation_position="top right")
timeline.add_vrect(x0=window_start, x1=window_end, fillcolor="#2563eb", opacity=.28, line_width=0, annotation_text="ONDE AS DUAS SE ENCONTRAM", annotation_position="bottom left")
timeline.add_vline(x=projection["last_date"], line_color="#64748b", line_dash="dot", annotation_text="hoje")
timeline.add_vline(x=projection["cycle_57w"], line_color="#3b82f6", line_dash="dot", annotation_text="57 semanas")
if show_smas:
    colors = {50:"#ef3340",100:"#22c55e",200:"#eab308"}
    for period in (50,100,200):
        sma = projection["smas"][period]
        timeline.add_trace(go.Scatter(x=sma.index, y=sma.values, name=f"Média de {period} semanas", line={"color":colors[period],"width":2}))
        future = projection["projected_smas"][period]
        timeline.add_trace(go.Scatter(x=future.index, y=future.values, showlegend=False, line={"color":colors[period],"width":2,"dash":"dash"}))
timeline.update_xaxes(range=[history["data"].iloc[0], projection["cycle_57w"] + pd.Timedelta(days=35)])
timeline.update_yaxes(type="log", title="Preço do BTC")
timeline.update_layout(height=520, margin={"l":20,"r":20,"t":40,"b":20}, paper_bgcolor="#080c14", plot_bgcolor="#0b1220", font={"color":"#cbd5e1"}, hovermode="x unified", legend={"orientation":"h","y":1.08})
st.plotly_chart(timeline, width="stretch")
st.caption(
    "A faixa azul é onde as duas contas concordam — o período mais provável. "
    "A linha de 57 semanas é aquele seu padrão de 399 dias; deixei separado porque tem menos histórico para comprovar. "
    "O preço está numa escala que espreme os números grandes, para dar para ver os ciclos antigos junto com os de hoje."
)

with st.expander("Para quem quiser ver a conta por trás"):
    a, b, c, d = st.columns(4)
    price, _ = latest_value(df, "preco")
    a.metric("Bitcoin agora", f"${price:,.0f}" if price else "N/D")
    b.metric("Data provável pela conta do halving", f"{projection['halving']['central']:%d/%m/%Y}")
    c.metric("Data provável pela conta do topo", f"{projection['top']['central']:%d/%m/%Y}")
    next_cross = projection["next_crossing"]
    d.metric("Próximo cruzamento de médias", f"{projection['next_crossing_pair']} · {next_cross:%d/%m/%Y}" if next_cross else "N/D")
    st.markdown("""
**Como a nota é calculada.** Cada indicador vira uma nota de 0 a 100, comparando o valor de hoje com os
valores que ele teve nos fundos anteriores. Depois tiramos uma média — alguns indicadores pesam mais que
outros, porque têm histórico melhor. Nota alta significa que várias coisas que aconteceram nos fundos
passados estão acontecendo de novo ao mesmo tempo.

**As datas** vêm de duas contas separadas: quantos dias costumam passar entre o halving e o fundo, e
quantos dias costumam passar entre o topo e o fundo. Elas não entram na nota — são só contexto.

**O que pode dar errado.** Só existem três ciclos completos para estudar, o que é pouquíssimo para
qualquer conclusão firme. As fontes de dados são gratuitas e às vezes atrasam. E nada garante que o
que funcionou antes vai funcionar de novo — o mercado muda. Use isso para acompanhar as coisas
melhorando aos poucos, não para tentar acertar o dia ou o preço exato.
""")

st.caption(f"Dados de {source} · leitura do dia {as_of:%d/%m/%Y} · o painel se atualiza sozinho todo dia")
