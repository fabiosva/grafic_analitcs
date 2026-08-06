"""
Coletor de indicadores BTC - Painel de Fundo
Roda via GitHub Actions (cron diario)
Fontes 100% gratuitas: bitcoin-data.com, alternative.me, coinbase
"""
import requests
import json
import os
from datetime import datetime, timezone

BD_BASE = "https://bitcoin-data.com/v1"
FNG_URL = "https://api.alternative.me/fng/?limit=1"
COINBASE_URL = "https://api.coinbase.com/v2/prices/BTC-USD/spot"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


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
    print(f"=== Coleta iniciada: {datetime.now(timezone.utc).isoformat()} ===")

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
        ti = r.json()[-1]
        dados["rsi"] = ti.get("rsi")
        dados["sma50"] = ti.get("sma50")
        dados["sma200"] = ti.get("sma200")
    except Exception as e:
        print(f"Erro technical-indicators: {e}")
        dados["rsi"] = dados["sma50"] = dados["sma200"] = None

    score = calcular_score(dados)

    registro = {
        "data": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        **dados,
        **score,
        "condicoes": json.dumps(score["condicoes"]),
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
    }

    print(json.dumps(registro, indent=2, ensure_ascii=False))

    salvar_supabase(registro)

    os.makedirs("data", exist_ok=True)
    with open("data/latest.json", "w", encoding="utf-8") as f:
        json.dump(registro, f, indent=2, ensure_ascii=False)

    print("=== Coleta finalizada ===")


if __name__ == "__main__":
    main()
