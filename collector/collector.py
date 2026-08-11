"""
Coletor de indicadores BTC - Painel de Fundo
Roda via GitHub Actions (cron diario)
Fontes 100% gratuitas: bitcoin-data.com, alternative.me, coinbase
"""
import requests
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))
from analytics import historical_analogs  # noqa: E402

BD_BASE = "https://bitcoin-data.com/v1"
FNG_URL = "https://api.alternative.me/fng/?limit=1"
COINBASE_URL = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
COINGECKO_DERIVATIVES_URL = "https://api.coingecko.com/api/v3/derivatives"
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Halvings do Bitcoin e os fundos ciclicos que se seguiram a cada um.
# Usado para estimar heuristicamente uma janela temporal de proximo fundo.
HALVINGS = ["2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20"]
FUNDOS_POS_HALVING = ["2015-01-14", "2018-12-15", "2022-11-21"]

# Modelos de preco de ciclo e capitulacao de mineradores. Sao os mesmos
# indicadores que o Bitcoin Magazine Pro publica, mas mudam devagar - nao
# faz diferenca busca-los todo dia.
#
# O plano gratuito da bitcoin-data.com da 10 requisicoes por hora e 15 por
# dia, e as metricas principais ja consomem 8. Por isso estes entram em
# rodizio: EXTRAS_POR_DIA por vez, cada um se renovando a cada 3 dias.
# Quando um deles nao e buscado (ou a API recusa), o painel simplesmente
# mantem o ultimo valor conhecido, que para modelos assim e suficiente.
EXTRAS = [
    ("cvdd", {"cvdd": "cvdd"}),
    ("balanced-price", {"balanced_price": "balancedPrice"}),
    ("terminal-price", {"terminal_price": "terminalPrice"}),
    ("lth-realized-price", {"lth_realized_price": "lthRealizedPrice"}),
    ("hashribbons", {"hashribbons": "hashribbons"}),
    ("golden-ratio-multiplier", {
        "gm_sma350": "sma350", "gm_x16": "x16", "gm_x2": "x2", "gm_x2618": "x2618",
    }),
    ("sth-mvrv", {"sth_mvrv": "sthMvrv"}),
    ("sth-mvrv-momentum", {"sth_mvrv_momentum": "sthMvrvMomentum"}),
    ("vdd-multiple", {"vdd_multiple": "vddMultiple"}),
    ("aviv", {"aviv": "aviv"}),
    ("sth-lth-ratio", {"sth_lth_ratio": "sthLthRatio"}),
    ("sth-realized-price", {"sth_realized_price": "sthRealizedPrice"}),
]
EXTRAS_POR_DIA = 2


def _num(valor):
    """Alguns endpoints devolvem numero como texto (ex.: lthRealizedPrice)."""
    if valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def fetch_row(endpoint: str):
    """Busca a linha mais recente inteira, para endpoints com varios campos."""
    for tentativa in range(3):
        try:
            r = requests.get(f"{BD_BASE}/{endpoint}/last", timeout=20)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else data[-1]
        except Exception as e:
            if tentativa == 2:
                print(f"Erro em {endpoint} apos 3 tentativas: {e}")
                return None
            time.sleep(1.5 * (tentativa + 1))


def coletar_extras(agora: datetime) -> dict:
    """Escolhe EXTRAS_POR_DIA metricas do rodizio com base na data."""
    total = len(EXTRAS)
    inicio = (agora.toordinal() * EXTRAS_POR_DIA) % total
    escolhidos = [EXTRAS[(inicio + i) % total] for i in range(min(EXTRAS_POR_DIA, total))]

    resultado = {}
    for endpoint, mapa in escolhidos:
        print(f"Rodizio do dia: buscando {endpoint}")
        linha = fetch_row(endpoint)
        if not linha:
            continue
        for coluna, campo in mapa.items():
            bruto = linha.get(campo)
            # hashribbons devolve o rotulo "Up"/"Down"; o resto e numerico.
            resultado[coluna] = bruto if coluna == "hashribbons" else _num(bruto)
    return resultado


