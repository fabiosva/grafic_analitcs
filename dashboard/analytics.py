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
    hoje = pd.Timestamp(df["data"].iloc[-1])
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
