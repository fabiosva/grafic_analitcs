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
                   targets: list[tuple[str, float, str]]) -> list[dict]:
    rows = []
    for name, price_usd, horizon in targets:
        value = total_btc * price_usd * usd_brl_future
        profit = value - capital_brl
        rows.append({
            "Cenário": name,
            "Preço BTC (US$)": price_usd,
            "Horizonte": horizon,
            "Valor estimado (R$)": value,
            "Lucro bruto (R$)": profit,
            "Retorno": profit / capital_brl * 100 if capital_brl else np.nan,
        })
    return rows