def fetch_latest(endpoint: str, key: str):
    """Busca o ponto mais recente com retry e payload pequeno."""
    for attempt in range(3):
        try:
            r = requests.get(f"{BD_BASE}/{endpoint}/last", timeout=20)
            r.raise_for_status()
            data = r.json()
            return data.get(key) if isinstance(data, dict) else data[-1].get(key)
        except Exception as e:
            if attempt == 2:
                print(f"Erro em {endpoint} apos 3 tentativas: {e}")
                return None
            time.sleep(1.5 * (attempt + 1))


def fetch_fear_greed():
    try:
        r = requests.get(FNG_URL, timeout=15)
        r.raise_for_status()
        return int(r.json()["data"][0]["value"])
    except Exception as e:
        print(f"Erro Fear&Greed: {e}")
        return None


def fetch_price():
    try:
        r = requests.get(COINBASE_URL, timeout=15)
        r.raise_for_status()
        return float(r.json()["data"]["amount"])
    except Exception as e:
        print(f"Erro preco: {e}")
        return None


def fetch_derivativos():
    """Open Interest (USD) e funding rate do perpetuo BTCUSDT na Binance, via
    CoinGecko (agregador, nao bloqueia os IPs dos runners do GitHub Actions
    como as corretoras bloqueiam direto - ja testamos Binance e Bybit, ambas
    devolveram erro 451/403)."""
    try:
        r = requests.get(COINGECKO_DERIVATIVES_URL, timeout=20)
        r.raise_for_status()
        for item in r.json():
            if item.get("market") == "Binance (Futures)" and item.get("symbol") == "BTCUSDT":
                return {
                    "open_interest_usd": _num(item.get("open_interest")),
                    "funding_rate": _num(item.get("funding_rate")),
                }
        return {"open_interest_usd": None, "funding_rate": None}
    except Exception as e:
        print(f"Erro derivativos (Open Interest/funding): {e}")
        return {"open_interest_usd": None, "funding_rate": None}


def stoch_rsi(rsi_series: list, period: int = 14, smooth_k: int = 3, smooth_d: int = 3):
    """
    rsi_series: valores de RSI em ordem cronologica (mais antigo -> mais recente).
    Retorna (%K, %D) do StochRSI mais recente, ou (None, None) se nao houver dados suficientes.
    """
    validos = [v for v in rsi_series if v is not None]
    if len(validos) < period + smooth_k + smooth_d:
        return None, None

    stoch_vals = []
    for i in range(period - 1, len(validos)):
        janela = validos[i - period + 1:i + 1]
        lo, hi = min(janela), max(janela)
        if hi == lo:
            stoch_vals.append(0.0)
        else:
            stoch_vals.append((validos[i] - lo) / (hi - lo) * 100)

    def sma(vals, n):
        return [sum(vals[i - n + 1:i + 1]) / n for i in range(n - 1, len(vals))]

    k_vals = sma(stoch_vals, smooth_k)
    d_vals = sma(k_vals, smooth_d)
    if not k_vals or not d_vals:
        return None, None
    return round(k_vals[-1], 2), round(d_vals[-1], 2)


def ciclo_halving(hoje: datetime) -> dict:
    halvings = [datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc) for d in HALVINGS]
    fundos = [datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc) for d in FUNDOS_POS_HALVING]

    deltas_dias = [(f - h).days for h, f in zip(halvings, fundos)]
    media_dias = sum(deltas_dias) / len(deltas_dias)
    variancia = sum((d - media_dias) ** 2 for d in deltas_dias) / len(deltas_dias)
    desvio_dias = variancia ** 0.5

    ultimo_halving = max(h for h in halvings if h <= hoje)
    dias_desde_halving = (hoje - ultimo_halving).days

    estimativa = ultimo_halving + timedelta(days=media_dias)
    janela_inicio = ultimo_halving + timedelta(days=media_dias - desvio_dias)
    janela_fim = ultimo_halving + timedelta(days=media_dias + desvio_dias)

    return {
        "ultimo_halving": ultimo_halving.strftime("%Y-%m-%d"),
        "dias_desde_halving": dias_desde_halving,
        "fundo_estimado": estimativa.strftime("%Y-%m-%d"),
        "janela_estimada_inicio": janela_inicio.strftime("%Y-%m-%d"),
        "janela_estimada_fim": janela_fim.strftime("%Y-%m-%d"),
        "dias_ate_fundo_estimado": (estimativa - hoje).days,
    }


