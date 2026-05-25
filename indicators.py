"""
沪深 A 股信号看板指标计算模块
来源：平安证券慧赢 TDX公式 → Python复现

已实现：
  1. 主图指标（破浪黄点 / 空仓绿点）
  2. 波段王（K/D动能柱 + 多/空文字状态）
"""

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────
# 工具函数：TDX 标准函数 Python 实现
# ─────────────────────────────────────────────

def ema(series, n):
    """指数移动平均，等价于 TDX EMA(series, n)"""
    return series.ewm(span=n, adjust=False).mean()


def ma(series, n):
    """简单移动平均，等价于 TDX MA(series, n)"""
    return series.rolling(n).mean()


def ref(series, n):
    """前N期数据，等价于 TDX REF(series, n)"""
    return series.shift(n)


def hhv(series, n):
    """N期最高值，等价于 TDX HHV(series, n)"""
    return series.rolling(n).max()


def llv(series, n):
    """N期最低值，等价于 TDX LLV(series, n)"""
    return series.rolling(n).min()


def cross(a, b):
    """上穿：前期 a<=b 且当期 a>b，等价于 TDX CROSS(a, b)"""
    return (ref(a, 1) <= ref(b, 1)) & (a > b)


def sma(series, n, m):
    """
    TDX SMA(X, N, M) = 威尔德平滑均值
    公式：Y = (M*X + (N-M)*Y') / N
    TDX 从第1根开始计算，无预热 NaN 期
    """
    result = series.copy().astype(float)
    alpha = m / n
    for i in range(1, len(series)):
        if pd.isna(result.iloc[i - 1]):
            result.iloc[i] = series.iloc[i]
        else:
            result.iloc[i] = alpha * series.iloc[i] + (1 - alpha) * result.iloc[i - 1]
    return result


# ─────────────────────────────────────────────
# 指标一：主图指标（破浪 / 空仓）
# 黄点 = 破浪 = 做多状态
# 绿点 = 空仓 = 做空状态
# ─────────────────────────────────────────────

def calc_main_signals(df):
    """
    输入：df 含 open/high/low/close 列（日线或分钟线）
    输出：原df 附加以下列
      M1-M5    : 五级叠加EMA均线
      支撑      : 动态支撑价位
      QRG      : 综合强度分(-50~+50)
      破浪      : True = 黄点做多状态
      空仓      : True = 绿点做空状态
    """
    c = df["close"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    o = df["open"].astype(float)

    out = df.copy()

    # 五级叠加EMA（沿用旧项目公式）
    out["M1"] = ema(c, 13)
    out["M2"] = ema(out["M1"], 3)
    out["M3"] = ema(out["M2"], 3)
    out["M4"] = ema(out["M3"], 3)
    out["M5"] = ema(out["M4"], 3)

    # 动态支撑（沿用旧项目公式）
    hlc = ref(ma((h + l + c) / 3, 10), 1)
    hv = ema(hhv(h, 10), 3)
    out["支撑"] = ema(hlc * 2 - hv, 3)

    # 综合强度评分 QRG（沿用旧项目公式）
    vc = (
        np.where(c >= out["M1"], 10, -10)
        + np.where(c >= out["M2"], 10, -10)
        + np.where(c >= out["M3"], 10, -10)
        + np.where(out["M1"] >= out["M2"], 10, -10)
        + np.where(out["M2"] >= out["M3"], 10, -10)
    )
    vc = pd.Series(vc, index=df.index)
    sn = (
        np.where(out["M5"] > ref(out["M5"], 1), 1, 0)
        * np.where(out["M4"] > ref(out["M4"], 1), 1, 0)
    )
    sn = pd.Series(sn, index=df.index)
    out["QRG"] = (vc - (1 - sn) * 10).clip(lower=-50)

    # 主图单项条件（沿用旧项目公式，增加带颜色语义的别名方便前端展示）
    out["破浪_黄点"] = cross(out["QRG"], pd.Series(-10, index=out.index))
    out["空仓_绿点"] = (out["QRG"] == -50) & (ref(out["QRG"], 1) >= -30)
    out["破浪"] = out["破浪_黄点"]
    out["空仓"] = out["空仓_绿点"]

    return out


# ─────────────────────────────────────────────
# 指标二：波段王（K/D 动能）
# ─────────────────────────────────────────────

def calc_bsd_wang(df):
    """
    波段王副图：K、D两条线 + 多空色块。
    计算逻辑保留旧项目公式复现。
    """
    c = df["close"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    out = df.copy()

    var1 = (c - llv(l, 15)) / (hhv(h, 15) - llv(l, 15)) * 100
    var3 = sma(var1, 5, 1)
    out["K"] = sma(var3, 3, 1)
    out["D"] = sma(out["K"], 3, 1)

    ma5 = ma(c, 5)
    out["波段王_多"] = cross(out["K"], out["D"]) & (c > ma5)
    out["波段王_空"] = cross(out["D"], out["K"])

    # 有 K/D 后再生成最终状态：主图单项条件 + 动能过滤
    if "破浪_黄点" in out.columns:
        out["破浪"] = out["破浪_黄点"] & (out["K"] > 30) & (out["K"] >= out["D"])
    if "空仓_绿点" in out.columns:
        out["空仓"] = out["空仓_绿点"] & (out["K"] < 80) & (out["K"] <= out["D"])

    return out


def get_latest_signals(df):
    """返回最新一根K线的信号状态 + 元信息。"""
    if df is None or len(df) == 0:
        return {}, {}

    work = calc_bsd_wang(calc_main_signals(df))
    last = work.iloc[-1]
    prev = work.iloc[-2] if len(work) >= 2 else last

    # 兼容内置公式列（破浪_黄点/空仓_绿点）和旧测试/插件常用列（破浪/空仓）。
    raw_long = bool(last.get("破浪_黄点", last.get("破浪", False)))
    raw_short = bool(last.get("空仓_绿点", last.get("空仓", False)))
    k = last.get("K")
    d = last.get("D")
    k_gt30 = bool(pd.notna(k) and k > 30)
    k_lt80 = bool(pd.notna(k) and k < 80)
    k_ge_d = bool(pd.notna(k) and pd.notna(d) and k >= d)
    k_le_d = bool(pd.notna(k) and pd.notna(d) and k <= d)

    sig = {
        "破浪_黄点": raw_long,
        "空仓_绿点": raw_short,
        "做多": raw_long and k_gt30 and k_ge_d,
        "做空": raw_short and k_lt80 and k_le_d,
    }
    meta = {
        "QRG": last.get("QRG"),
        "K": k,
        "D": d,
        "QRG_prev": prev.get("QRG"),
        "K_gt30": k_gt30,
        "K_lt80": k_lt80,
        "K_ge_D": k_ge_d,
        "K_le_D": k_le_d,
    }
    return sig, meta
