"""
数据分析工具 — 支撑压力位 + 资金流向
（数据获取已全部移至 server.py，此模块只做计算）
"""
import os
import pandas as pd
import warnings
warnings.filterwarnings("ignore")


def calculate_support_resistance(df, lookback=20):
    """支撑/压力位：斐波那契 + 均线"""
    if df is None or len(df) < lookback:
        return None
    recent = df.tail(lookback)
    hi = recent["high"].max()
    lo = recent["low"].min()
    cur = float(df["close"].iloc[-1])
    r = hi - lo

    levels = {
        "压力1": round(hi, 0),
        "压力2": round(lo + r * 0.786, 0),
        "中轴":  round(lo + r * 0.618, 0),
        "支撑1": round(lo + r * 0.382, 0),
        "支撑2": round(lo + r * 0.236, 0),
        "支撑3": round(lo, 0),
    }
    for n in [5, 10, 20]:
        if len(df) >= n:
            levels[f"MA{n}"] = round(df["close"].rolling(n).mean().iloc[-1], 0)

    return {"current_price": cur, "levels": levels, "range_high": hi, "range_low": lo}


def calculate_capital_flow(df, lookback=5):
    """成交量加权多空比"""
    if df is None or len(df) < lookback:
        return None
    r = df.tail(lookback).copy()
    r["is_bull"] = r["close"] > r["open"]
    bv = r.loc[r["is_bull"], "volume"].sum()
    sv = r.loc[~r["is_bull"], "volume"].sum()
    total = bv + sv
    if total == 0:
        return None
    bull = bv / total * 100
    signal = "多头主导" if bull > 60 else ("空头主导" if bull < 40 else "多空均衡")
    return {"bull_ratio": round(bull, 1), "bear_ratio": round(100 - bull, 1), "signal": signal}