def calcular_score(dados: dict) -> dict:
    condicoes = {
        "mvrv_baixo": dados.get("mvrv_zscore") is not None and dados["mvrv_zscore"] < 0.3,
        "medo_extremo": dados.get("fear_greed") is not None and dados["fear_greed"] < 25,
        "rsi_sobrevendido": dados.get("rsi") is not None and dados["rsi"] < 35,
        "perto_realized_price": (
            dados.get("preco") is not None
            and dados.get("realized_price") is not None
            and dados["preco"] < dados["realized_price"] * 1.05
        ),
    }

    obrigatorias_ativas = sum(condicoes.values())
    obrigatorias_disponiveis = sum(
        [
            dados.get("mvrv_zscore") is not None,
            dados.get("fear_greed") is not None,
            dados.get("rsi") is not None,
            dados.get("preco") is not None and dados.get("realized_price") is not None,
        ]
    )

    bonus = 0
    if dados.get("nupl") is not None and dados["nupl"] < 0:
        bonus += 10
    if dados.get("sopr") is not None and dados["sopr"] < 1:
        bonus += 10
    if dados.get("puell_multiple") is not None and dados["puell_multiple"] < 0.5:
        bonus += 10
    if dados.get("stoch_rsi_k") is not None and dados["stoch_rsi_k"] < 20:
        bonus += 10
    if (
        dados.get("preco") is not None
        and dados.get("sma200") is not None
        and dados["preco"] < dados["sma200"]
    ):
        bonus += 10
    if dados.get("reserve_risk") is not None and dados["reserve_risk"] < 0.002:
        bonus += 10
    if dados.get("rhodl_ratio") is not None and dados["rhodl_ratio"] < 1000:
        bonus += 10

    score_obrigatorias = (obrigatorias_ativas / 4) * 70
    score_final = min(100, score_obrigatorias + bonus) if obrigatorias_disponiveis >= 3 else None

    if obrigatorias_disponiveis < 3:
        classificacao = "Dados insuficientes"
    elif obrigatorias_ativas == 4:
        classificacao = "FUNDO ESTRUTURAL"
    elif obrigatorias_ativas >= 2:
        classificacao = "Zona de acumulacao"
    elif obrigatorias_ativas == 1:
        classificacao = "Atencao"
    else:
        classificacao = "Neutro/Topo"

    return {
        "condicoes": condicoes,
        "obrigatorias_ativas": obrigatorias_ativas,
        "score_final": round(score_final, 1) if score_final is not None else None,
        "classificacao": classificacao,
    }


def salvar_supabase(registro: dict):
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("SUPABASE_URL/KEY nao configurados - pulando salvamento.")
        return
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    url = f"{SUPABASE_URL}/rest/v1/bottom_indicators"
    r = requests.post(url, headers=headers, json=registro, timeout=15)
    if r.status_code not in (200, 201):
        print(f"Erro Supabase: {r.status_code} {r.text}")
    else:
        print("Salvo no Supabase com sucesso.")


