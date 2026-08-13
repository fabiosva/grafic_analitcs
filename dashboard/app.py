"""Painel de Fundo do BTC: uma leitura diária, em português simples, de quão perto estamos de um fundo."""
from pathlib import Path
import json
import os

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from analytics import (
    INDICATORS, NEXT_HALVING_ESTIMATE, NEXT_TOP_WINDOW, build_cycle_projection, build_cycle_repeat,
    build_signals, classify, data_health, historical_analogs, latest_value, models_consensus, pnl_regime,
    purchase_readiness, score_calibration, simulate_dca, simulate_exits, stress_fundo_mais_baixo,
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
  .lens-scale { color:#64748b; font-size:.72rem; line-height:1.4; margin-top:8px; padding-top:8px; border-top:1px dashed #273449; }
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
def load_previsoes():
    if SUPABASE_URL and SUPABASE_KEY:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        try:
            response = requests.get(
                f"{SUPABASE_URL}/rest/v1/previsoes?select=*&order=data_previsao.desc,prazo_dias.asc",
                headers=headers, timeout=15,
            )
            response.raise_for_status()
            return pd.DataFrame(response.json())
        except requests.RequestException:
            pass
    return pd.DataFrame()


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
    "Preço vs média de 2 anos": "Preço vs média de 2 anos",
    "Preço vs Power Law": "Preço vs corredor de longo prazo",
    "STH-MVRV": "Quem comprou recente está no lucro? (STH-MVRV)",
    "AVIV Ratio": "Preço vs custo de quem está ativo (AVIV)",
    "VDD Multiple": "Moedas antigas sendo movimentadas (VDD)",
    "LTH % em lucro": "Quanto de quem segura há anos está no lucro",
    "STH % da oferta": "Quanto do BTC em circulação é de quem comprou recente",
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


def price_level_card(model, target, current_price, detail):
    reached = current_price <= target
    if reached:
        distance = (target - current_price) / target * 100
        status = "ATINGIU"
        status_text = f"preço está {distance:.1f}% abaixo do limite"
        color = "#22c55e"
    else:
        distance = (current_price - target) / current_price * 100
        status = "AINDA NÃO"
        status_text = f"falta cair {distance:.1f}%"
        color = "#f59e0b"
    st.markdown(
        f'<div class="lens">'
        f'<div class="lens-title">{model}</div>'
        f'<div class="lens-score">US$ {target:,.0f}</div>'
        f'<div style="color:{color};font-weight:800;margin-bottom:7px">● {status} · {status_text}</div>'
        f'<div class="lens-text">{detail}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


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
saude_dados = data_health(df)

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
    cycle_repeat = build_cycle_repeat(cycle_prices if not cycle_prices.empty else df)
except ValueError:
    st.error(
        "Faltou histórico de preço para calcular o período provável do fundo. "
        "Essa parte precisa de uns 4 anos de cotação e o arquivo "
        "`collector/data/price_history.json` não chegou até aqui. "
        "Rode o backfill de novo para gerar esse arquivo."
    )
    st.stop()
structural_score = (
    structural_score * len(STRUCTURAL)
    + cycle_repeat["investor_score"]
    + cycle_repeat["power_score"]
) / (len(STRUCTURAL) + 2)
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

gauge_label, gauge_color = classify(score, coverage_now)
gauge = go.Figure(go.Indicator(
    mode="gauge+number",
    value=score if pd.notna(score) else 0,
    number={"suffix": "/100", "font": {"size": 46, "color": gauge_color}},
    gauge={
        "axis": {"range": [0, 100], "tickcolor": "#94a3b8", "tickfont": {"color": "#94a3b8"}},
        "bar": {"color": gauge_color, "thickness": 0.3},
        "bgcolor": "#0b1220",
        "borderwidth": 1,
        "bordercolor": "#273449",
        "steps": [
            {"range": [0, 35], "color": "#3f1d1d"},
            {"range": [35, 55], "color": "#4a2b12"},
            {"range": [55, 75], "color": "#4a3b0e"},
            {"range": [75, 100], "color": "#14351f"},
        ],
    },
))
gauge.update_layout(height=230, margin={"l": 40, "r": 40, "t": 10, "b": 10}, paper_bgcolor="#080c14", font={"color": "#e5e7eb"})
st.markdown("### Velocímetro: é um bom momento pra comprar?")
st.plotly_chart(gauge, width="stretch")
st.markdown(
    f"<div style='text-align:center;font-size:1.15rem;font-weight:800;color:{gauge_color};margin-top:-8px'>{gauge_label}</div>",
    unsafe_allow_html=True,
)
st.caption(
    f"Combina os {len(INDICATORS)} indicadores do painel numa nota só, cada um com seu peso "
    f"(cobertura hoje: {coverage_now:.0f}% dos dados disponíveis). Quanto mais alto, mais parecido "
    "com momentos históricos de fundo — não é garantia de nada, é confluência de sinais."
)

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

alertas = []
previous_structural = structural_series.dropna().iloc[-2] if structural_series.notna().sum() > 1 else structural_score
if previous_structural < 70 <= structural_score:
    alertas.append(("🟢", "Preço entrou na faixa considerada barata (nota de 'preço barato' cruzou 70 hoje)."))
elif previous_structural >= 70 > structural_score:
    alertas.append(("🟡", "Preço saiu da faixa considerada barata (nota de 'preço barato' caiu abaixo de 70)."))
if confirmation_today >= 80:
    alertas.append(("🟢", f"Confirmação de virada está forte hoje ({confirmation_today:.0f}/100) — os sinais de curto prazo estão bem alinhados com fundo."))
if daily_delta is not None and pd.notna(daily_delta):
    price_change_pct = df["preco"].pct_change().iloc[-1] * 100 if len(df) > 1 else 0
    if daily_delta > 5 and pd.notna(price_change_pct) and price_change_pct < -2:
        alertas.append(("🔵", "Divergência: a nota de confirmação subiu enquanto o preço caiu — pode ser sinal de exaustão da queda."))
    elif daily_delta < -5 and pd.notna(price_change_pct) and price_change_pct > 2:
        alertas.append(("🔵", "Divergência: a nota de confirmação caiu enquanto o preço subiu — pode ser um alívio de curto prazo, não uma virada real."))
criticos = {"mvrv_zscore", "fear_greed", "rsi", "realized_price"}
vencidos = [h["coluna"] for h in saude_dados if h["coluna"] in criticos and h["status"] == "desatualizado"]
if vencidos:
    alertas.append(("🔴", f"Dado crítico desatualizado (mais de 7 dias): {', '.join(vencidos)}. A nota de hoje pode estar usando valor antigo nesses indicadores."))

if alertas:
    st.markdown("##### Alertas de hoje")
    for emoji, texto in alertas:
        st.markdown(f"{emoji} {texto}")
    st.caption("Alertas aparecem só quando algo muda de faixa, a confirmação fica muito forte, há divergência entre nota e preço, ou um dado crítico está vencido.")

current = signals.iloc[-1].copy()
current["Preço vs média de 2 anos"] = cycle_repeat["investor_score"]
current["Preço vs Power Law"] = cycle_repeat["power_score"]
LENSES = {
    "Preço está barato?": ["MVRV Z-Score", "Preço / Realized", "Puell Multiple", "Reserve Risk", "RHODL Ratio", "Preço vs média de 2 anos", "Preço vs Power Law"],
    "Quem tem BTC está sofrendo?": ["NUPL", "SOPR"],
    "Queda está perdendo força?": ["RSI diário", "StochRSI", "Preço / SMA 200", "Drawdown anual", "Retorno 30 dias", "Z-Score preço 90d", "MACD normalizado"],
    "Há medo no mercado?": ["Fear & Greed"],
}
LENS_COPY = {
    "Preço está barato?": "Compara o preço de hoje com o dos fundos anteriores.",
    "Quem tem BTC está sofrendo?": "Se quem tem BTC está no lucro, no prejuízo ou vendendo.",
    "Queda está perdendo força?": "Se a queda está desacelerando e o preço se afastou das médias.",
    "Há medo no mercado?": "Medo extremo costuma aparecer perto dos fundos. Dado do Fear & Greed Index, fornecido pela Alternative.me.",
}
LENS_SCALE = {
    "Preço está barato?": ("0 = preço caro, sem desconto", "100 = muito barato, ótimo momento"),
    "Quem tem BTC está sofrendo?": ("0 = quase todo mundo no lucro", "100 = muita gente no prejuízo"),
    "Queda está perdendo força?": ("0 = queda ainda forte", "100 = queda esgotada, sinais de virada"),
    "Há medo no mercado?": ("0 = mercado ganancioso", "100 = medo extremo"),
}

st.subheader("As quatro perguntas que importam")
st.caption("Cada pergunta vira uma nota de 0 a 100. Quanto maior, mais a resposta é 'sim'.")
lens_columns = st.columns(4)
for column, (name, members) in zip(lens_columns, LENSES.items()):
    # "Preço está barato?" usa o mesmo numero do resumo (structural_score),
    # em vez de recalcular com outro conjunto de indicadores, pra nao mostrar
    # dois valores diferentes pra mesma pergunta em lugares diferentes do painel.
    value = structural_score if name == "Preço está barato?" else float(current.reindex(members).mean())
    state, color = score_state(value)
    escala_baixa, escala_alta = LENS_SCALE[name]
    with column:
        st.markdown(
            f'<div class="lens"><div class="lens-title">{name}</div>'
            f'<div class="lens-score" style="color:{color}">{value:.0f} · {state}</div>'
            f'<div class="lens-text">{LENS_COPY[name]}</div>'
            f'<div class="lens-scale">{escala_baixa}<br>{escala_alta}</div></div>',
            unsafe_allow_html=True,
        )

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

st.subheader("Para onde o preço pode ir (baseado em dias parecidos)")
st.caption(
    "Isso NÃO é uma previsão. O painel procura, no último ano, dias em que a situação técnica (RSI, força do "
    "preço, distância das médias móveis) foi parecida com a de hoje, e mostra o que o preço fez de verdade "
    "depois desses dias. Os dias escolhidos são forçados a vir de períodos diferentes entre si (não pega vários "
    "dias seguidos do mesmo evento como se fossem casos separados). Amostra pequena — quando a margem de erro "
    "cobre 50%, o painel marca como 'inconclusivo' em vez de fingir uma direção clara."
)
btc_price_hoje, _ = latest_value(df, "preco")
analog = historical_analogs(df)
if analog:
    horizonte_labels = {3: "3 dias", 7: "7 dias", 14: "14 dias", 30: "30 dias"}
    linhas_previsao = []
    for h, label in horizonte_labels.items():
        dado = analog["horizontes"].get(h)
        if not dado:
            continue
        if dado["inconclusivo"]:
            direcao = "? Inconclusivo"
        elif dado["prob_alta"] > 50:
            direcao = "↑ Alta"
        else:
            direcao = "↓ Queda"
        linhas_previsao.append({
            "Prazo": label,
            "Direção": direcao,
            "Subiu em % dos casos (intervalo de confiança)": f"{dado['prob_alta']:.0f}% ({dado['prob_alta_ic_baixo']:.0f}–{dado['prob_alta_ic_alto']:.0f}%)",
            "Preço-alvo estimado": f"US$ {dado['preco_alvo_medio']:,.0f}",
            "Episódios independentes": dado["n_amostras"],
        })
    st.caption(f"Preço de hoje: US$ {btc_price_hoje:,.0f} · {analog['n_episodios']} episódios históricos independentes usados na comparação")
    st.dataframe(pd.DataFrame(linhas_previsao), width="stretch", hide_index=True)
    st.caption(
        "O intervalo entre parênteses é a faixa onde a % real provavelmente está (95% de confiança, método de "
        "Wilson). Quando essa faixa cruza 50%, não dá pra afirmar uma direção — por isso 'inconclusivo'."
    )

    dado_7d = analog["horizontes"].get(7)
    if dado_7d and dado_7d.get("exemplos"):
        with st.expander("Ver os dias parecidos que embasam essa conta (olhando 7 dias à frente)"):
            st.caption("Cada linha é um dia do passado parecido com hoje, o preço dele, e o preço 7 dias depois.")
            tabela_exemplos = pd.DataFrame([
                {
                    "Dia parecido": pd.Timestamp(e["data"]).strftime("%d/%m/%Y"),
                    "Preço na época": f"US$ {e['preco_na_epoca']:,.0f}",
                    "Preço 7 dias depois": f"US$ {e['preco_depois']:,.0f}",
                    "Variação": f"{e['variacao_pct']:+.1f}%",
                }
                for e in dado_7d["exemplos"]
            ])
            st.dataframe(tabela_exemplos, width="stretch", hide_index=True)
else:
    st.caption("Ainda não há histórico suficiente com todos os dados necessários (RSI, StochRSI, médias móveis) para fazer essa comparação.")

st.subheader("Placar: os palpites anteriores acertaram?")
st.caption(
    "Todo dia o coletor grava o palpite do dia (igual a tabela acima) antes de saber o resultado. Quando a "
    "data-alvo chega, ele confere sozinho se a direção estava certa e se o preço-alvo foi batido. Isso é um "
    "histórico honesto: nada aqui é reescrito depois de saber o resultado."
)
previsoes_df = load_previsoes()
if previsoes_df.empty:
    st.caption("Ainda não há palpites registrados — a partir de hoje o coletor começa a gravar, e os primeiros resultados aparecem aqui em alguns dias.")
else:
    avaliadas = previsoes_df[previsoes_df["preco_real"].notna()].copy()
    pendentes_n = len(previsoes_df) - len(avaliadas)
    if not avaliadas.empty:
        acerto_direcao = avaliadas["direcao_correta"].mean() * 100
        acerto_alvo = avaliadas["alvo_batido"].mean() * 100
        m1, m2, m3 = st.columns(3)
        m1.metric("Acertou a direção", f"{acerto_direcao:.0f}%", help="Das vezes em que já sabemos o resultado, quantas o painel acertou se ia subir ou cair.")
        m2.metric("Bateu o preço-alvo", f"{acerto_alvo:.0f}%", help="Das vezes em que já sabemos o resultado, quantas o preço chegou no valor estimado ou passou dele.")
        m3.metric("Palpites já conferidos", f"{len(avaliadas)}", f"{pendentes_n} aguardando data" if pendentes_n else None)

        tabela_placar = avaliadas.sort_values("data_previsao", ascending=False).head(20).copy()
        tabela_placar["Palpite feito em"] = pd.to_datetime(tabela_placar["data_previsao"]).dt.strftime("%d/%m/%Y")
        tabela_placar["Prazo"] = tabela_placar["prazo_dias"].astype(str) + " dias"
        tabela_placar["Direção prevista"] = tabela_placar["direcao_prevista"]
        tabela_placar["Preço-alvo"] = tabela_placar["preco_alvo_estimado"].map(lambda v: f"US$ {v:,.0f}")
        tabela_placar["Preço real"] = tabela_placar["preco_real"].map(lambda v: f"US$ {v:,.0f}")
        tabela_placar["Variação real"] = tabela_placar["variacao_real_pct"].map(lambda v: f"{v:+.1f}%")
        tabela_placar["Direção acertou?"] = tabela_placar["direcao_correta"].map(lambda v: "✅" if v else "❌")
        tabela_placar["Bateu o alvo?"] = tabela_placar["alvo_batido"].map(lambda v: "✅" if v else "❌")
        st.dataframe(
            tabela_placar[[
                "Palpite feito em", "Prazo", "Direção prevista", "Preço-alvo", "Preço real",
                "Variação real", "Direção acertou?", "Bateu o alvo?",
            ]],
            width="stretch", hide_index=True,
        )
    else:
        st.caption(f"{pendentes_n} palpite(s) já registrado(s), mas nenhum ainda com data-alvo vencida para conferir.")

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
    capital_brl = st.number_input("Quanto você tem para investir (R$)", min_value=100.0, max_value=100_000_000.0, value=10000.0, step=1000.0)
with i2:
    strategy = st.selectbox("Seu jeito de investir", ["Conservador", "Balanceado", "Agressivo"], index=1,
                            help="Conservador compra menos agora e guarda mais para depois. Agressivo faz o contrário.")
with i3:
    default_window_price = round(cycle_repeat["bottom_price"], -2)
    window_price = st.number_input("Preço que você acha que o BTC vai ter no fundo (US$)", min_value=1000.0, max_value=10_000_000.0, value=float(default_window_price), step=1000.0)
with i4:
    fee_pct = st.number_input("Taxa que a corretora cobra (%)", min_value=0.0, max_value=5.0, value=0.5, step=0.1)

dca = simulate_dca(capital_brl, btc_price, window_price, usd_brl, fee_pct, strategy, readiness["score"])
next_top_central = NEXT_TOP_WINDOW[0] + (NEXT_TOP_WINDOW[1] - NEXT_TOP_WINDOW[0]) / 2
hold_years = max(0, (next_top_central - as_of).days / 365.25)

r1, r2, r3, r4 = st.columns(4)
r1.metric("É hora de comprar?", f"{readiness['score']:.0f}/100", help="Junta as notas do painel com a proximidade do período de fundo. Nota alta não garante que o fundo chegou.")
r2.metric("O que o simulador sugere", readiness["label"], help=readiness["detail"])
r3.metric("Quanto de BTC você teria no fim", f"₿ {dca['btc']:.6f}")
r4.metric("Preço médio que você pagaria", f"US$ {dca['effective_entry_usd']:,.0f}")

st.markdown("#### Como dividir suas compras")
st.caption("Se a nota estiver baixa (abaixo de 60), o simulador compra menos agora e guarda mais para depois. Se estiver alta (acima de 80), compra mais agora. Entre os dois, segue o jeito de investir que você escolheu. Essa conta é refeita todo dia.")
plan_df = pd.DataFrame(dca["rows"])
plan_df["Aporte (R$)"] = plan_df["Aporte (R$)"].map(brl)
st.dataframe(
    plan_df,
    hide_index=True,
    width="stretch",
    column_config={
        "%": st.column_config.NumberColumn("Quanto do total", format="%.0f%%"),
        "Aporte (R$)": st.column_config.TextColumn("Valor a investir"),
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
    top_target = e4.number_input("BTC faz novo topo (US$)", min_value=1000.0, value=float(round(cycle_repeat["top_price"], -3)), step=10000.0)
    future_fx = st.number_input("Dólar na hora de vender (R$)", min_value=1.0, max_value=20.0, value=float(round(usd_brl, 2)), step=0.10)
    st.caption(f"Dólar de hoje, usado nas compras: R$ {usd_brl:.2f} ({fx_source}). Ninguém consegue prever o dólar do futuro, e ele muda bastante o resultado em reais.")

with st.expander("Custos de vender, imposto e custódia (opcional, avançado)"):
    st.caption("Por padrão o simulador acima só desconta a taxa de compra. Aqui você pode incluir mais custos reais pra ver o valor líquido, não só o bruto.")
    ce1, ce2, ce3, ce4 = st.columns(4)
    custos_venda_pct = ce1.number_input("Taxa + spread + slippage na venda (%)", min_value=0.0, max_value=10.0, value=0.5, step=0.1, help="Some a taxa da corretora, o spread (diferença entre compra e venda) e o slippage (o preço mudar entre você mandar a ordem e ela executar).")
    imposto_pct = ce2.number_input("Imposto sobre o lucro (%)", min_value=0.0, max_value=50.0, value=15.0, step=1.0, help="No Brasil, hoje a alíquota de come varia por faixa de lucro mensal. Ajuste pro seu caso — isso não é orientação fiscal.")
    custodia_pct_ano = ce3.number_input("Custo de guardar o BTC por ano (%)", min_value=0.0, max_value=10.0, value=0.0, step=0.1, help="Corretoras/custodiantes que cobram taxa de custódia. Se você guarda na sua própria carteira, deixe 0.")
    anos_custodia_manual = ce4.number_input("Por quantos anos vai guardar", min_value=0.0, max_value=20.0, value=float(round(hold_years, 1)), step=0.5)

targets = [
    ("Vender cedo, no seguro", defensive_target, "quando o preço chegar lá; não dá para saber a data"),
    ("Volta ao topo antigo", retest_target, "provavelmente entre 2027 e 2028"),
    ("Meio da próxima alta", mid_target, f"por volta de {NEXT_HALVING_ESTIMATE + pd.Timedelta(days=365):%m/%Y}"),
    ("Novo topo", top_target, f"cenário repetido aponta {cycle_repeat['top_date']:%m/%Y}"),
]
exit_rows = simulate_exits(
    dca["btc"], capital_brl, future_fx, targets,
    custos_venda_pct=custos_venda_pct, imposto_pct=imposto_pct,
    custodia_pct_ano=custodia_pct_ano, anos_custodia=anos_custodia_manual,
)
exit_df = pd.DataFrame(exit_rows)
exit_df["Valor estimado (R$)"] = exit_df["Valor estimado (R$)"].map(brl)
exit_df["Lucro bruto (R$)"] = exit_df["Lucro bruto (R$)"].map(brl)
exit_df["Imposto (R$)"] = exit_df["Imposto (R$)"].map(brl)
exit_df["Lucro líquido (R$)"] = exit_df["Lucro líquido (R$)"].map(brl)

st.markdown("#### Quanto seu dinheiro poderia virar (já líquido, com custos e imposto)")
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
        "Valor estimado (R$)": st.column_config.TextColumn("Você teria (líquido)"),
        "Lucro bruto (R$)": st.column_config.TextColumn("Lucro antes do imposto"),
        "Imposto (R$)": st.column_config.TextColumn("Imposto"),
        "Lucro líquido (R$)": st.column_config.TextColumn("Lucro líquido"),
        "Retorno": st.column_config.NumberColumn("Ganho líquido", format="%.1f%%"),
    },
)

with st.expander("E se o fundo real vier mais baixo do que você estimou?"):
    st.caption("Cenários de estresse: se o preço cair mais do que o esperado além da sua estimativa de fundo.")
    st.dataframe(
        pd.DataFrame(stress_fundo_mais_baixo(window_price)),
        hide_index=True, width="stretch",
        column_config={"Novo fundo possível (US$)": st.column_config.NumberColumn(format="US$ %.0f")},
    )
st.warning(
    f"Para o cenário de novo topo, você precisaria esperar uns {hold_years:.1f} anos. "
    "As contas já descontam taxa de compra, taxa/spread/slippage de venda, custódia e imposto (com os valores "
    "que você ajustou acima). Mesmo assim são simplificadas — câmbio, inflação e mudanças na lei de imposto no "
    "meio do caminho não entram na conta. E esses preços são possibilidades, não previsões."
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
timeline.update_layout(title="Preço do BTC ao longo do tempo, com a janela provável do próximo fundo", height=520, margin={"l":20,"r":20,"t":60,"b":20}, paper_bgcolor="#080c14", plot_bgcolor="#0b1220", font={"color":"#cbd5e1"}, hovermode="x unified", legend={"orientation":"h","y":1.08})
st.plotly_chart(timeline, width="stretch")
st.caption(
    "A faixa azul é onde as duas contas concordam — o período mais provável. "
    "A linha de 57 semanas é aquele seu padrão de 399 dias; deixei separado porque tem menos histórico para comprovar. "
    "O preço está numa escala que espreme os números grandes, para dar para ver os ciclos antigos junto com os de hoje."
)

st.subheader("Mapa dos possíveis fundos")
st.caption(
    f"Bitcoin hoje: US$ {btc_price:,.0f}. Cada cartão mostra um nível associado a fundos, se o preço já chegou nele "
    "e quanto ainda precisaria cair. São referências diferentes, não uma promessa de preço."
)

pi_gap = cycle_repeat["pi_gap_pct"]
if cycle_repeat["pi_triggered"]:
    pi_label = "Alerta de topo ativo"
elif pi_gap <= 10:
    pi_label = "Linhas próximas"
else:
    pi_label = "Sem alerta de topo"
scenario_cross = cycle_repeat["pi_cross_date_scenario"]
weekly_200 = float(projection["smas"][200].dropna().iloc[-1])

balanced_price, _ = latest_value(df, "balanced_price")
terminal_price, _ = latest_value(df, "terminal_price")
lth_realized_price, _ = latest_value(df, "lth_realized_price")
gm_sma350, _ = latest_value(df, "gm_sma350")
gm_x2, _ = latest_value(df, "gm_x2")
gm_x2618, _ = latest_value(df, "gm_x2618")
hashribbons_state, _ = latest_value(df, "hashribbons")

bottom_levels = [
    ("Cycle Repeat", cycle_repeat["bottom_price"], f"Menor preço do cenário repetido · {cycle_repeat['bottom_date']:%m/%Y}"),
    ("Média de 2 anos", cycle_repeat["current_ma730"], "Zona histórica de compra quando o preço fica abaixo"),
    ("Piso do Power Law", cycle_repeat["current_power_lower"], "Limite inferior do corredor estatístico atual"),
    ("Preço realizado", float(realized_price), "Preço médio estimado pago pelas moedas da rede"),
    ("Média de 200 semanas", weekly_200, "Suporte de longo prazo acompanhado entre ciclos"),
]
if lth_realized_price is not None:
    bottom_levels.append(
        ("Preço pago por quem segura há anos", float(lth_realized_price),
         "Custo médio de quem não vende há muito tempo (LTH Realized Price)")
    )
if balanced_price is not None:
    bottom_levels.append(
        ("Preço equilibrado", float(balanced_price),
         "Modelo que soma custo de mineração e custo dos investidores (Balanced Price)")
    )
if gm_sma350 is not None:
    bottom_levels.append(
        ("Média de 350 dias", float(gm_sma350),
         "Base da régua Golden Ratio — abaixo dela, o preço está historicamente barato")
    )

rows = [bottom_levels[i:i + 3] for i in range(0, len(bottom_levels), 3)]
for row_levels in rows:
    cols = st.columns(3)
    for column, level in zip(cols, row_levels):
        with column:
            price_level_card(level[0], level[1], btc_price, level[2])

consenso = models_consensus({nome: preco for nome, preco, _ in bottom_levels})
if consenso:
    st.markdown("##### Consenso entre os modelos")
    cc1, cc2, cc3 = st.columns(3)
    cc1.metric("Mediana dos modelos", f"US$ {consenso['mediana']:,.0f}", help="O valor do meio entre todos os modelos de fundo acima — metade aponta mais alto, metade mais baixo.")
    cc2.metric("Faixa entre eles (US$)", f"{consenso['minimo']:,.0f} – {consenso['maximo']:,.0f}")
    cc3.metric("O quanto discordam", f"{consenso['dispersao_pct']:.0f}%", help="Diferença entre o modelo mais alto e o mais baixo, como % da mediana. Quanto maior, menos os modelos concordam entre si — trate com mais cautela.")
    st.caption("Cada modelo usa uma conta diferente pra estimar 'preço justo' ou 'fundo histórico'. Quando eles concordam (faixa estreita), a referência é mais forte. Quando discordam muito, é sinal de incerteza — nenhum modelo sozinho é garantia.")

sth_realized_price, _ = latest_value(df, "sth_realized_price")
regime = pnl_regime(df)

clock = projection["clock_1064_365"]
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(
        f'<div class="lens"><div class="lens-title">Relógio 1064/365 · somente data</div>'
        f'<div class="lens-score">{clock["bottom"]:%d/%m/%Y}</div>'
        f'<div style="color:#f59e0b;font-weight:800;margin-bottom:7px">● FALTAM {clock["days_to_bottom"]} DIAS</div>'
        f'<div class="lens-text">Não estima preço; mede 365 dias desde o topo provisório.</div></div>',
        unsafe_allow_html=True,
    )
with c2:
    if hashribbons_state == "Down":
        hr_color, hr_text = "#ef4444", "● MINERADORES EM DIFICULDADE"
        hr_detail = "Mineradores fracos estão desligando as máquinas. Historicamente isso acontece perto de fundos, mas o sinal de compra é quando isso virar 'Up' de novo — ainda não virou."
    elif hashribbons_state == "Up":
        hr_color, hr_text = "#22c55e", "● MINERADORES SE RECUPERANDO"
        hr_detail = "A capitulação dos mineradores passou. Se isso aconteceu logo depois de um período fraco, é historicamente um bom sinal (Hash Ribbons)."
    else:
        hr_color, hr_text = "#94a3b8", "● SEM DADO"
        hr_detail = "Sem informação sobre a saúde dos mineradores hoje."
    st.markdown(
        f'<div class="lens"><div class="lens-title">Saúde dos mineradores</div>'
        f'<div class="lens-score">{hashribbons_state or "N/D"}</div>'
        f'<div style="color:{hr_color};font-weight:800;margin-bottom:7px">{hr_text}</div>'
        f'<div class="lens-text">{hr_detail}</div></div>',
        unsafe_allow_html=True,
    )
with c3:
    if sth_realized_price is not None and lth_realized_price is not None:
        virou = sth_realized_price < lth_realized_price
        if virou:
            cross_color, cross_text = "#22c55e", "● QUEM COMPROU RECENTE PAGOU MENOS"
            cross_detail = "O custo médio de quem comprou nos últimos meses caiu abaixo do custo de quem segura há anos. Isso historicamente marca o fundo de um mercado em baixa — a alavancagem fraca já foi eliminada."
        else:
            cross_color, cross_text = "#94a3b8", "● SEM CRUZAMENTO"
            cross_detail = "Quem comprou recente ainda paga mais caro que quem segura há anos. Esse cruzamento (quando o custo de quem comprou recente cai abaixo do de quem segura há anos) costuma marcar fundos de mercado em baixa."
        st.markdown(
            f'<div class="lens"><div class="lens-title">Custo de quem comprou recente vs quem segura há anos</div>'
            f'<div class="lens-score">US$ {sth_realized_price:,.0f}</div>'
            f'<div style="color:{cross_color};font-weight:800;margin-bottom:7px">{cross_text}</div>'
            f'<div class="lens-text">{cross_detail}</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="lens"><div class="lens-title">Custo de quem comprou recente vs quem segura há anos</div>'
            '<div class="lens-score">N/D</div>'
            '<div class="lens-text">Ainda sem dado suficiente (esse indicador roda em rodízio, chega a cada poucos dias).</div></div>',
            unsafe_allow_html=True,
        )
with c4:
    if regime is not None:
        reg_color = "#22c55e" if regime["estado"] == "bull" else "#ef4444"
        reg_text = "● REGIME DE ALTA (aproximado)" if regime["estado"] == "bull" else "● REGIME DE BAIXA (aproximado)"
        st.markdown(
            f'<div class="lens"><div class="lens-title">Regime CryptoQuant (aproximado)</div>'
            f'<div class="lens-score">{regime["dias_no_regime"]} dias nesse regime</div>'
            f'<div style="color:{reg_color};font-weight:800;margin-bottom:7px">{reg_text}</div>'
            f'<div class="lens-text">NÃO é o dado real da CryptoQuant (fórmula deles é proprietária) — é uma '
            f'reconstrução nossa com a mesma ideia (MVRV+NUPL+SOPR vs média de 1 ano). Baseado em {regime["amostras"]} dias de histórico.</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="lens"><div class="lens-title">Regime CryptoQuant (aproximado)</div>'
            '<div class="lens-score">N/D</div>'
            '<div class="lens-text">Ainda não há histórico suficiente (precisa de LTH-SOPR e STH-SOPR, que rodam em rodízio) pra calcular essa aproximação.</div></div>',
            unsafe_allow_html=True,
        )

st.subheader("Zonas estimadas de liquidação")
oi_usd, _ = latest_value(df, "open_interest_usd")
funding_rate, _ = latest_value(df, "funding_rate")
st.caption(
    "Onde uma massa de posições alavancadas pode ser forçada a fechar se o preço bater ali. "
    "Não é o mapa de calor real da corretora (esse é dado pago e fechado) — é uma conta feita a partir do preço "
    "de hoje e das alavancagens mais usadas em corretoras de futuros (5x a 100x). Quanto mais alavancagem, mais perto do preço "
    "atual fica a zona de risco."
)

LEVERAGE_TIERS = [5, 10, 25, 50, 100]
zones = []
for lev in LEVERAGE_TIERS:
    zones.append({"lado": "Comprados (long)", "alavancagem": lev, "preco": btc_price * (1 - 1 / lev)})
    zones.append({"lado": "Vendidos (short)", "alavancagem": lev, "preco": btc_price * (1 + 1 / lev)})

liq_fig = go.Figure()
liq_fig.add_hline(y=btc_price, line_color="#f8fafc", line_width=2,
                   annotation_text=f"Preço agora · US$ {btc_price:,.0f}", annotation_position="right")
for z in zones:
    cor = "#ef4444" if z["lado"].startswith("Comprados") else "#22c55e"
    # alavancagens altas ficam mais "quentes" (mais perto do preço, liquidam com um movimento menor)
    intensidade = 1 - (LEVERAGE_TIERS.index(z["alavancagem"]) / len(LEVERAGE_TIERS)) * 0.7
    posicao = "left" if z["lado"].startswith("Comprados") else "right"
    liq_fig.add_hline(
        y=z["preco"], line_color=cor, line_width=1 + intensidade * 3, opacity=0.35 + intensidade * 0.5,
        annotation_text=f"{z['alavancagem']}x", annotation_position=posicao,
        annotation_font_size=10,
    )
y_min = min([btc_price] + [z["preco"] for z in zones]) * 0.97
y_max = max([btc_price] + [z["preco"] for z in zones]) * 1.03
liq_fig.update_layout(
    title="Zonas estimadas de liquidação por alavancagem, em torno do preço atual",
    height=380, margin={"l": 20, "r": 20, "t": 40, "b": 20},
    paper_bgcolor="#080c14", plot_bgcolor="#0b1220", font={"color": "#cbd5e1"},
    xaxis={"visible": False, "range": [0, 1]},
    yaxis={"title": "Preço estimado da zona (US$)", "range": [y_min, y_max]},
    showlegend=False,
)
st.plotly_chart(liq_fig, width="stretch")
with st.expander("Ver as zonas de liquidação em tabela (alternativa ao gráfico)"):
    st.dataframe(
        pd.DataFrame([{"Alavancagem": f"{z['alavancagem']}x", "Lado": z["lado"], "Preço estimado (US$)": round(z["preco"])} for z in zones]),
        hide_index=True, width="stretch",
    )

lz1, lz2 = st.columns(2)
lz1.metric(
    "Dinheiro alavancado em aberto (Binance)",
    f"US$ {oi_usd/1e9:.2f} bi" if oi_usd else "N/D",
    help=(
        "Open Interest: soma de todas as posições com alavancagem ainda abertas no futuro perpétuo de BTC "
        "na Binance. Quanto maior, mais dinheiro alavancado pode virar liquidação forçada se o preço se mover forte."
    ),
)
if funding_rate is not None:
    lado_maioria = "Comprados (alta)" if funding_rate > 0 else "Vendidos (baixa)"
    lz2.metric(
        "Maioria das contas está", lado_maioria, f"{funding_rate:.4f}% / 8h",
        help=(
            "Funding rate: taxa que quem está de um lado paga pra quem está do outro, a cada 8h, no futuro "
            "perpétuo. Positiva = mais gente comprada pagando pra segurar a posição (mercado inclinado pra alta). "
            "Negativa = mais gente vendida pagando (mercado inclinado pra baixa). Muita gente do mesmo lado é "
            "o combustível para uma liquidação em cadeia se o preço for contra a maioria."
        ),
    )
else:
    lz2.metric("Maioria das contas está", "N/D")
st.caption(
    "Se o preço cair até perto de uma linha vermelha, gente comprada com aquela alavancagem é liquidada "
    "à força (venda forçada, empurra o preço mais pra baixo ainda). Se subir até uma linha verde, é o "
    "inverso com quem está vendido. Fundos de mercado às vezes acontecem quando essa venda forçada "
    "some — os que iam vender à força já venderam."
)

st.subheader("Alertas de topo e planejamento de saída")
st.caption("Esta parte é somente sobre possível topo. Ela não entra na confirmação de fundo de hoje.")
t1, t2, t3, t4 = st.columns(4)
t1.metric("Cycle Repeat · possível topo", f"US$ {cycle_repeat['top_price']:,.0f}", cycle_repeat["top_date"].strftime("%m/%Y"))
t2.metric("Teto atual do Power Law", f"US$ {cycle_repeat['current_power_upper']:,.0f}")
t3.metric("Média de 2 anos × 5", f"US$ {cycle_repeat['current_ma730x5']:,.0f}")
t4.metric(
    "Pi Cycle hoje", pi_label, f"faltam {pi_gap:.1f}%",
    help=(
        "O Pi Cycle compara duas médias do preço: uma rápida (111 dias) e uma lenta, dobrada "
        "(350 dias × 2). Nas ultimas vezes, quando a rápida cruzou pra cima da lenta, isso "
        "bateu bem perto do topo do ciclo. Hoje a média rápida ainda está "
        f"{pi_gap:.1f}% abaixo da lenta — quando chegar a 0%, é o alerta."
    ),
)
st.caption(
    "Pi Cycle é só sobre topo, não sobre fundo. "
    + ("No cenário de repetição dos últimos 1.458 dias, cruzaria em "
       + scenario_cross.strftime("%m/%Y") + "."
       if scenario_cross else
       "No cenário de repetição dos últimos 1.458 dias, não chega a cruzar nos próximos 4 anos.")
)

u1, u2, u3 = st.columns(3)
if terminal_price is not None:
    u1.metric("Teto histórico de topos", f"US$ {terminal_price:,.0f}", help="Nível que marcou topos em ciclos anteriores (Terminal Price)")
if gm_x2 is not None:
    u2.metric("Régua Golden Ratio × 2", f"US$ {gm_x2:,.0f}", help="Dobro da média de 350 dias — banda intermediária de topo")
if gm_x2618 is not None:
    u3.metric("Régua Golden Ratio × 2,618", f"US$ {gm_x2618:,.0f}", help="Proporção áurea sobre a média de 350 dias — banda clássica de topo de ciclo")

st.subheader("Gráficos detalhados")
tab_cycle, tab_clock, tab_investor, tab_power, tab_pi = st.tabs(["Cenário de 1.458 dias", "Relógio 1064/365", "Média de 2 anos", "Power Law", "Pi Cycle Top"])
model = cycle_repeat["combined"]
model_view = model.tail(1458 * 2 + 200)
with tab_cycle:
    cycle_chart = go.Figure()
    past = model_view.loc[model_view["tipo"] == "historico"]
    future = model_view.loc[model_view["tipo"] == "cenario"]
    cycle_chart.add_trace(go.Scatter(x=past["data"], y=past["preco"], name="Preço real", line={"color":"#e5e7eb","width":1.4}))
    cycle_chart.add_trace(go.Scatter(x=future["data"], y=future["preco"], name="Cenário repetido", line={"color":"#22c55e","width":1.5}))
    cycle_chart.add_trace(go.Scatter(x=model_view["data"], y=model_view["ma200"], name="Média 200 dias", line={"color":"#f59e0b","width":2}))
    cycle_chart.add_trace(go.Scatter(x=model_view["data"], y=model_view["ma1458"], name="Média 1.458 dias", line={"color":"#3b82f6","width":2}))
    cycle_chart.add_vline(x=cycle_repeat["last_date"], line_color="#94a3b8", line_dash="dot", annotation_text="hoje")
    cycle_chart.add_annotation(x=cycle_repeat["bottom_date"], y=cycle_repeat["bottom_price"], text=f"fundo do cenário<br>US$ {cycle_repeat['bottom_price']:,.0f}", showarrow=True, arrowcolor="#22c55e")
    cycle_chart.add_annotation(x=cycle_repeat["top_date"], y=cycle_repeat["top_price"], text=f"topo do cenário<br>US$ {cycle_repeat['top_price']:,.0f}", showarrow=True, arrowcolor="#ef4444")
    cycle_chart.update_yaxes(type="log", title="Preço do BTC")
    cycle_chart.update_layout(title="Cenário de repetição dos últimos 1.458 dias", height=540, margin={"l":20,"r":20,"t":50,"b":20}, paper_bgcolor="#080c14", plot_bgcolor="#0b1220", font={"color":"#cbd5e1"}, hovermode="x unified", legend={"orientation":"h","y":1.08})
    st.plotly_chart(cycle_chart, width="stretch")
    st.info("Este não é um preço previsto: o gráfico pega as variações dos últimos 1.458 dias e repete a mesma sequência a partir de hoje.")

with tab_clock:
    clock_chart = go.Figure()
    clock_history = projection["work"].loc[projection["work"]["data"] >= pd.Timestamp("2014-01-01")]
    clock_chart.add_trace(go.Scatter(x=clock_history["data"], y=clock_history["preco"], name="Preço real", line={"color":"#e5e7eb","width":1.3}))
    for start, end, phase in projection["clock_1064_365"]["phases"]:
        is_up = "alta" in phase
        clock_chart.add_vrect(
            x0=start, x1=end,
            fillcolor="#166534" if is_up else "#7f1d1d",
            opacity=.20 if "projetada" not in phase else .12,
            line_width=0,
            annotation_text=("1.064 dias" if is_up else "365 dias") + (" · cenário" if "projetada" in phase else ""),
            annotation_position="top left",
        )
    clock_chart.add_vline(x=projection["last_date"], line_color="#94a3b8", line_dash="dot", annotation_text="hoje")
    clock_chart.add_vline(x=projection["clock_1064_365"]["bottom"], line_color="#22c55e", line_dash="dash", annotation_text="fundo pelo relógio")
    clock_chart.add_vline(x=projection["clock_1064_365"]["next_top"], line_color="#ef4444", line_dash="dash", annotation_text="próximo topo pelo relógio")
    clock_chart.update_yaxes(type="log", title="Preço do BTC")
    clock_chart.update_xaxes(range=[pd.Timestamp("2014-01-01"), projection["clock_1064_365"]["next_top"] + pd.Timedelta(days=60)])
    clock_chart.update_layout(title="Relógio de 1.064 dias (fundo→topo) e 365 dias (topo→fundo)", height=540, margin={"l":20,"r":20,"t":50,"b":20}, paper_bgcolor="#080c14", plot_bgcolor="#0b1220", font={"color":"#cbd5e1"}, hovermode="x unified", legend={"orientation":"h","y":1.08})
    st.plotly_chart(clock_chart, width="stretch")
    st.info(
        "Esse relógio usa somente datas. O topo atual é provisório: se surgir uma máxima mais alta, a contagem de 365 dias reinicia. "
        "Ele não prevê o preço do fundo nem entra novamente na nota, pois a janela pós-topo já considera esse tipo de evidência."
    )

with tab_investor:
    investor = model.loc[model["tipo"] == "historico"]
    investor_chart = go.Figure()
    investor_chart.add_trace(go.Scatter(x=investor["data"], y=investor["preco"], name="Preço real", line={"color":"#e5e7eb","width":1.2}))
    investor_chart.add_trace(go.Scatter(x=investor["data"], y=investor["ma730"], name="Média de 2 anos", line={"color":"#22c55e","width":2}))
    investor_chart.add_trace(go.Scatter(x=investor["data"], y=investor["ma730x5"], name="Média de 2 anos × 5", line={"color":"#ef4444","width":2}))
    show_2y_bands = st.toggle("Mostrar também os multiplicadores ×2, ×3 e ×4", value=False)
    if show_2y_bands:
        for multiple, color in ((2, "#fbbf24"), (3, "#fb923c"), (4, "#f87171")):
            investor_chart.add_trace(go.Scatter(x=investor["data"], y=investor[f"ma730x{multiple}"], name=f"Média 2 anos × {multiple}", line={"color":color,"width":1,"dash":"dot"}))
    investor_chart.update_yaxes(type="log", title="Preço do BTC")
    investor_chart.update_layout(title="Preço vs média de 2 anos (Investor Tool)", height=540, margin={"l":20,"r":20,"t":50,"b":20}, paper_bgcolor="#080c14", plot_bgcolor="#0b1220", font={"color":"#cbd5e1"}, hovermode="x unified", legend={"orientation":"h","y":1.08})
    st.plotly_chart(investor_chart, width="stretch")
    if cycle_repeat["investor_ratio"] <= 1:
        st.success("O preço está abaixo da média de 2 anos: zona histórica de compra deste indicador.")
    elif cycle_repeat["investor_ratio"] >= 5:
        st.error("O preço está acima de 5 vezes a média de 2 anos: zona histórica de realização deste indicador.")
    else:
        st.info(f"O preço está em {cycle_repeat['investor_ratio']:.2f}× a média de 2 anos: entre as zonas extremas de compra e venda.")

with tab_power:
    power_chart = go.Figure()
    power_chart.add_trace(go.Scatter(x=model["data"], y=model["power_upper"], name="Faixa superior", line={"color":"#ef4444","width":2}))
    power_chart.add_trace(go.Scatter(x=model["data"], y=model["power_center"], name="Valor central", line={"color":"#f59e0b","width":2}))
    power_chart.add_trace(go.Scatter(x=model["data"], y=model["power_lower"], name="Piso estatístico", line={"color":"#38bdf8","width":2}))
    power_actual = model.loc[model["tipo"] == "historico"]
    power_chart.add_trace(go.Scatter(x=power_actual["data"], y=power_actual["preco"], name="Preço real", line={"color":"#e5e7eb","width":1.2}))
    power_chart.add_vline(x=cycle_repeat["last_date"], line_color="#94a3b8", line_dash="dot", annotation_text="hoje")
    power_chart.update_yaxes(type="log", title="Preço do BTC")
    power_chart.update_layout(title="Corredor estatístico Power Law (regressão log-log)", height=540, margin={"l":20,"r":20,"t":50,"b":20}, paper_bgcolor="#080c14", plot_bgcolor="#0b1220", font={"color":"#cbd5e1"}, hovermode="x unified", legend={"orientation":"h","y":1.08})
    st.plotly_chart(power_chart, width="stretch")
    st.info(
        "O Power Law ajusta uma curva ao histórico diário em escala logarítmica. O piso, o centro e o teto são "
        "faixas estatísticas; o modelo não conhece notícias, liquidez, regulação ou mudanças na adoção."
    )

with tab_pi:
    pi_view = model.loc[model["data"] >= cycle_repeat["last_date"] - pd.Timedelta(days=2200)]
    pi_chart = go.Figure()
    actual_pi = pi_view.loc[pi_view["tipo"] == "historico"]
    future_pi = pi_view.loc[pi_view["tipo"] == "cenario"]
    pi_chart.add_trace(go.Scatter(x=actual_pi["data"], y=actual_pi["preco"], name="Preço real", line={"color":"#e5e7eb","width":1}))
    pi_chart.add_trace(go.Scatter(x=actual_pi["data"], y=actual_pi["pi111"], name="Média 111 dias", line={"color":"#f59e0b","width":2}))
    pi_chart.add_trace(go.Scatter(x=actual_pi["data"], y=actual_pi["pi350x2"], name="2 × média 350 dias", line={"color":"#22c55e","width":2}))
    pi_chart.add_trace(go.Scatter(x=future_pi["data"], y=future_pi["pi111"], name="111d no cenário", line={"color":"#f59e0b","width":1.5,"dash":"dot"}))
    pi_chart.add_trace(go.Scatter(x=future_pi["data"], y=future_pi["pi350x2"], name="350d × 2 no cenário", line={"color":"#22c55e","width":1.5,"dash":"dot"}))
    pi_chart.add_vline(x=cycle_repeat["last_date"], line_color="#94a3b8", line_dash="dot", annotation_text="hoje")
    if scenario_cross:
        pi_chart.add_vline(x=scenario_cross, line_color="#ef4444", line_dash="dash", annotation_text="possível alerta no cenário")
    pi_chart.update_yaxes(type="log", title="Preço do BTC")
    pi_chart.update_layout(title="Pi Cycle Top (SMA 111 dias × 2 SMA 350 dias)", height=540, margin={"l":20,"r":20,"t":50,"b":20}, paper_bgcolor="#080c14", plot_bgcolor="#0b1220", font={"color":"#cbd5e1"}, hovermode="x unified", legend={"orientation":"h","y":1.08})
    st.plotly_chart(pi_chart, width="stretch")
    st.info("O Pi Cycle dá alerta quando a média de 111 dias cruza para cima de duas vezes a média de 350 dias. Ele procura topo, não fundo.")

with st.expander("Para quem quiser ver a conta por trás"):
    a, b, c = st.columns(3)
    price, _ = latest_value(df, "preco")
    a.metric("Bitcoin agora", f"${price:,.0f}" if price else "N/D")
    b.metric(
        "Data provável pela conta do halving", f"{projection['halving']['central']:%d/%m/%Y}",
        help="Último halving (20/04/2024) + a média de dias que levou do halving até o fundo nos 3 ciclos anteriores.",
    )
    c.metric(
        "Data provável pela conta do topo", f"{projection['top']['central']:%d/%m/%Y}",
        help="Maior preço deste ciclo até agora + a média de dias que levou do topo até o fundo seguinte nos 3 ciclos anteriores.",
    )

    next_cross = projection["next_crossing"]
    next_pair = projection["next_crossing_pair"]
    if next_cross and next_pair:
        direction = projection["crossings"].get(next_pair, {}).get("direction")
        semanas_curta, semanas_longa = next_pair.split("/")
        sentido = "sobe acima" if direction == "alta" else "desce abaixo"
        st.metric(
            "Próximo cruzamento de médias semanais", f"{next_cross:%d/%m/%Y}",
            help=(
                f"É quando a média de {semanas_curta} semanas de preço deve cruzar a de "
                f"{semanas_longa} semanas: a rápida ({semanas_curta} sem.) {sentido} da lenta "
                f"({semanas_longa} sem.). Cruzamento pra cima costuma ser sinal de alta; pra "
                "baixo, de baixa. É uma projeção simples, supondo que as médias continuem no "
                "ritmo atual — pode não se confirmar."
            ),
        )
        st.caption(
            f"Médias de {semanas_curta} e {semanas_longa} semanas, projetando pra frente no "
            "ritmo de inclinação das últimas 8 semanas de cada uma."
        )
    else:
        st.metric("Próximo cruzamento de médias semanais", "Nenhum previsto")
        st.caption("Nas médias semanais acompanhadas (50, 100 e 200 semanas), nenhum cruzamento aparece nos próximos ~1,5 ano no ritmo atual.")

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

st.subheader("Saúde dos dados, calibração e mais")
st.caption("Essa parte é técnica — pra quem quiser conferir a origem, a idade e o histórico de acerto dos números do painel.")

with st.expander("Saúde dos dados — de onde vem cada número e há quanto tempo"):
    st.caption("Alguns indicadores entram em rodízio (não são buscados todo dia, pra respeitar o limite gratuito da fonte de dados). Aqui você vê exatamente quando cada um foi atualizado pela última vez.")
    if saude_dados:
        tabela_saude = pd.DataFrame([
            {
                "Indicador": plain(INDICATORS.get(h["coluna"], (h["coluna"],))[0]) if h["coluna"] in INDICATORS else h["coluna"],
                "Valor mais recente": f"{h['valor']:.4g}" if h["valor"] is not None else "N/D",
                "De quando": h["data"].strftime("%d/%m/%Y") if h["data"] is not None else "—",
                "Idade (dias)": h["idade_dias"] if h["idade_dias"] is not None else "—",
                "Status": h["status"],
            }
            for h in saude_dados
        ])
        st.dataframe(tabela_saude, hide_index=True, width="stretch")
    else:
        st.caption("Sem dados suficientes para montar essa tabela.")

with st.expander("Calibração histórica — quando a nota ficou alta, o preço realmente subiu depois?"):
    st.caption(
        "Isso é um teste honesto (walk-forward): olha só pro que já tinha acontecido até aquele dia, sem "
        "espiar o futuro. Toda vez que a nota de confirmação cruzou um limite no passado, o painel conferiu "
        "o que o preço fez de verdade nos dias seguintes."
    )
    calibracao = score_calibration(df, composite)
    if calibracao:
        linhas_cal = []
        for (limite, h), dado in sorted(calibracao.items()):
            linhas_cal.append({
                "Nota cruzou": f"{limite}+",
                "Prazo depois": f"{h} dias",
                "Vezes que aconteceu": dado["n"],
                "Subiu em % das vezes": f"{dado['subiu_pct']:.0f}%",
                "Retorno médio": f"{dado['retorno_medio_pct']:+.1f}%",
            })
        st.dataframe(pd.DataFrame(linhas_cal), hide_index=True, width="stretch")
        st.caption("Poucos cruzamentos no histórico curto do painel (~1 ano) — trate como indício, não como prova estatística forte.")
    else:
        st.caption("Ainda não há cruzamentos de limite suficientes no histórico disponível para calibrar.")

with st.expander("Glossário — o que cada sigla quer dizer"):
    glossario = {
        "MVRV / MVRV Z-Score": "Compara o valor de mercado do Bitcoin com o 'preço realizado' (quanto custou, em média, cada moeda em circulação, na hora em que ela se moveu pela última vez). Z-Score mede o quão fora do normal essa diferença está.",
        "NUPL": "Net Unrealized Profit/Loss — o lucro ou prejuízo médio (no papel, ainda não vendido) de quem tem BTC hoje.",
        "SOPR": "Spent Output Profit Ratio — quando alguém vende, o SOPR mostra se essa venda em média deu lucro (acima de 1) ou prejuízo (abaixo de 1).",
        "Puell Multiple": "Compara o quanto os mineradores estão faturando hoje (em dólar) com a média de 1 ano. Muito alto = mineradores ricos, historicamente perto de topos. Muito baixo = mineradores sofrendo, historicamente perto de fundos.",
        "Realized Price": "Preço médio pago por todas as moedas em circulação, calculado pela última vez que cada uma se moveu on-chain.",
        "Reserve Risk": "Compara o preço de hoje com o quanto os detentores antigos parecem confiantes (medido pela pouca movimentação das moedas deles).",
        "RHODL Ratio": "Compara o peso de moedas muito antigas com o de moedas muito novas na rede.",
        "Power Law": "Um modelo estatístico que ajusta uma curva ao histórico de preço do Bitcoin em escala logarítmica — usado para estimar corredores prováveis de preço no longo prazo.",
        "Pi Cycle Top": "Compara a média móvel de 111 dias com o dobro da média de 350 dias. Historicamente, quando a rápida cruza a lenta, marcou topos de ciclo.",
        "STH / LTH": "Short-Term Holder / Long-Term Holder — divide quem tem BTC entre quem comprou recentemente (menos de ~155 dias) e quem segura há mais tempo.",
        "AVIV Ratio": "Como o MVRV, mas ignorando moedas perdidas ou inativas há muito tempo — foca só em quem está de fato ativo no mercado.",
        "VDD Multiple": "Mede o quanto de valor (em dólar) está sendo movimentado por moedas antigas de uma vez. Picos altos historicamente marcam topos.",
        "Open Interest": "Soma de todas as posições com alavancagem ainda abertas no mercado futuro.",
        "Funding Rate": "Taxa que um lado (comprado ou vendido) paga pro outro, a cada 8h, nos contratos futuros perpétuos — mostra pra que lado o mercado está mais inclinado.",
        "Hash Ribbons": "Mostra se os mineradores estão desligando máquinas (capitulação) ou ligando de novo (recuperação).",
        "LTH % em lucro": "Percentual de todo o BTC segurado por detentores de longo prazo (LTH) que está com preço acima do que foi pago. Nos fundos de 2015, 2018, 2020 e 2022, esse número caiu para a faixa de 50%-75% antes de virar — quando cai muito, é sinal de que até quem segura há anos está sentindo dor, o que historicamente precede reversões.",
        "STH % da oferta": "Fatia de todo o Bitcoin em circulação que está em mãos de quem comprou há menos de ~155 dias. Quando essa fatia encolhe, quer dizer que sobrou pouca gente 'nova' segurando — historicamente aparece perto do fim de mercados de baixa (ou porque venderam e saíram, ou porque as moedas deles 'envelheceram' para virar LTH).",
        "Regime CryptoQuant (aproximado)": "Reconstrução nossa, inspirada no conceito público do indicador Bull-Bear da CryptoQuant (combina MVRV, NUPL e a diferença de lucro entre holders antigos e recentes, comparado com a média de 1 ano). NÃO é o número real deles — a fórmula exata é proprietária. Trate como uma segunda opinião aproximada, não como o dado oficial.",
    }
    for termo, explicacao in glossario.items():
        st.markdown(f"**{termo}** — {explicacao}")

with st.expander("Exportar dados"):
    st.caption("Baixe o histórico completo usado nessa leitura, junto com a nota composta calculada pra cada dia.")
    export_df = df.copy()
    export_df["data"] = export_df["data"].dt.strftime("%Y-%m-%d")
    csv_bytes = export_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Baixar histórico em CSV", data=csv_bytes,
        file_name=f"painel_fundo_btc_{as_of:%Y-%m-%d}.csv", mime="text/csv",
    )
    st.caption(f"Fonte dos dados: {source}. Data de referência: {as_of:%d/%m/%Y}.")

st.caption(
    "Fontes de dados: preço e indicadores técnicos via bitcoin-data.com e CoinGecko; Fear & Greed Index via "
    "Alternative.me; derivativos (Open Interest, funding) via CoinGecko; câmbio via Coinbase. Nenhuma fonte "
    "paga é usada — quando um dado não está disponível de graça, o painel mostra 'N/D' em vez de inventar."
)

st.caption(f"Dados de {source} · leitura do dia {as_of:%d/%m/%Y} · o painel se atualiza sozinho todo dia")
