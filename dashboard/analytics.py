"""Funcoes puras para transformar indicadores em sinais comparaveis."""
from __future__ import annotations

import numpy as np
import pandas as pd


LAST_HALVING = pd.Timestamp("2024-04-20")
HALVING_TO_BOTTOM_DAYS = np.array([777, 889, 924])
TOP_TO_BOTTOM_DAYS = np.array([406, 364, 378])
NEXT_HALVING_ESTIMATE = pd.Timestamp("2028-04-13")
NEXT_TOP_WINDOW = (
    NEXT_HALVING_ESTIMATE + pd.Timedelta(days=525),
    NEXT_HALVING_ESTIMATE + pd.Timedelta(days=546),
)

STRATEGY_ALLOCATIONS = {
    "Conservador": (0.10, 0.20, 0.45, 0.25),
    "Balanceado": (0.20, 0.20, 0.45, 0.15),
    "Agressivo": (0.35, 0.20, 0.35, 0.10),
}


INDICATORS = {
    "mvrv_zscore": ("MVRV Z-Score", 1.0, [0.0, 0.3, 1.5, 3.0], [100, 85, 35, 0]),
    "nupl": ("NUPL", 1.0, [-0.25, 0.0, 0.5, 0.75], [100, 80, 25, 0]),
    "sopr": ("SOPR", 1.0, [0.95, 0.99, 1.01, 1.08], [100, 80, 40, 0]),
    "puell_multiple": ("Puell Multiple", 1.0, [0.3, 0.5, 1.0, 2.5], [100, 85, 45, 0]),
    "fear_greed": ("Fear & Greed", 1.0, [10, 25, 50, 80], [100, 80, 40, 0]),
    "rsi": ("RSI diário", 1.0, [20, 35, 50, 75], [100, 80, 40, 0]),
    "price_realized_ratio": ("Preço / Realized", 1.0, [0.75, 1.05, 1.8, 3.0], [100, 80, 25, 0]),
    "stoch_rsi_k": ("StochRSI", 0.5, [10, 20, 50, 80], [100, 80, 40, 0]),
    "price_sma200_ratio": ("Preço / SMA 200", 0.75, [0.7, 1.0, 1.5, 2.0], [100, 70, 10, 0]),
    "reserve_risk": ("Reserve Risk", 0.75, [0.0005, 0.002, 0.01, 0.05], [100, 80, 30, 0]),
    "rhodl_ratio": ("RHODL Ratio", 0.75, [250, 1000, 10000, 100000], [100, 80, 35, 0]),
    "drawdown_365_pct": ("Drawdown anual", 0.75, [-75, -50, -25, 0], [100, 85, 45, 0]),
    "return_30d_pct": ("Retorno 30 dias", 0.5, [-40, -20, 0, 30], [100, 80, 40, 0]),
    "price_zscore_90d": ("Z-Score preço 90d", 0.5, [-2.5, -1.5, 0, 2], [100, 80, 40, 0]),
    "macd_hist_pct": ("MACD normalizado", 0.5, [-3, -1, 0, 3], [100, 80, 45, 0]),
    "sth_mvrv": ("STH-MVRV", 1.0, [0.7, 0.85, 1.5, 2.0], [100, 90, 30, 0]),
    "aviv": ("AVIV Ratio", 1.0, [0.4, 0.6, 2.0, 2.5], [100, 85, 25, 0]),
    "vdd_multiple": ("VDD Multiple", 0.75, [0.3, 0.75, 2.9, 4.0], [100, 85, 20, 0]),
    "percent_lth_in_profit": ("LTH % em lucro", 1.0, [50, 60, 90, 100], [100, 85, 20, 0]),
    "percent_sth_supply": ("STH % da oferta", 0.75, [15, 18, 25, 30], [100, 85, 30, 0]),
}

# Métricas coletadas em rodízio por causa do limite da API gratuita. Elas
# mudam devagar e podem usar a última observação por alguns dias, mas nunca
# indefinidamente. Os demais indicadores precisam de observação do próprio dia.
ROTATING_INDICATOR_MAX_AGE_DAYS = {
    "reserve_risk": 10,
    "rhodl_ratio": 10,
    "sth_mvrv": 10,
    "aviv": 10,
    "vdd_multiple": 10,
    "percent_lth_in_profit": 10,
    "lth_realized_price": 10,
    "sth_realized_price": 10,
    "hashribbons": 10,
    "supply_in_profit_pct": 10,
    "etf_btc_total": 10,
    "etf_flow_btc": 10,
    "btc_issued": 10,
    "thermo_cap": 10,
    "short_term_hodler_supply_btc": 10,
    "supply_current": 10,
}


def prepare_signal_history(df: pd.DataFrame) -> pd.DataFrame:
    """Preenche somente métricas lentas do rodízio, respeitando sua validade."""
    work = df.copy()
    if work.empty or "data" not in work:
        return work
    dates = pd.to_datetime(work["data"], errors="coerce").dt.tz_localize(None)
    work["data"] = dates
    for column, max_age in ROTATING_INDICATOR_MAX_AGE_DAYS.items():
        if column not in work:
            continue
        raw = pd.to_numeric(work[column], errors="coerce")
        observed_at = dates.where(raw.notna()).ffill()
        ages = (dates - observed_at).dt.days
        work[column] = raw.ffill().where(ages.between(0, max_age))
    return work