def fetch_history_df():
    """Busca o historico completo (data, preco, RSI, medias moveis) do Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    url = (
        f"{SUPABASE_URL}/rest/v1/bottom_indicators"
        "?select=data,preco,rsi,stoch_rsi_k,sma50,sma200&order=data.asc"
    )
    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        registros = r.json()
        if not registros:
            return None
        df = pd.DataFrame(registros)
        return df.dropna(subset=["data"]).sort_values("data").reset_index(drop=True)
    except Exception as e:
        print(f"Erro ao buscar historico para previsoes: {e}")
        return None


def registrar_previsoes(agora: datetime, df: pd.DataFrame):
    """Roda o mesmo raio-x de dias parecidos do painel e grava o palpite de hoje."""
    if df is None or len(df) < 50:
        print("Historico insuficiente para gerar previsoes hoje.")
        return
    analog = historical_analogs(df)
    if not analog:
        print("Sem dias parecidos suficientes para gerar previsoes hoje.")
        return

    hoje_str = agora.strftime("%Y-%m-%d")
    linhas = []
    for prazo_dias, dado in analog["horizontes"].items():
        data_alvo = (agora + timedelta(days=prazo_dias)).strftime("%Y-%m-%d")
        if dado["prob_alta"] >= 55:
            direcao = "Alta"
        elif dado["prob_alta"] <= 45:
            direcao = "Queda"
        else:
            direcao = "Neutro"
        linhas.append({
            "data_previsao": hoje_str,
            "prazo_dias": prazo_dias,
            "data_alvo": data_alvo,
            "direcao_prevista": direcao,
            "prob_alta": round(dado["prob_alta"], 1),
            "preco_no_dia": round(float(df["preco"].iloc[-1]), 2),
            "preco_alvo_estimado": round(dado["preco_alvo_medio"], 2),
            "n_amostras": dado["n_amostras"],
            "criado_em": agora.isoformat(),
        })

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    url = f"{SUPABASE_URL}/rest/v1/previsoes"
    r = requests.post(url, headers=headers, json=linhas, timeout=15)
    if r.status_code not in (200, 201):
        print(f"Erro ao salvar previsoes: {r.status_code} {r.text}")
    else:
        print(f"Previsoes de hoje gravadas ({len(linhas)} prazos).")


def avaliar_previsoes_vencidas(agora: datetime, df: pd.DataFrame):
    """Confere palpites cuja data_alvo ja chegou e ainda nao foram avaliados."""
    if df is None or not SUPABASE_URL or not SUPABASE_KEY:
        return
    hoje_str = agora.strftime("%Y-%m-%d")
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    url = (
        f"{SUPABASE_URL}/rest/v1/previsoes"
        f"?select=*&preco_real=is.null&data_alvo=lte.{hoje_str}"
    )
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        pendentes = r.json()
    except Exception as e:
        print(f"Erro ao buscar previsoes pendentes: {e}")
        return
    if not pendentes:
        print("Nenhuma previsao pendente de avaliacao.")
        return

    preco_por_data = dict(zip(df["data"], df["preco"]))
    datas_ordenadas = sorted(preco_por_data.keys())

    def preco_mais_proximo(data_alvo: str):
        # As fontes on-chain as vezes atrasam 1-2 dias; pega o ultimo preco
        # conhecido em ou antes da data alvo.
        candidatos = [d for d in datas_ordenadas if d <= data_alvo]
        return preco_por_data[candidatos[-1]] if candidatos else None

    patch_headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    avaliadas = 0
    for previsao in pendentes:
        preco_real = preco_mais_proximo(previsao["data_alvo"])
        if preco_real is None:
            continue
        preco_no_dia = previsao["preco_no_dia"]
        preco_alvo = previsao["preco_alvo_estimado"]
        variacao_real_pct = (preco_real / preco_no_dia - 1) * 100 if preco_no_dia else None
        direcao_real = "Alta" if variacao_real_pct and variacao_real_pct > 0 else "Queda"
        direcao_prevista = previsao["direcao_prevista"]
        if direcao_prevista == "Neutro":
            direcao_correta = variacao_real_pct is not None and abs(variacao_real_pct) < 2
        else:
            direcao_correta = direcao_prevista == direcao_real
        if direcao_prevista == "Alta":
            alvo_batido = preco_real >= preco_alvo
        elif direcao_prevista == "Queda":
            alvo_batido = preco_real <= preco_alvo
        else:
            alvo_batido = preco_alvo and abs(preco_real / preco_alvo - 1) < 0.02

        update = {
            "preco_real": round(preco_real, 2),
            "direcao_correta": direcao_correta,
            "alvo_batido": bool(alvo_batido),
            "variacao_real_pct": round(variacao_real_pct, 2) if variacao_real_pct is not None else None,
            "avaliado_em": agora.isoformat(),
        }
        patch_url = (
            f"{SUPABASE_URL}/rest/v1/previsoes"
            f"?data_previsao=eq.{previsao['data_previsao']}&prazo_dias=eq.{previsao['prazo_dias']}"
        )
        r = requests.patch(patch_url, headers=patch_headers, json=update, timeout=15)
        if r.status_code not in (200, 204):
            print(f"Erro ao avaliar previsao {previsao['data_previsao']}/{previsao['prazo_dias']}d: {r.status_code} {r.text}")
        else:
            avaliadas += 1
    print(f"Previsoes avaliadas agora: {avaliadas}/{len(pendentes)}")


def main():
    agora = datetime.now(timezone.utc)
    print(f"=== Coleta iniciada: {agora.isoformat()} ===")

    dados = {
        "preco": fetch_price(),
        "mvrv_zscore": fetch_latest("mvrv-zscore", "mvrvZscore"),
        "nupl": fetch_latest("nupl", "nupl"),
        "sopr": fetch_latest("sopr", "sopr"),
        "realized_price": fetch_latest("realized-price", "realizedPrice"),
        "puell_multiple": fetch_latest("puell-multiple", "puellMultiple"),
        "reserve_risk": fetch_latest("reserve-risk", "reserveRisk"),
        "rhodl_ratio": fetch_latest("rhodl-ratio", "rhodlRatio"),
        "fear_greed": fetch_fear_greed(),
    }
    dados.update(fetch_derivativos())

    try:
        r = requests.get(f"{BD_BASE}/technical-indicators", timeout=15)
        ti_full = r.json()
        ti = ti_full[-1]
        dados["rsi"] = ti.get("rsi")
        dados["sma50"] = ti.get("sma50")
        dados["sma200"] = ti.get("sma200")

        rsi_series = [item.get("rsi") for item in ti_full[-120:]]
        dados["stoch_rsi_k"], dados["stoch_rsi_d"] = stoch_rsi(rsi_series)
    except Exception as e:
        print(f"Erro technical-indicators: {e}")
        dados["rsi"] = dados["sma50"] = dados["sma200"] = None
        dados["stoch_rsi_k"] = dados["stoch_rsi_d"] = None

    dados.update(coletar_extras(agora))

    score = calcular_score(dados)
    halving = ciclo_halving(agora)

    registro = {
        "data": agora.strftime("%Y-%m-%d"),
        **dados,
        **score,
        **halving,
        "condicoes": json.dumps(score["condicoes"]),
        "atualizado_em": agora.isoformat(),
    }

    print(json.dumps(registro, indent=2, ensure_ascii=False))

    salvar_supabase(registro)

    historico_df = fetch_history_df()
    avaliar_previsoes_vencidas(agora, historico_df)
    registrar_previsoes(agora, historico_df)

    os.makedirs(DATA_DIR, exist_ok=True)
    latest_path = os.path.join(DATA_DIR, "latest.json")
    history_path = os.path.join(DATA_DIR, "history.json")
    prices_path = os.path.join(DATA_DIR, "price_history.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(registro, f, indent=2, ensure_ascii=False)

    history = []
    if os.path.exists(history_path):
        with open(history_path, encoding="utf-8") as f:
            history = json.load(f)
    history = [row for row in history if row.get("data") != registro["data"]]
    history.append(registro)
    history.sort(key=lambda row: row.get("data", ""))
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

    prices = []
    if os.path.exists(prices_path):
        with open(prices_path, encoding="utf-8") as f:
            prices = json.load(f)
    prices = [row for row in prices if row.get("data") != registro["data"]]
    prices.append({"data": registro["data"], "preco": registro["preco"]})
    prices.sort(key=lambda row: row.get("data", ""))
    with open(prices_path, "w", encoding="utf-8") as f:
        json.dump(prices, f, ensure_ascii=False)

    print("=== Coleta finalizada ===")


if __name__ == "__main__":
    main()
