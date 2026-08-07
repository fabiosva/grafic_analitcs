"""
Backfill historico de indicadores BTC - roda uma vez manualmente.
Usa o mesmo calculo de score do collector.py, mas para o ultimo ano
(limitado pela cobertura gratuita de preco historico do CoinGecko).
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(__file__))
from collector import calcular_score  # noqa: E402

BD_BASE = "https://bitcoin-data.com/v1"
FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"
COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=365&interval=daily"

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


CACHE_DIR = os.environ.get("BACKFILL_CACHE_DIR")


def fetch_full(endpoint: str, cache_name: str = None) -> dict:
    if CACHE_DIR and cache_name:
        cache_path = os.path.join(CACHE_DIR, cache_name)
        if os.path.exists(cache_path):
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            return {item["d"]: item for item in data}
    r = requests.get(f"{BD_BASE}/{endpoint}", timeout=30)
    r.raise_for_status()
    data = r.json()
    return {item["d"]: item for item in data}


def fetch_fear_greed_by_date() -> dict:
    if CACHE_DIR and os.path.exists(os.path.join(CACHE_DIR, "fng.json")):
        with open(os.path.join(CACHE_DIR, "fng.json"), encoding="utf-8") as f:
            data = json.load(f)["data"]
    else:
        r = requests.get(FNG_URL, timeout=30)
        r.raise_for_status()
        data = r.json()["data"]
    out = {}
    for item in data:
        d = datetime.fromtimestamp(int(item["timestamp"]), tz=timezone.utc).strftime("%Y-%m-%d")
        out[d] = int(item["value"])
    return out


def fetch_price_by_date() -> dict:
    if CACHE_DIR and os.path.exists(os.path.join(CACHE_DIR, "cg.json")):
        with open(os.path.join(CACHE_DIR, "cg.json"), encoding="utf-8") as f:
            prices = json.load(f)["prices"]
    else:
        r = requests.get(COINGECKO_URL, timeout=30)
        r.raise_for_status()
        prices = r.json()["prices"]
    out = {}
    for ts_ms, price in prices:
        d = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        out[d] = price
    return out


def upsert_batch(registros: list):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    url = f"{SUPABASE_URL}/rest/v1/bottom_indicators"
    for i in range(0, len(registros), 100):
        chunk = registros[i:i + 100]
        r = requests.post(url, headers=headers, json=chunk, timeout=30)
        if r.status_code not in (200, 201):
            print(f"Erro Supabase (lote {i}): {r.status_code} {r.text}")
        else:
            print(f"Lote {i}-{i+len(chunk)} salvo.")


def main():
    print("Buscando historico on-chain...")
    mvrv = fetch_full("mvrv-zscore", "mvrv.json")
    nupl = fetch_full("nupl", "nupl.json")
    sopr = fetch_full("sopr", "sopr.json")
    realized = fetch_full("realized-price", "realized.json")
    puell = fetch_full("puell-multiple", "puell.json")
    ti = fetch_full("technical-indicators", "ti.json")

    print("Buscando Fear & Greed historico...")
    fng = fetch_fear_greed_by_date()

    print("Buscando preco historico (CoinGecko, ultimo ano)...")
    precos = fetch_price_by_date()

    print(f"Dias com preco disponivel: {len(precos)}")

    registros = []
    for data_str, preco in sorted(precos.items()):
        dados = {
            "preco": preco,
            "mvrv_zscore": mvrv.get(data_str, {}).get("mvrvZscore"),
            "nupl": nupl.get(data_str, {}).get("nupl"),
            "sopr": sopr.get(data_str, {}).get("sopr"),
            "realized_price": realized.get(data_str, {}).get("realizedPrice"),
            "puell_multiple": puell.get(data_str, {}).get("puellMultiple"),
            "fear_greed": fng.get(data_str),
            "rsi": ti.get(data_str, {}).get("rsi"),
            "sma50": ti.get(data_str, {}).get("sma50"),
            "sma200": ti.get(data_str, {}).get("sma200"),
        }
        score = calcular_score(dados)
        registro = {
            "data": data_str,
            **dados,
            **score,
            "condicoes": json.dumps(score["condicoes"]),
            "atualizado_em": datetime.now(timezone.utc).isoformat(),
        }
        registros.append(registro)

    print(f"Total de registros a salvar: {len(registros)}")
    upsert_batch(registros)
    print("Backfill concluido.")


if __name__ == "__main__":
    main()
