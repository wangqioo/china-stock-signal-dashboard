"""TDX 内置函数库 — Python 实现"""
import numpy as np
import pandas as pd


def EMA(series, n):
    return series.ewm(span=n, adjust=False).mean()


def MA(series, n):
    return series.rolling(int(n)).mean()


def SMA(series, n, m):
    result = series.copy().astype(float)
    alpha = m / n
    for i in range(1, len(series)):
        prev = result.iloc[i - 1]
        result.iloc[i] = alpha * series.iloc[i] + (1 - alpha) * (series.iloc[i] if pd.isna(prev) else prev)
    return result


def REF(series, n):
    return series.shift(int(n))


def HHV(series, n):
    return series.rolling(int(n)).max()


def LLV(series, n):
    return series.rolling(int(n)).min()


def CROSS(a, b):
    return (REF(a, 1) <= REF(b, 1)) & (a > b)


def IF(cond, a, b):
    if isinstance(cond, pd.Series):
        return pd.Series(np.where(cond, a if not isinstance(a, pd.Series) else a,
                                        b if not isinstance(b, pd.Series) else b),
                         index=cond.index)
    return a if cond else b


def ABS(series):
    return series.abs()


def MAX(a, b):
    if isinstance(a, pd.Series) or isinstance(b, pd.Series):
        a = a if isinstance(a, pd.Series) else pd.Series(a, index=b.index)
        b = b if isinstance(b, pd.Series) else pd.Series(b, index=a.index)
        return pd.concat([a, b], axis=1).max(axis=1)
    return max(a, b)


def MIN(a, b):
    if isinstance(a, pd.Series) or isinstance(b, pd.Series):
        a = a if isinstance(a, pd.Series) else pd.Series(a, index=b.index)
        b = b if isinstance(b, pd.Series) else pd.Series(b, index=a.index)
        return pd.concat([a, b], axis=1).min(axis=1)
    return min(a, b)


def STD(series, n):
    return series.rolling(int(n)).std()


def SUM(series, n):
    if n == 0:
        return series.cumsum()
    return series.rolling(int(n)).sum()


def COUNT(cond, n):
    return cond.astype(int).rolling(int(n)).sum()


def EVERY(cond, n):
    return cond.astype(int).rolling(int(n)).min().astype(bool)


def EXIST(cond, n):
    return cond.astype(int).rolling(int(n)).max().astype(bool)


def HHVBARS(series, n):
    """距最高值的周期数"""
    result = pd.Series(0, index=series.index)
    for i in range(len(series)):
        window = series.iloc[max(0, i - int(n) + 1): i + 1]
        result.iloc[i] = len(window) - 1 - window.values.argmax()
    return result


def LLVBARS(series, n):
    result = pd.Series(0, index=series.index)
    for i in range(len(series)):
        window = series.iloc[max(0, i - int(n) + 1): i + 1]
        result.iloc[i] = len(window) - 1 - window.values.argmin()
    return result


def SLOPE(series, n):
    return series.diff(int(n)) / int(n)


# 所有函数导出为字典，供解析器使用
BUILTIN_FUNCS = {
    'EMA': EMA, 'MA': MA, 'SMA': SMA,
    'REF': REF, 'HHV': HHV, 'LLV': LLV,
    'CROSS': CROSS, 'IF': IF,
    'ABS': ABS, 'MAX': MAX, 'MIN': MIN,
    'STD': STD, 'SUM': SUM,
    'COUNT': COUNT, 'EVERY': EVERY, 'EXIST': EXIST,
    'HHVBARS': HHVBARS, 'LLVBARS': LLVBARS,
    'SLOPE': SLOPE,
}