def build_signals(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Retorna sinais 0-100, confluencia ponderada e cobertura ponderada."""
    work = df.copy()
    price = pd.to_numeric(work.get("preco"), errors="coerce")
    work["price_realized_ratio"] = price / work.get("realized_price")
    work["price_sma200_ratio"] = price / work.get("sma200")

    # Sinais derivados: acrescentam contexto de mercado sem consumir novas chamadas de API.
    rolling_high = price.rolling(365, min_periods=60).max()
    rolling_mean = price.rolling(90, min_periods=45).mean()
    rolling_std = price.rolling(90, min_periods=45).std()
    ema12 = price.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = price.ewm(span=26, adjust=False, min_periods=26).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False, min_periods=9).mean()

    work["drawdown_365_pct"] = (price / rolling_high - 1) * 100
    work["return_30d_pct"] = price.pct_change(30, fill_method=None) * 100
    work["price_zscore_90d"] = (price - rolling_mean) / rolling_std.replace(0, np.nan)
    work["macd_hist_pct"] = (macd - macd_signal) / price * 100
    sth_supply_raw = work["short_term_hodler_supply_btc"] if "short_term_hodler_supply_btc" in work else pd.Series(np.nan, index=work.index)
    total_supply_raw = work["supply_current"] if "supply_current" in work else pd.Series(np.nan, index=work.index)
    sth_supply = pd.to_numeric(sth_supply_raw, errors="coerce")
    total_supply = pd.to_numeric(total_supply_raw, errors="coerce")
    work["percent_sth_supply"] = sth_supply / total_supply * 100

    signals = pd.DataFrame(index=work.index, dtype=float)
    weights = {}
    for column, (label, weight, x_points, y_points) in INDICATORS.items():
        raw_values = work[column] if column in work else pd.Series(np.nan, index=work.index)
        values = pd.to_numeric(raw_values, errors="coerce")
        signals[label] = values.map(
            lambda value: np.interp(value, x_points, y_points) if pd.notna(value) else np.nan
        )
        weights[label] = weight

    weight_series = pd.Series(weights)
    available_weight = signals.notna().mul(weight_series, axis=1).sum(axis=1)
    total_weight = float(weight_series.sum())
    composite = signals.mul(weight_series, axis=1).sum(axis=1) / available_weight.replace(0, np.nan)
    coverage = available_weight / total_weight * 100
    composite = composite.where(coverage >= 45)
    return signals, composite, coverage


def indicator_bottom_events(
    signals: pd.DataFrame,
    dates: pd.Series,
    since: pd.Timestamp | None = None,
    threshold: float = 75,
) -> list[dict]:
    """Resume se cada indicador entrou na sua zona histórica de fundo.

    O evento pertence ao indicador, não declara sozinho que o preço do BTC fez
    o fundo definitivo. ``triggered_at`` é a entrada mais recente na zona.
    """
    if signals.empty:
        return []
    date_series = pd.to_datetime(dates, errors="coerce").dt.tz_localize(None)
    rows = []
    for label in signals.columns:
        complete = pd.DataFrame({"data": date_series, "score": signals[label]})
        current_observation = complete.iloc[-1]["score"] if not complete.empty else np.nan
        frame = complete.dropna()
        if since is not None:
            frame = frame.loc[frame["data"] >= pd.Timestamp(since).tz_localize(None)]
        if frame.empty:
            rows.append({
                "indicator": label, "status": "no_data", "current_score": np.nan,
                "triggered_at": None, "peak_score": np.nan,
            })
            continue
        in_zone = frame["score"] >= threshold
        entries = frame.loc[in_zone & ~in_zone.shift(fill_value=False)]
        triggered_at = pd.Timestamp(entries.iloc[-1]["data"]) if not entries.empty else None
        current_score = float(current_observation) if pd.notna(current_observation) else np.nan
        if pd.isna(current_score):
            status = "stale_after_hit" if triggered_at is not None else "no_data"
        elif current_score >= threshold:
            status = "active"
        elif triggered_at is not None:
            status = "already_hit"
        else:
            status = "not_hit"
        rows.append({
            "indicator": label,
            "status": status,
            "current_score": current_score,
            "triggered_at": triggered_at,
            "peak_score": float(frame["score"].max()),
        })
    return rows


def assess_cycle_bottom(indicator_df: pd.DataFrame, price_df: pd.DataFrame | None = None) -> dict | None:
    """Testa se o menor fechamento depois do topo do ciclo ja virou um fundo.

    A funcao nao tenta adivinhar o menor preco futuro. Ela separa duas perguntas:
    houve capitulacao no menor fechamento observado e o mercado confirmou alguma
    recuperacao depois dele? O resultado e uma contagem de evidencias, nao uma
    probabilidade estatistica.
    """
    source = price_df if price_df is not None and not price_df.empty else indicator_df
    prices = source[["data", "preco"]].copy()
    prices["data"] = pd.to_datetime(prices["data"], errors="coerce").dt.tz_localize(None)
    prices["preco"] = pd.to_numeric(prices["preco"], errors="coerce")
    prices = prices.dropna().drop_duplicates("data", keep="last").sort_values("data")

    cycle = prices.loc[prices["data"] >= LAST_HALVING].copy()
    if len(cycle) < 60:
        return None
    top = cycle.loc[cycle["preco"].idxmax()]
    after_top = cycle.loc[cycle["data"] > top["data"]]
    if after_top.empty:
        return None
    candidate = after_top.loc[after_top["preco"].idxmin()]
    current = cycle.iloc[-1]

    indicators = indicator_df.copy()
    indicators["data"] = pd.to_datetime(indicators["data"], errors="coerce").dt.tz_localize(None)
    indicators = indicators.dropna(subset=["data"]).sort_values("data").reset_index(drop=True)
    if indicators.empty:
        return None
    nearest_pos = int((indicators["data"] - candidate["data"]).abs().idxmin())
    nearest = indicators.loc[nearest_pos]
    _, composite, signal_coverage = build_signals(indicators)
    candidate_score = float(composite.loc[nearest_pos]) if pd.notna(composite.loc[nearest_pos]) else np.nan
    candidate_coverage = float(signal_coverage.loc[nearest_pos])

    def number(row: pd.Series, name: str) -> float:
        value = pd.to_numeric(pd.Series([row.get(name)]), errors="coerce").iloc[0]
        return float(value) if pd.notna(value) else np.nan

    current_indicators = indicators.iloc[-1]
    current_price = float(current["preco"])
    candidate_price = float(candidate["preco"])
    rebound_pct = (current_price / candidate_price - 1) * 100
    drawdown_pct = (candidate_price / float(top["preco"]) - 1) * 100
    days_since = int((current["data"] - candidate["data"]).days)
    expected_days = max(1, days_since + 1)
    observed_days = int(prices.loc[
        (prices["data"] >= candidate["data"]) & (prices["data"] <= current["data"]), "data"
    ].nunique())
    observation_coverage = min(100.0, observed_days / expected_days * 100)

    fear_greed = number(nearest, "fear_greed")
    rsi = number(nearest, "rsi")
    mvrv = number(nearest, "mvrv_zscore")
    capitulation_inputs = [fear_greed <= 25, rsi <= 35, mvrv <= 0.30]
    capitulation_passed = sum(bool(value) for value in capitulation_inputs) >= 2
    sma50 = number(current_indicators, "sma50")
    sma200 = number(current_indicators, "sma200")

    evidence = [
        {
            "name": "Indicadores convergiram no mínimo",
            "passed": bool(pd.notna(candidate_score) and candidate_score >= 75),
            "detail": f"nota de fundo {candidate_score:.0f}/100" if pd.notna(candidate_score) else "sem nota suficiente",
        },
        {
            "name": "Houve capitulação",
            "passed": capitulation_passed,
            "detail": f"Fear & Greed {fear_greed:.0f}, RSI {rsi:.0f}, MVRV {mvrv:.2f}",
        },
        {
            "name": "Preco reagiu pelo menos 20%",
            "passed": rebound_pct >= 20,
            "detail": f"recuperação de {rebound_pct:+.1f}%",
        },
        {
            "name": "Mínimo resistiu por pelo menos 30 dias",
            "passed": days_since >= 30 and observation_coverage >= 75,
            "detail": f"{days_since} dias; {observation_coverage:.0f}% dos fechamentos observados",
        },
        {
            "name": "Preço recuperou a média de 50 dias",
            "passed": bool(pd.notna(sma50) and current_price > sma50),
            "detail": f"SMA 50 em US$ {sma50:,.0f}" if pd.notna(sma50) else "sem dado",
        },
        {
            "name": "Preço recuperou a média de 200 dias",
            "passed": bool(pd.notna(sma200) and current_price > sma200),
            "detail": f"SMA 200 em US$ {sma200:,.0f}" if pd.notna(sma200) else "sem dado",
        },
    ]
    evidence_passed = sum(int(item["passed"]) for item in evidence)
    if days_since == 0:
        status, label = "new_low", "Novo mínimo: ainda sem confirmação"
    elif evidence_passed >= 5:
        status, label = "strong", "Forte candidato: o fundo pode já ter acontecido"
    elif evidence_passed == 4:
        status, label = "probable", "Candidato relevante, ainda em confirmação"
    else:
        status, label = "uncertain", "Ainda não há evidência suficiente"

    return {
        "status": status,
        "label": label,
        "evidence": evidence,
        "evidence_passed": evidence_passed,
        "evidence_total": len(evidence),
        "top_date": pd.Timestamp(top["data"]),
        "top_price": float(top["preco"]),
        "candidate_date": pd.Timestamp(candidate["data"]),
        "candidate_price": candidate_price,
        "candidate_indicator_date": pd.Timestamp(nearest["data"]),
        "candidate_score": candidate_score,
        "candidate_coverage": candidate_coverage,
        "current_date": pd.Timestamp(current["data"]),
        "current_price": current_price,
        "rebound_pct": float(rebound_pct),
        "drawdown_pct": float(drawdown_pct),
        "days_since": days_since,
        "observation_coverage": float(observation_coverage),
        "sma50": sma50,
        "sma200": sma200,
    }


def classify(score: float | None, coverage: float) -> tuple[str, str]:
    if score is None or pd.isna(score) or coverage < 45:
        return "Dados insuficientes", "#94a3b8"
    if score >= 75:
        return "Confluência forte", "#22c55e"
    if score >= 55:
        return "Acumulação em formação", "#eab308"
    if score >= 35:
        return "Sem confirmação", "#f97316"
    return "Baixa confluência", "#ef4444"


def latest_value(df: pd.DataFrame, column: str):
    if column not in df:
        return None, None
    valid = df.loc[df[column].notna(), ["data", column]]
    if valid.empty:
        return None, None
    row = valid.iloc[-1]
    return row[column], pd.Timestamp(row["data"])


def _wilson_interval(sucessos: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de confianca de 95% (Wilson) pra uma proporcao com amostra pequena."""
    if n == 0:
        return (0.0, 100.0)
    p = sucessos / n
    denom = 1 + z ** 2 / n
    centro = p + z ** 2 / (2 * n)
    margem = z * ((p * (1 - p) / n + z ** 2 / (4 * n ** 2)) ** 0.5)
    lo = (centro - margem) / denom
    hi = (centro + margem) / denom
    return (max(0.0, lo * 100), min(100.0, hi * 100))


def historical_analogs(df: pd.DataFrame, k: int = 15, horizons=(3, 7, 14, 30)) -> dict | None:
    """
    Acha os K dias historicos mais parecidos com hoje (RSI, StochRSI, preco vs
    medias moveis, Z-Score de 90 dias) e olha o que o preco realmente fez nos
    dias seguintes a cada um deles.

    Os candidatos sao escolhidos exigindo pelo menos `max(horizons)` dias de
    distancia entre eles, pra evitar que o mesmo periodo historico (varios
    dias consecutivos parecidos) conte como se fossem N casos independentes
    quando na pratica e o mesmo episodio.

    Isso NAO e uma previsao: e frequencia historica em situacoes parecidas,
    com amostra pequena. O intervalo de confianca (Wilson, 95%) mostra o
    quanto essa frequencia pode estar variando so por acaso.
    """
    work = df.copy()
    price = pd.to_numeric(work["preco"], errors="coerce")

    features = pd.DataFrame(index=work.index)
    features["rsi"] = pd.to_numeric(work.get("rsi"), errors="coerce")
    features["stoch_rsi_k"] = pd.to_numeric(work.get("stoch_rsi_k"), errors="coerce")
    features["price_sma50"] = price / pd.to_numeric(work.get("sma50"), errors="coerce")
    features["price_sma200"] = price / pd.to_numeric(work.get("sma200"), errors="coerce")
    rolling_mean = price.rolling(90, min_periods=45).mean()
    rolling_std = price.rolling(90, min_periods=45).std()
    features["zscore_90d"] = (price - rolling_mean) / rolling_std.replace(0, np.nan)

    valid = features.dropna()
    if valid.empty:
        return None

    today_pos = len(work) - 1
    if today_pos not in valid.index:
        return None
    today_vec = valid.loc[today_pos]

    max_h = max(horizons)
    candidates = valid[valid.index <= today_pos - max_h - 1]
    if len(candidates) < k:
        return None

    mean, std = candidates.mean(), candidates.std().replace(0, np.nan)
    norm = (candidates - mean) / std
    today_norm = (today_vec - mean) / std
    dist = ((norm - today_norm) ** 2).sum(axis=1).pow(0.5).sort_values()

    # Selecao gulosa: so aceita um candidato se ele estiver a pelo menos
    # max_h dias de distancia de todos os ja escolhidos (episodios distintos).
    nearest = []
    for pos in dist.index:
        if all(abs(pos - escolhido) >= max_h for escolhido in nearest):
            nearest.append(pos)
        if len(nearest) >= k:
            break
    if len(nearest) < max(5, k // 2):
        return None  # poucos episodios de fato independentes no historico

    resultados = {}
    for h in horizons:
        retornos = []
        exemplos = []
        for pos in nearest:
            futuro_pos = pos + h
            if futuro_pos < len(work):
                preco_agora = price.iloc[pos]
                preco_futuro = price.iloc[futuro_pos]
                if pd.notna(preco_agora) and pd.notna(preco_futuro) and preco_agora > 0:
                    variacao = (preco_futuro / preco_agora - 1) * 100
                    retornos.append(variacao)
                    exemplos.append({
                        "data": work["data"].iloc[pos],
                        "preco_na_epoca": float(preco_agora),
                        "preco_depois": float(preco_futuro),
                        "variacao_pct": float(variacao),
                    })
        if not retornos:
            continue
        retornos = np.array(retornos)
        preco_hoje = float(price.iloc[today_pos])
        sucessos = int((retornos > 0).sum())
        ic_baixo, ic_alto = _wilson_interval(sucessos, len(retornos))
        resultados[h] = {
            "prob_alta": float((retornos > 0).mean() * 100),
            "prob_alta_ic_baixo": ic_baixo,
            "prob_alta_ic_alto": ic_alto,
            "inconclusivo": ic_baixo <= 50 <= ic_alto,
            "retorno_medio_pct": float(retornos.mean()),
            "retorno_mediano_pct": float(np.median(retornos)),
            "n_amostras": len(retornos),
            "preco_alvo_medio": preco_hoje * (1 + retornos.mean() / 100),
            "preco_alvo_mediano": preco_hoje * (1 + np.median(retornos) / 100),
            "exemplos": sorted(exemplos, key=lambda e: e["data"], reverse=True),
        }
    if not resultados:
        return None
    datas_vizinhas = work.loc[nearest, "data"].tolist()
    return {"horizontes": resultados, "datas_vizinhas": datas_vizinhas, "n_episodios": len(nearest)}


def _date_window(anchor: pd.Timestamp, samples: np.ndarray) -> dict:
    mean_days = float(samples.mean())
    std_days = float(samples.std())
    return {
        "central": anchor + pd.Timedelta(days=round(mean_days)),
        "start": anchor + pd.Timedelta(days=round(mean_days - std_days)),
        "end": anchor + pd.Timedelta(days=round(mean_days + std_days)),
        "mean_days": mean_days,
        "std_days": std_days,
    }


def build_cycle_projection(df: pd.DataFrame, horizon_days: int = 520) -> dict:
    """Projeta relogios de ciclo e SMAs semanais; nao projeta o preco."""
    work = df.copy()
    work["data"] = pd.to_datetime(work["data"]).dt.tz_localize(None)
    work["preco"] = pd.to_numeric(work["preco"], errors="coerce")
    work = work.dropna(subset=["data", "preco"]).sort_values("data").reset_index(drop=True)
    if len(work) < 200:
        raise ValueError("Sao necessarios ao menos 200 dias para projetar as medias")

    current_cycle = work.loc[work["data"] >= LAST_HALVING]
    top_row = current_cycle.loc[current_cycle["preco"].idxmax()]
    provisional_top = pd.Timestamp(top_row["data"])
    halving_window = _date_window(LAST_HALVING, HALVING_TO_BOTTOM_DAYS)
    top_window = _date_window(provisional_top, TOP_TO_BOTTOM_DAYS)

    consensus_start = max(halving_window["start"], top_window["start"])
    consensus_end = min(halving_window["end"], top_window["end"])
    if consensus_start <= consensus_end:
        consensus_central = consensus_start + (consensus_end - consensus_start) / 2
    else:
        consensus_start = min(halving_window["central"], top_window["central"])
        consensus_end = max(halving_window["central"], top_window["central"])
        consensus_central = consensus_start + (consensus_end - consensus_start) / 2

    weekly = work.set_index("data")["preco"].resample("W-SUN").last().dropna()
    if len(weekly) < 200:
        raise ValueError("Sao necessarias ao menos 200 semanas para projetar as medias")
    smas = {period: weekly.rolling(period).mean() for period in (50, 100, 200)}
    last_date = pd.Timestamp(work["data"].iloc[-1])
    horizon_weeks = int(np.ceil(horizon_days / 7))
    future_dates = pd.date_range(weekly.index[-1], periods=horizon_weeks + 1, freq="W-SUN")
    projected = {}
    slopes = {}
    for period, series in smas.items():
        recent = series.dropna().tail(8)
        slope = float(np.polyfit(np.arange(len(recent)), recent.to_numpy(), 1)[0])
        slopes[period] = slope
        projected[period] = pd.Series(
            recent.iloc[-1] + slope * np.arange(horizon_weeks + 1), index=future_dates
        ).where(lambda values: values > 0)

    crossings = {}
    for short, long in ((50, 100), (50, 200), (100, 200)):
        gap = float(smas[short].iloc[-1] - smas[long].iloc[-1])
        relative_slope = slopes[short] - slopes[long]
        weeks = -gap / relative_slope if relative_slope else np.nan
        if pd.notna(weeks) and 0 < weeks * 7 <= horizon_days:
            direction = "alta" if relative_slope > 0 else "baixa"
            crossings[f"{short}/{long}"] = {
                "date": weekly.index[-1] + pd.Timedelta(days=float(weeks * 7)),
                "direction": direction,
            }

    state_50_100 = smas[50] > smas[100]
    death_crosses = state_50_100.index[(state_50_100.shift(1) == True) & (state_50_100 == False)]
    last_death_cross = pd.Timestamp(death_crosses[-1]) if len(death_crosses) else None
    cycle_57w = last_death_cross + pd.Timedelta(weeks=57) if last_death_cross else None
    clock_bottom = provisional_top + pd.Timedelta(days=365)
    clock_next_top = clock_bottom + pd.Timedelta(days=1064)
    clock_phases = [
        (pd.Timestamp("2015-01-14"), pd.Timestamp("2017-12-16"), "alta"),
        (pd.Timestamp("2017-12-16"), pd.Timestamp("2018-12-15"), "baixa"),
        (pd.Timestamp("2018-12-15"), pd.Timestamp("2021-11-08"), "alta"),
        (pd.Timestamp("2021-11-08"), pd.Timestamp("2022-11-09"), "baixa"),
        (pd.Timestamp("2022-11-09"), provisional_top, "alta"),
        (provisional_top, clock_bottom, "baixa projetada"),
        (clock_bottom, clock_next_top, "alta projetada"),
    ]
    next_crossing_pair = None
    next_crossing = None
    if crossings:
        next_crossing_pair, crossing_data = min(crossings.items(), key=lambda item: item[1]["date"])
        next_crossing = crossing_data["date"]
    return {
        "work": work,
        "weekly": weekly,
        "smas": smas,
        "projected_smas": projected,
        "crossings": crossings,
        "next_crossing": next_crossing,
        "next_crossing_pair": next_crossing_pair,
        "last_death_cross": last_death_cross,
        "cycle_57w": cycle_57w,
        "provisional_top": provisional_top,
        "provisional_top_price": float(top_row["preco"]),
        "halving": halving_window,
        "top": top_window,
        "consensus_start": consensus_start,
        "consensus_end": consensus_end,
        "consensus_central": consensus_central,
        "last_date": last_date,
        "clock_1064_365": {
            "bottom": clock_bottom,
            "next_top": clock_next_top,
            "days_to_bottom": (clock_bottom.normalize() - last_date.normalize()).days,
            "phases": clock_phases,
        },
    }


def build_cycle_repeat(df: pd.DataFrame, cycle_days: int = 1458) -> dict:
    """Repete os retornos dos ultimos 1.458 dias como cenario, nao previsao."""
    work = df[["data", "preco"]].copy()
    work["data"] = pd.to_datetime(work["data"]).dt.tz_localize(None)
    work["preco"] = pd.to_numeric(work["preco"], errors="coerce")
    work = work.dropna().drop_duplicates("data", keep="last").sort_values("data")
    if len(work) < cycle_days + 1:
        raise ValueError(f"Sao necessarios ao menos {cycle_days + 1} dias de preco")

    repeated_returns = np.log(work["preco"]).diff().dropna().tail(cycle_days).to_numpy()
    last_date = pd.Timestamp(work["data"].iloc[-1])
    future_dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=cycle_days, freq="D")
    future_prices = float(work["preco"].iloc[-1]) * np.exp(np.cumsum(repeated_returns))
    future = pd.DataFrame({"data": future_dates, "preco": future_prices, "tipo": "cenario"})

    actual = work.copy()
    actual["tipo"] = "historico"
    combined = pd.concat([actual, future], ignore_index=True)
    combined["ma200"] = combined["preco"].rolling(200).mean()
    combined["ma730"] = combined["preco"].rolling(730).mean()
    for multiple in (2, 3, 4, 5):
        combined[f"ma730x{multiple}"] = combined["ma730"] * multiple
    combined["ma1458"] = combined["preco"].rolling(cycle_days).mean()
    combined["pi111"] = combined["preco"].rolling(111).mean()
    combined["pi350x2"] = combined["preco"].rolling(350).mean() * 2
    combined["ema150"] = combined["preco"].ewm(span=150, adjust=False).mean()
    combined["sma471x0745"] = combined["preco"].rolling(471).mean() * 0.745

    genesis = pd.Timestamp("2009-01-03")
    actual_days = (actual["data"] - genesis).dt.days.clip(lower=1)
    log_days = np.log10(actual_days)
    log_prices = np.log10(actual["preco"])
    power_slope, power_intercept = np.polyfit(log_days, log_prices, 1)
    residuals = log_prices - (power_intercept + power_slope * log_days)
    lower_offset, upper_offset = residuals.quantile([0.10, 0.90])
    all_days = (combined["data"] - genesis).dt.days.clip(lower=1)
    power_log = power_intercept + power_slope * np.log10(all_days)
    combined["power_center"] = 10 ** power_log
    combined["power_lower"] = 10 ** (power_log + lower_offset)
    combined["power_upper"] = 10 ** (power_log + upper_offset)

    current = combined.loc[combined["data"] == last_date].iloc[-1]
    investor_ratio = current["preco"] / current["ma730"]
    investor_score = np.interp(
        investor_ratio,
        [0.60, 1.00, 1.50, 3.00, 5.00],
        [100.0, 90.0, 55.0, 15.0, 0.0],
    )
    power_position = (
        np.log10(current["preco"]) - np.log10(current["power_lower"])
    ) / (
        np.log10(current["power_upper"]) - np.log10(current["power_lower"])
    )
    power_score = np.interp(
        power_position,
        [-0.25, 0.00, 0.50, 1.00, 1.25],
        [100.0, 90.0, 50.0, 10.0, 0.0],
    )
    pi_gap_pct = (current["pi350x2"] / current["pi111"] - 1) * 100
    future_mask = combined["data"] > last_date
    pi_above = combined["pi111"] >= combined["pi350x2"]
    pi_crosses = combined.loc[future_mask & pi_above & ~pi_above.shift(1, fill_value=False)]
    pi_cross_date = pd.Timestamp(pi_crosses.iloc[0]["data"]) if not pi_crosses.empty else None

    bottom = future.loc[future["preco"].idxmin()]
    top = future.loc[future["preco"].idxmax()]
    return {
        "combined": combined,
        "future": future,
        "last_date": last_date,
        "current_pi111": float(current["pi111"]),
        "current_pi350x2": float(current["pi350x2"]),
        "current_ema150": float(current["ema150"]),
        "current_sma471x0745": float(current["sma471x0745"]),
        "current_ma730": float(current["ma730"]),
        "current_ma730x5": float(current["ma730x5"]),
        "investor_ratio": float(investor_ratio),
        "investor_score": float(investor_score),
        "current_power_center": float(current["power_center"]),
        "current_power_lower": float(current["power_lower"]),
        "current_power_upper": float(current["power_upper"]),
        "power_position": float(power_position),
        "power_score": float(power_score),
        "power_slope": float(power_slope),
        "pi_gap_pct": float(pi_gap_pct),
        "pi_triggered": bool(current["pi111"] >= current["pi350x2"]),
        "pi_cross_date_scenario": pi_cross_date,
        "bottom_date": pd.Timestamp(bottom["data"]),
        "bottom_price": float(bottom["preco"]),
        "top_date": pd.Timestamp(top["data"]),
        "top_price": float(top["preco"]),
    }


def purchase_readiness(indicator_score: float, as_of: pd.Timestamp, window_start: pd.Timestamp, window_end: pd.Timestamp) -> dict:
    """Combina sinais atuais (75%) e proximidade temporal (25%)."""
    as_of = pd.Timestamp(as_of).normalize()
    if window_start <= as_of <= window_end:
        timing = 100.0
    elif as_of < window_start:
        distance = (window_start - as_of).days
        timing = max(20.0, 100 - distance / 180 * 60)
    else:
        distance = (as_of - window_end).days
        timing = max(20.0, 100 - distance / 180 * 60)
    score = indicator_score * 0.75 + timing * 0.25
    # Rotulo curto cabe no card; a frase inteira vai para o tooltip.
    if score >= 80:
        label, detail = "Bom momento", "Bom momento para começar a comprar aos poucos."
    elif score >= 60:
        label, detail = "Comprar pouco", "Dá para comprar um pouco agora e guardar o resto para depois."
    elif score >= 40:
        label, detail = "Quase lá", "Melhor comprar bem pouco ou esperar mais um pouco."
    else:
        label, detail = "Esperar", "Ainda é cedo para comprar. Melhor esperar."
    return {"score": score, "timing_score": timing, "label": label, "detail": detail}


def simulate_dca(capital_brl: float, current_price_usd: float, window_price_usd: float,
                 usd_brl: float, fee_pct: float, strategy: str,
                 readiness_score: float | None = None) -> dict:
    allocations = list(STRATEGY_ALLOCATIONS[strategy])
    # Faz a primeira parcela reagir ao painel sem transformar a regra em all-in.
    if readiness_score is not None and readiness_score >= 80:
        shift = min(0.10, allocations[3])
        allocations[0] += shift
        allocations[3] -= shift
    elif readiness_score is not None and readiness_score < 60:
        shift = min(0.10, max(0, allocations[0] - 0.05))
        allocations[0] -= shift
        allocations[3] += shift
    phases = [
        ("1. Comprar agora", allocations[0], current_price_usd),
        ("2. Comprar até chegar o período", allocations[1], (current_price_usd + window_price_usd) / 2),
        ("3. Comprar durante o período", allocations[2], window_price_usd),
        ("4. Guardar para quando confirmar", allocations[3], window_price_usd * 1.10),
    ]
    rows = []
    total_btc = 0.0
    for name, allocation, entry_price in phases:
        amount = capital_brl * allocation
        btc = amount * (1 - fee_pct / 100) / (entry_price * usd_brl)
        total_btc += btc
        rows.append({
            "Quando comprar": name,
            "%": allocation * 100,
            "Aporte (R$)": amount,
            "BTC estimado": btc,
            "Preço assumido (US$)": entry_price,
        })
    effective_entry = capital_brl / (total_btc * usd_brl) if total_btc else np.nan
    return {"rows": rows, "btc": total_btc, "effective_entry_usd": effective_entry,
            "allocations": allocations}


def simulate_exits(total_btc: float, capital_brl: float, usd_brl_future: float,
                   targets: list[tuple[str, float, str]],
                   custos_venda_pct: float = 0.0, imposto_pct: float = 0.0,
                   custodia_pct_ano: float = 0.0, anos_custodia: float = 0.0) -> list[dict]:
    """custos_venda_pct junta taxa de corretora + spread + slippage (tudo cobrado
    na hora de vender). custodia_pct_ano e cobrado sobre o capital investido,
    multiplicado pelos anos que ficou guardado ate esse cenario."""
    rows = []
    for name, price_usd, horizon in targets:
        valor_bruto = total_btc * price_usd * usd_brl_future
        custos_venda = valor_bruto * (custos_venda_pct / 100)
        custodia_total = capital_brl * (custodia_pct_ano / 100) * anos_custodia
        lucro_bruto = valor_bruto - custos_venda - capital_brl - custodia_total
        imposto = max(0.0, lucro_bruto) * (imposto_pct / 100)
        lucro_liquido = lucro_bruto - imposto
        valor_liquido = capital_brl + lucro_liquido
        rows.append({
            "Cenário": name,
            "Preço BTC (US$)": price_usd,
            "Horizonte": horizon,
            "Valor estimado (R$)": valor_liquido,
            "Lucro bruto (R$)": lucro_bruto,
            "Imposto (R$)": imposto,
            "Lucro líquido (R$)": lucro_liquido,
            "Retorno": lucro_liquido / capital_brl * 100 if capital_brl else np.nan,
        })
    return rows


def stress_fundo_mais_baixo(window_price_usd: float, quedas_extras_pct=(10, 20, 30)) -> list[dict]:
    """E se o fundo real vier mais baixo do que a estimativa usada no simulador?"""
    return [
        {
            "Se cair mais": f"{q}%",
            "Novo fundo possível (US$)": window_price_usd * (1 - q / 100),
        }
        for q in quedas_extras_pct
    ]


def data_health(df: pd.DataFrame) -> list[dict]:
    """Pra cada indicador usado no score, mostra o valor mais recente disponivel,
    de quando ele e, e ha quanto tempo (idade). Serve pra saber quando o painel
    esta usando um dado reciclado (rodizio) em vez de fresco."""
    if df.empty:
        return []
    # A idade precisa ser comparada com o calendario real. Usar a ultima linha
    # como "hoje" fazia um arquivo inteiro vencido parecer perfeitamente atual.
    hoje = pd.Timestamp.now().normalize()
    colunas = list(dict.fromkeys(list(INDICATORS.keys()) + ["fear_greed", "preco"]))
    linhas = []
    for coluna in colunas:
        if coluna not in df.columns:
            continue
        serie = df[["data", coluna]].dropna()
        if serie.empty:
            linhas.append({"coluna": coluna, "valor": None, "data": None, "idade_dias": None, "status": "sem dado"})
            continue
        ultimo = serie.iloc[-1]
        idade = (hoje - pd.Timestamp(ultimo["data"])).days
        if idade <= 1:
            status = "atual"
        elif idade <= 7:
            status = "levemente desatualizado"
        else:
            status = "desatualizado"
        linhas.append({
            "coluna": coluna,
            "valor": float(ultimo[coluna]),
            "data": pd.Timestamp(ultimo["data"]),
            "idade_dias": idade,
            "status": status,
        })
    return linhas


def score_calibration(df: pd.DataFrame, composite: pd.Series, thresholds=(60, 70, 80),
                       horizons=(7, 14, 30)) -> dict:
    """Walk-forward honesto: toda vez que a nota composta cruzou um limite no
    passado (usando so dados conhecidos ate aquele dia), o que o preco fez
    depois? Mostra se notas altas de fato precederam alta de preco."""
    price = pd.to_numeric(df["preco"], errors="coerce")
    resultados = {}
    for limite in thresholds:
        cruzou = (composite >= limite) & (composite.shift(1) < limite)
        posicoes = [i for i, v in cruzou.items() if v]
        for h in horizons:
            retornos = []
            for pos in posicoes:
                futuro = pos + h
                if futuro < len(df):
                    p0, p1 = price.iloc[pos], price.iloc[futuro]
                    if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                        retornos.append((p1 / p0 - 1) * 100)
            if retornos:
                arr = np.array(retornos)
                resultados[(limite, h)] = {
                    "n": len(arr),
                    "subiu_pct": float((arr > 0).mean() * 100),
                    "retorno_medio_pct": float(arr.mean()),
                }
    return resultados


def models_consensus(modelos: dict) -> dict | None:
    """Recebe {rotulo: preco} de varios modelos de fundo e resume mediana,
    minimo, maximo e o quanto eles discordam entre si."""
    valores = {k: v for k, v in modelos.items() if v is not None}
    if not valores:
        return None
    arr = np.array(list(valores.values()), dtype=float)
    mediana = float(np.median(arr))
    return {
        "modelos": valores,
        "mediana": mediana,
        "minimo": float(arr.min()),
        "maximo": float(arr.max()),
        "dispersao_pct": float((arr.max() - arr.min()) / mediana * 100) if mediana else 0.0,
    }


def bitbo_confirmation_summary(df: pd.DataFrame) -> dict:
    """Calcula confirmações inspiradas nos gráficos públicos do Bitbo.

    São mantidas fora da nota composta de fundo para evitar contar duas vezes
    preço realizado, MVRV e médias móveis. A função responde uma pergunta
    diferente: depois de ficar barato, o mercado começou a virar?
    """
    if df.empty:
        return {}
    work = df.copy()
    dates = pd.to_datetime(work.get("data"), errors="coerce")

    def numeric(column: str) -> pd.Series:
        raw = work[column] if column in work else pd.Series(np.nan, index=work.index)
        return pd.to_numeric(raw, errors="coerce")

    price = numeric("preco")
    realized = numeric("realized_price")
    price_ma50 = price.rolling(50, min_periods=35).mean()
    realized_ma50 = realized.rolling(50, min_periods=35).mean()
    marp50 = price_ma50 / realized_ma50.replace(0, np.nan)
    marp50_ma3 = marp50.rolling(3, min_periods=3).mean()
    marp_momentum = marp50 - marp50_ma3

    lth_realized = numeric("lth_realized_price")
    sth_realized = numeric("sth_realized_price")
    lth_mvrv_api = numeric("lth_mvrv")
    lth_mvrv_derived = price / lth_realized.replace(0, np.nan)
    lth_mvrv = lth_mvrv_api.combine_first(lth_mvrv_derived)
    sth_mvrv_api = numeric("sth_mvrv")
    sth_mvrv_derived = price / sth_realized.replace(0, np.nan)
    sth_mvrv = sth_mvrv_api.combine_first(sth_mvrv_derived)
    mvrv_spread = lth_mvrv - sth_mvrv
    cross_entries = (mvrv_spread < 0) & (mvrv_spread.shift(1) >= 0)
    cross_dates = dates.loc[cross_entries & dates.notna()]

    supply_profit = numeric("supply_in_profit_pct")
    supply_profit = supply_profit.where(supply_profit > 1, supply_profit * 100)
    etf_flow = numeric("etf_flow_btc")
    etf_total = numeric("etf_btc_total")
    issued = numeric("btc_issued")
    thermo_cap = numeric("thermo_cap")
    supply = numeric("supply_current")
    thermo_multiple = price * supply / thermo_cap.replace(0, np.nan)

    def last(series: pd.Series):
        valid = series.dropna()
        return float(valid.iloc[-1]) if not valid.empty else None

    marp_now = last(marp50)
    marp_momentum_now = last(marp_momentum)
    lth_now = last(lth_mvrv)
    sth_now = last(sth_mvrv)
    spread_now = last(mvrv_spread)
    etf_flow_now = last(etf_flow)
    issued_now = last(issued)
    return {
        "marp50": marp_now,
        "marp50_momentum": marp_momentum_now,
        "marp50_bullish": marp_momentum_now is not None and marp_momentum_now > 0,
        "lth_mvrv": lth_now,
        "sth_mvrv": sth_now,
        "mvrv_spread": spread_now,
        "mvrv_cross_confirmed": spread_now is not None and spread_now < 0,
        "mvrv_cross_date": pd.Timestamp(cross_dates.iloc[-1]) if not cross_dates.empty else None,
        "supply_in_profit_pct": last(supply_profit),
        "etf_flow_btc": etf_flow_now,
        "etf_btc_total": last(etf_total),
        "btc_issued": issued_now,
        "etf_absorption_ratio": (
            etf_flow_now / issued_now
            if etf_flow_now is not None and issued_now not in (None, 0)
            else None
        ),
        "thermocap_multiple": last(thermo_multiple),
    }


def weekly_market_filter(price_df: pd.DataFrame) -> dict:
    """Filtro semanal simples para evitar entrada forte contra resistência."""
    if price_df.empty or not {"data", "preco"}.issubset(price_df.columns):
        return {}
    work = price_df[["data", "preco"]].copy()
    work["data"] = pd.to_datetime(work["data"], errors="coerce")
    work["preco"] = pd.to_numeric(work["preco"], errors="coerce")
    work = work.dropna().drop_duplicates("data", keep="last").set_index("data").sort_index()
    weekly = work["preco"].resample("W-SUN").last().dropna()
    if len(weekly) < 50:
        return {}

    delta = weekly.diff()
    avg_gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    rsi_low = rsi.rolling(14, min_periods=14).min()
    rsi_high = rsi.rolling(14, min_periods=14).max()
    stoch = (rsi - rsi_low) / (rsi_high - rsi_low).replace(0, np.nan) * 100
    stoch_k = stoch.rolling(3, min_periods=3).mean()
    stoch_d = stoch_k.rolling(3, min_periods=3).mean()

    as_of = work.index[-1]
    return {
        "as_of": pd.Timestamp(as_of),
        "week_closed": pd.Timestamp(as_of).weekday() == 6,
        "price": float(weekly.iloc[-1]),
        "sma50": float(weekly.rolling(50).mean().iloc[-1]),
        "sma100": float(weekly.rolling(100).mean().iloc[-1]) if len(weekly) >= 100 else None,
        "sma200": float(weekly.rolling(200).mean().iloc[-1]) if len(weekly) >= 200 else None,
        "stoch_k": float(stoch_k.iloc[-1]) if pd.notna(stoch_k.iloc[-1]) else None,
        "stoch_d": float(stoch_d.iloc[-1]) if pd.notna(stoch_d.iloc[-1]) else None,
    }


def pnl_regime(df: pd.DataFrame) -> dict | None:
    """
    Aproximacao PROPRIA, inspirada no conceito publicamente descrito do
    'Bull-Bear Market Cycle Indicator' da CryptoQuant: eles juntam MVRV,
    NUPL e a comparacao entre SOPR de holders antigos e recentes num
    'indice de lucro/prejuizo', e comparam esse indice com a media dele
    mesmo nos ultimos 365 dias. A formula exata deles e proprietaria e
    NAO foi reproduzida fielmente aqui - isso e uma reconstrucao nossa
    com a mesma ideia geral, sem validacao contra o numero real deles.
    Por isso fica de fora da nota composta do painel, so como contexto.
    """
    work = df.copy()

    def coluna(nome):
        return work[nome] if nome in work else pd.Series(np.nan, index=work.index)

    def zscore(serie):
        serie = pd.to_numeric(serie, errors="coerce")
        return (serie - serie.mean()) / serie.std()

    z_mvrv = zscore(coluna("mvrv_zscore"))
    z_nupl = zscore(coluna("nupl"))
    sopr_delta = pd.to_numeric(coluna("lth_sopr"), errors="coerce") - pd.to_numeric(coluna("sth_sopr"), errors="coerce")
    z_sopr = zscore(sopr_delta)

    indice = pd.concat([z_mvrv, z_nupl, z_sopr], axis=1).mean(axis=1, skipna=True)
    media_365 = indice.rolling(365, min_periods=120).mean()
    sinal = indice - media_365

    validos = sinal.dropna()
    if validos.empty:
        return None
    atual = float(validos.iloc[-1])
    estado = "bull" if atual > 0 else "bear"
    trocas = (validos > 0) != (validos > 0).shift(1)
    trocas = trocas.fillna(False)
    posicoes_troca = list(validos.index[trocas])
    dias_no_regime = len(validos) - (list(validos.index).index(posicoes_troca[-1]) if posicoes_troca else 0)
    return {"estado": estado, "valor": atual, "dias_no_regime": int(dias_no_regime), "amostras": len(validos)}
