"""
Coletor de indicadores BTC - Painel de Fundo
Roda via GitHub Actions (cron diario)
Fontes 100% gratuitas: bitcoin-data.com, alternative.me, coinbase
"""
import requests
import json
import os
from datetime import datetime, timezone, timedelta

BD_BASE = "https://bitcoin-data.com/v1"
FNG_URL = "https://api.alternative.me/fng/?limit=1"
COINBASE_URL = "https://api.coinbase.com/v2/prices/BTC-USD/spot"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Halvings do Bitcoin e os fundos ciclicos que se seguiram a cada um.
# Usado para estimar heuristicamente uma janela temporal de proximo fundo.
HALVINGS = ["2012-11-28", "2016-07-09", "2020-05-11", "2024-04-20"]
FUNDOS_POS_HALVING = ["2015-01-14", "2018-12-15", "2022-11-21"]


def fetch_latest(endpoint: str, key: str):
    try:
        r = requests.get(f"{BD_BASE}/{endpoint}", timeout=15)
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        return data[-1].get(key)
    except Exception as e:
        print(f"Erro em {endpoint}: {e}")
        return None


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

    score_obrigatorias = (obrigatorias_ativas / 4) * 70
    score_final = min(100, score_obrigatorias + bonus)

    if obrigatorias_ativas == 4:
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
        "score_final": round(score_final, 1),
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
        "fear_greed": fetch_fear_greed(),
    }

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

    os.makedirs("data", exist_ok=True)
    with open("data/latest.json", "w", encoding="utf-8") as f:
        json.dump(registro, f, indent=2, ensure_ascii=False)

    print("=== Coleta finalizada ===")


if __name__ == "__main__":
    main()
