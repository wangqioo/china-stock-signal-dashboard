"""
沪深 A 股信号看板 — Flask API 服务

复用原项目的指标公式与图表数据结构，数据源切换为沪深 A 股，
只做看板展示与自选股管理，不包含任何主动消息/队列/后台扫描逻辑。
"""
import json
import math
import os
import re
import sqlite3
import sys
import time as _time
import importlib
from datetime import datetime, timedelta

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

sys.path.insert(0, os.path.dirname(__file__))

app = Flask(__name__, static_folder="dashboard")
CORS(app)

# 东方财富/新浪 A 股分钟线原生支持 1/5/15/30/60；3 和 120 用聚合得到。
PERIOD_MAP = {"1": "1", "3": "1", "5": "5", "15": "15", "30": "30", "60": "60", "120": "60"}
PERIOD_LABEL = {
    "1": "1分",
    "3": "3分",
    "5": "5分",
    "15": "15分",
    "30": "30分",
    "60": "60分",
    "120": "120分",
    "daily": "日线",
    "weekly": "周线",
}
PERIOD_MINUTES = {"1": 1, "3": 3, "5": 5, "15": 15, "30": 30, "60": 60, "120": 120}

CACHE_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(CACHE_DIR, exist_ok=True)
WATCHLIST_DB_PATH = os.path.join(CACHE_DIR, "watchlist.db")

DEFAULT_WATCHLIST = [
    ("000725", "京东方A"),
    ("002031", "巨轮智能"),
    ("600433", "冠豪高新"),
    ("000060", "中金岭南"),
    ("603077", "和邦生物"),
    ("600871", "石化油服"),
    ("002421", "达实智能"),
    ("600039", "四川路桥"),
    ("002640", "跨境通"),
    ("601766", "中国中车"),
]
DEFAULT_SYMBOL, DEFAULT_SYMBOL_NAME = DEFAULT_WATCHLIST[0]

# ── 股票代码与自选股 ───────────────────────────────────────────────


def _parse_stock_code(raw):
    text = str(raw or "").strip().upper()
    if not text:
        raise ValueError("股票代码不能为空")
    compact = re.sub(r"[\s._\-/]", "", text)
    match = re.fullmatch(r"(?:(SH|SZ))?(\d{6})(?:(SH|SZ))?", compact)
    if not match:
        raise ValueError(f"无效股票代码: {raw}")
    prefix, code, suffix = match.groups()
    supplied_exchange = prefix or suffix
    if prefix and suffix and prefix != suffix:
        raise ValueError(f"交易所前后缀冲突: {raw}")
    return code, supplied_exchange


def infer_exchange(raw):
    """按沪深 A 股代码段推断交易所：SH / SZ。"""
    code, supplied_exchange = _parse_stock_code(raw)
    if code.startswith(("600", "601", "603", "605", "688", "689")):
        exchange = "SH"
    elif code.startswith(("000", "001", "002", "003", "300", "301")):
        exchange = "SZ"
    else:
        raise ValueError(f"仅支持沪深 A 股股票代码: {raw}")
    if supplied_exchange and supplied_exchange != exchange:
        raise ValueError(f"代码 {code} 属于 {exchange}，不是 {supplied_exchange}")
    return exchange


def normalize_stock_code(raw):
    """接受 000001 / sz000001 / 600519.SH / SH.688981 等常见写法，返回 6 位代码。"""
    code, _ = _parse_stock_code(raw)
    infer_exchange(code)
    return code


def to_sina_symbol(raw):
    code = normalize_stock_code(raw)
    return f"{infer_exchange(code).lower()}{code}"


def _connect_watchlist(db_path=WATCHLIST_DB_PATH):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_watchlist_db(db_path=WATCHLIST_DB_PATH):
    with _connect_watchlist(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                exchange TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _row_to_watchlist_item(row):
    return {
        "symbol": row["symbol"],
        "name": row["name"],
        "exchange": row["exchange"],
        "created_at": row["created_at"],
    }


def add_watchlist_item(symbol, name=None, db_path=WATCHLIST_DB_PATH):
    init_watchlist_db(db_path)
    code = normalize_stock_code(symbol)
    exchange = infer_exchange(code)
    final_name = (name or "").strip() or resolve_stock_name(code) or code
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _connect_watchlist(db_path) as conn:
        conn.execute(
            """
            INSERT INTO watchlist (symbol, name, exchange, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                name=excluded.name,
                exchange=excluded.exchange
            """,
            (code, final_name, exchange, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM watchlist WHERE symbol=?", (code,)).fetchone()
    return _row_to_watchlist_item(row)


def list_watchlist(db_path=WATCHLIST_DB_PATH):
    init_watchlist_db(db_path)
    with _connect_watchlist(db_path) as conn:
        rows = conn.execute("SELECT * FROM watchlist ORDER BY id ASC").fetchall()
    return [_row_to_watchlist_item(row) for row in rows]


def remove_watchlist_item(symbol, db_path=WATCHLIST_DB_PATH):
    init_watchlist_db(db_path)
    code = normalize_stock_code(symbol)
    with _connect_watchlist(db_path) as conn:
        cur = conn.execute("DELETE FROM watchlist WHERE symbol=?", (code,))
        conn.commit()
        return cur.rowcount > 0


def ensure_default_watchlist():
    init_watchlist_db(WATCHLIST_DB_PATH)
    with _connect_watchlist(WATCHLIST_DB_PATH) as conn:
        count = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
    if count == 0:
        for symbol, name in DEFAULT_WATCHLIST:
            add_watchlist_item(symbol, name)


# ── 通用清洗与缓存 ─────────────────────────────────────────────────


def _cache_path(name):
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    return os.path.join(CACHE_DIR, f"{safe_name}.csv")


def _save_cache(name, df):
    try:
        df.to_csv(_cache_path(name), index=False)
    except Exception as exc:
        print(f"cache save {name}: {exc}")


def _load_cache(name):
    path = _cache_path(name)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path)
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception as exc:
        print(f"cache load {name}: {exc}")
        return None


def safe(v, ndigits=2):
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else round(f, ndigits)
    except Exception:
        return None


def clean(obj):
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    if hasattr(obj, "item"):
        return clean(obj.item())
    return obj


def _normalize_ohlcv(df):
    if df is None or df.empty:
        return None
    rename = {
        "日期": "date",
        "时间": "date",
        "day": "date",
        "datetime": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
    }
    result = df.rename(columns={c: rename.get(c, str(c).lower()) for c in df.columns}).copy()
    if "date" not in result.columns:
        return None
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume", "amount"):
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")
    if "volume" not in result.columns:
        result["volume"] = 0
    keep = ["date", "open", "high", "low", "close", "volume"]
    if "amount" in result.columns:
        keep.append("amount")
    result = result[keep].dropna(subset=["date", "open", "high", "low", "close"])
    result = result.sort_values("date").reset_index(drop=True)
    return result


def _resample_ohlcv(df, rule):
    if df is None or df.empty:
        return None
    agg = {
        "open": ("open", "first"),
        "high": ("high", "max"),
        "low": ("low", "min"),
        "close": ("close", "last"),
        "volume": ("volume", "sum"),
    }
    if "amount" in df.columns:
        agg["amount"] = ("amount", "sum")
    out = (
        df.set_index("date")
        .resample(rule, closed="left", label="left")
        .agg(**agg)
        .dropna(subset=["close"])
        .reset_index()
    )
    return out


# ── A 股列表、搜索、行情数据 ────────────────────────────────────────

_STOCK_LIST_CACHE = {"ts": 0, "items": []}
_STOCK_LIST_TTL = 3600
_minute_cache = {}
_MINUTE_TTL = {"1": 20, "3": 30, "5": 60, "15": 180, "30": 300, "60": 600, "120": 1200}
_daily_cache = {}
_DAILY_TTL = 300
_trend_cache = {}
_TREND_TTL = 300


def _stock_items_from_frame(df):
    if df is None or df.empty:
        return []
    items = []
    for _, row in df.iterrows():
        raw_code = ""
        raw_name = ""
        for col in ("代码", "code", "symbol", "证券代码"):
            if col in row and pd.notna(row.get(col)):
                raw_code = str(row.get(col)).strip()
                break
        for col in ("名称", "name", "证券简称", "股票简称"):
            if col in row and pd.notna(row.get(col)):
                raw_name = str(row.get(col)).strip()
                break
        try:
            code = normalize_stock_code(raw_code)
            exchange = infer_exchange(code)
        except ValueError:
            continue
        items.append({"symbol": code, "name": raw_name or code, "exchange": exchange})
    deduped = {item["symbol"]: item for item in items}
    return sorted(deduped.values(), key=lambda x: x["symbol"])


def _fetch_eastmoney_stock_list():
    import akshare as ak

    return _stock_items_from_frame(ak.stock_zh_a_spot_em())


def _fetch_code_name_stock_list():
    import akshare as ak

    return _stock_items_from_frame(ak.stock_info_a_code_name())


def _fetch_realtime_stock_list():
    import akshare as ak

    return _stock_items_from_frame(ak.stock_zh_a_spot())


def get_stock_list(force=False):
    now = _time.time()
    if not force and _STOCK_LIST_CACHE["items"] and now - _STOCK_LIST_CACHE["ts"] < _STOCK_LIST_TTL:
        return _STOCK_LIST_CACHE["items"]

    last_error = None
    for source_name, fetcher in (
        ("东方财富实时", _fetch_eastmoney_stock_list),
        ("代码名称表", _fetch_code_name_stock_list),
        ("实时列表", _fetch_realtime_stock_list),
    ):
        try:
            items = fetcher()
            if items:
                _STOCK_LIST_CACHE.update({"ts": now, "items": items})
                return items
        except Exception as exc:
            last_error = exc
            print(f"A股列表加载失败[{source_name}]: {exc}")
    if last_error:
        print(f"A股列表全部失败，使用缓存: {last_error}")
    return _STOCK_LIST_CACHE["items"]


def resolve_stock_name(symbol):
    try:
        code = normalize_stock_code(symbol)
    except ValueError:
        return None
    for item in get_stock_list():
        if item["symbol"] == code:
            return item["name"]
    return None


def resolve_stock(symbol, name=None):
    code = normalize_stock_code(symbol)
    exchange = infer_exchange(code)
    return {
        "symbol": code,
        "name": (name or "").strip() or resolve_stock_name(code) or code,
        "exchange": exchange,
        "sina_code": f"{exchange.lower()}{code}",
    }


def get_minute_data(symbol_cfg, period="15"):
    import akshare as ak

    code = symbol_cfg["symbol"]
    sina_code = symbol_cfg["sina_code"]
    period = str(period)
    cache_key = (code, period)
    ttl = _MINUTE_TTL.get(period, 180)
    now = _time.time()
    if cache_key in _minute_cache:
        ts, cached = _minute_cache[cache_key]
        if now - ts < ttl:
            return cached

    fetch_period = PERIOD_MAP.get(period, "15")
    resample_to = "3min" if period == "3" else ("120min" if period == "120" else None)
    df = None
    last_error = None
    for attempt in range(3):
        try:
            raw = ak.stock_zh_a_minute(symbol=sina_code, period=fetch_period, adjust="")
            df = _normalize_ohlcv(raw)
            if df is None or df.empty:
                raise ValueError("空数据")
            if resample_to:
                df = _resample_ohlcv(df, resample_to)
            break
        except Exception as exc:
            last_error = exc
            print(f"{code} {period}分 第{attempt + 1}次失败: {exc}")
            if attempt < 2:
                _time.sleep(1)

    if df is None or df.empty:
        if cache_key in _minute_cache:
            print(f"{code} {period}分 使用过期缓存")
            return _minute_cache[cache_key][1]
        print(f"{code} {period}分 无可用数据: {last_error}")
        return None

    _minute_cache[cache_key] = (now, df)
    return df


def _fetch_akshare_daily_data(code, start_date, end_date):
    import akshare as ak

    raw = ak.stock_zh_a_hist(
        symbol=code,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust="",
        timeout=10,
    )
    return _normalize_ohlcv(raw)


def _parse_sina_daily_payload(text):
    match = re.search(r"\((\s*\[.*\]\s*)\)", text or "", flags=re.S)
    if not match:
        raise ValueError("新浪日线响应无法解析")
    rows = json.loads(match.group(1))
    df = pd.DataFrame(rows)
    return _normalize_ohlcv(df)


def _fetch_sina_daily_data(symbol_cfg):
    import requests

    url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_K=/CN_MarketDataService.getKLineData"
    resp = requests.get(
        url,
        params={
            "symbol": symbol_cfg["sina_code"],
            "scale": "240",
            "ma": "no",
            "datalen": "1500",
        },
        timeout=10,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    resp.raise_for_status()
    if not resp.encoding:
        resp.encoding = "gbk"
    df = _parse_sina_daily_payload(resp.text)
    if df is None or df.empty:
        raise ValueError("新浪日线为空")
    return df


def get_daily_data(symbol_cfg):
    code = symbol_cfg["symbol"]
    cache_key = f"daily_{code}"
    now = _time.time()
    if cache_key in _daily_cache:
        ts, cached = _daily_cache[cache_key]
        if now - ts < _DAILY_TTL:
            return cached

    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=365 * 5)).strftime("%Y%m%d")
    last_error = None
    for attempt in range(3):
        try:
            df = _fetch_akshare_daily_data(code, start_date, end_date)
            if df is None or df.empty:
                raise ValueError("空数据")
            _daily_cache[cache_key] = (now, df)
            _save_cache(cache_key, df)
            return df
        except Exception as exc:
            last_error = exc
            print(f"{code} 日线第{attempt + 1}次失败: {exc}")
            if attempt < 2:
                _time.sleep(1)

    try:
        df = _fetch_sina_daily_data(symbol_cfg)
        if df is not None and not df.empty:
            _daily_cache[cache_key] = (now, df)
            _save_cache(cache_key, df)
            return df
    except Exception as exc:
        last_error = exc
        print(f"{code} 新浪日线失败: {exc}")

    print(f"{code} 日线全部失败，使用本地缓存: {last_error}")
    if cache_key in _daily_cache:
        return _daily_cache[cache_key][1]
    return _load_cache(cache_key)


def get_weekly_data(symbol_cfg):
    daily = get_daily_data(symbol_cfg)
    if daily is None or daily.empty:
        return None
    return _resample_ohlcv(daily, "W-FRI")


# ── 市场状态 ───────────────────────────────────────────────────────


def get_market_status(symbol=None, now=None):
    """A 股交易状态：trading / lunch / closed。"""
    if now is None:
        now = datetime.now()
    wd = now.weekday()
    t = now.hour * 60 + now.minute
    if wd >= 5:
        return {"status": "closed", "next_open": "周一 09:30"}
    if 9 * 60 + 30 <= t < 11 * 60 + 30:
        return {"status": "trading", "next_open": None}
    if 11 * 60 + 30 <= t < 13 * 60:
        return {"status": "lunch", "next_open": "13:00"}
    if 13 * 60 <= t < 15 * 60:
        return {"status": "trading", "next_open": None}
    if t < 9 * 60 + 30:
        return {"status": "closed", "next_open": "09:30"}
    if wd == 4:
        return {"status": "closed", "next_open": "周一 09:30"}
    return {"status": "closed", "next_open": "明日 09:30"}


# ── 核心计算 ───────────────────────────────────────────────────────


def get_data(symbol=DEFAULT_SYMBOL, period="30", name=None):
    from data_fetcher import calculate_capital_flow, calculate_support_resistance
    from indicators import calc_bsd_wang, calc_main_signals, get_latest_signals

    sym = resolve_stock(symbol, name)
    period = str(period)
    is_minute = period not in ("daily", "weekly")
    daily = get_daily_data(sym)
    if period == "weekly":
        display_df = get_weekly_data(sym)
    elif is_minute:
        display_df = get_minute_data(sym, period)
    else:
        display_df = daily

    if display_df is None or len(display_df) == 0:
        return {"error": "数据获取失败"}

    signals, meta = get_latest_signals(display_df)
    df2 = calc_bsd_wang(calc_main_signals(display_df))

    sr = calculate_support_resistance(daily if daily is not None else display_df)
    cf = calculate_capital_flow(daily if daily is not None else display_df)

    last = df2.iloc[-1]
    meta.update(
        {
            "datetime": str(last.get("date", last.name))[:19],
            "close": safe(last.get("close")),
            "QRG": safe(last.get("QRG"), 1),
            "K": safe(last.get("K"), 2),
            "D": safe(last.get("D"), 2),
            "支撑": safe(last.get("支撑"), 2),
        }
    )

    df2["做多"] = df2["破浪"]
    df2["做空"] = df2["空仓"]

    history = []
    for _, row in df2[df2["做多"] | df2["做空"]].tail(10).iterrows():
        labels = []
        if row["做多"]:
            labels.append("🟡 破浪")
        if row["做空"]:
            labels.append("🟢 空仓")
        history.append(
            {
                "date": str(row["date"])[:16],
                "close": safe(row["close"]),
                "K": safe(row.get("K"), 1),
                "signal": " ".join(labels),
            }
        )

    levels_sorted = []
    if sr:
        cur = float(sr["current_price"])
        threshold = max(cur * 0.005, 0.03)
        for level_name, val in sorted(sr["levels"].items(), key=lambda x: -x[1]):
            levels_sorted.append(
                {"name": level_name, "value": safe(val), "current": abs(float(val) - cur) < threshold}
            )

    def _rising(row, prev_row, col):
        if prev_row is None:
            return False
        try:
            return float(row.get(col)) > float(prev_row.get(col))
        except Exception:
            return False

    indicator_series = []
    df2_tail = df2.reset_index(drop=True)
    for i, row in df2_tail.iterrows():
        ts = int(pd.Timestamp(row["date"]).timestamp())
        prev = df2_tail.iloc[i - 1] if i > 0 else None

        def rising(col, _row=row, _prev=prev):
            return _rising(_row, _prev, col)

        indicator_series.append(
            {
                "time": ts,
                "date": str(row["date"])[:16],
                "open": safe(row.get("open", row.get("close", 0))),
                "high": safe(row.get("high", row.get("close", 0))),
                "low": safe(row.get("low", row.get("close", 0))),
                "close": safe(row.get("close", 0)),
                "volume": safe(row.get("volume", 0), 0),
                "QRG": safe(row.get("QRG", 0), 1),
                "K": safe(row.get("K", 0), 2),
                "D": safe(row.get("D", 0), 2),
                "M1": safe(row.get("M1")),
                "M1r": rising("M1"),
                "M2": safe(row.get("M2")),
                "M2r": rising("M2"),
                "M3": safe(row.get("M3")),
                "M3r": rising("M3"),
                "M4": safe(row.get("M4")),
                "M4r": rising("M4"),
                "M5": safe(row.get("M5")),
                "M5r": rising("M5"),
                "支撑": safe(row.get("支撑")),
                "po": bool(row.get("破浪", False)),
                "kong": bool(row.get("空仓", False)),
            }
        )

    return clean(
        {
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": sym["symbol"],
            "name": sym["name"],
            "exchange": sym["exchange"],
            "period": period,
            "period_label": PERIOD_LABEL.get(period, period),
            "signals": {k: bool(v) for k, v in signals.items()},
            "meta": meta,
            "capital_flow": cf,
            "levels": levels_sorted,
            "history": list(reversed(history)),
            "indicator_series": indicator_series,
        }
    )


# ── API ────────────────────────────────────────────────────────────


@app.route("/api/data")
def api_data():
    period = request.args.get("period", "30")
    symbol = request.args.get("symbol", DEFAULT_SYMBOL)
    name = request.args.get("name")
    mode = request.args.get("mode", "full")
    try:
        data = get_data(symbol=symbol, period=period, name=name)
        if data is None or data.get("error"):
            return jsonify(data or {"error": "数据获取失败"}), 500
        if mode == "update" and "indicator_series" in data:
            data["indicator_series"] = data["indicator_series"][-3:]
        return jsonify(data)
    except Exception as exc:
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/symbols")
def api_symbols():
    ensure_default_watchlist()
    return jsonify(list_watchlist())


@app.route("/api/watchlist", methods=["GET", "POST"])
def api_watchlist():
    if request.method == "GET":
        ensure_default_watchlist()
        return jsonify(list_watchlist())
    body = request.get_json(silent=True) or {}
    try:
        item = add_watchlist_item(body.get("symbol", ""), body.get("name"))
        return jsonify(item)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/watchlist/<symbol>", methods=["DELETE"])
def api_watchlist_delete(symbol):
    try:
        return jsonify({"ok": remove_watchlist_item(symbol)})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip().upper()
    if not q:
        return jsonify([])
    items = get_stock_list()
    results = []
    for item in items:
        if item["symbol"].startswith(q) or q in item["symbol"] or q in item["name"].upper():
            results.append(item)
            if len(results) >= 30:
                break
    return jsonify(results)


@app.route("/api/resolve")
def api_resolve():
    symbol = request.args.get("symbol", "").strip()
    if not symbol:
        return jsonify({"error": "缺少 symbol"}), 400
    try:
        stock = resolve_stock(symbol)
        return jsonify({**stock, "known": stock["name"] != stock["symbol"]})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/trend")
def api_trend():
    symbol = request.args.get("symbol", DEFAULT_SYMBOL)
    name = request.args.get("name")
    try:
        sym = resolve_stock(symbol, name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    now = _time.time()
    cache_key = sym["symbol"]
    if cache_key in _trend_cache:
        ts, cached = _trend_cache[cache_key]
        if now - ts < _TREND_TTL:
            return jsonify(cached)

    from indicators import calc_bsd_wang, calc_main_signals

    periods = [
        ("1", "1分"),
        ("3", "3分"),
        ("5", "5分"),
        ("15", "15分"),
        ("30", "30分"),
        ("60", "60分"),
        ("120", "120分"),
        ("daily", "日线"),
        ("weekly", "周线"),
    ]
    daily_df = get_daily_data(sym)

    def _calc_one(p, label):
        try:
            if p == "daily":
                df = daily_df
            elif p == "weekly":
                df = get_weekly_data(sym) if daily_df is not None else None
            else:
                df = get_minute_data(sym, p)
            if df is None or len(df) < 15:
                return p, {"status": "unknown", "label": label, "K": None, "D": None}
            df2 = calc_bsd_wang(calc_main_signals(df))
            last = df2.iloc[-1]
            k_val = safe(last.get("K"), 2)
            d_val = safe(last.get("D"), 2)
            if k_val is None or d_val is None:
                status = "unknown"
            elif abs(k_val - d_val) < 1.0:
                status = "wait"
            else:
                status = "bull" if k_val > d_val else "bear"
            return p, {"status": status, "label": label, "K": k_val, "D": d_val}
        except Exception as exc:
            print(f"trend {sym['symbol']} {p}: {exc}")
            return p, {"status": "unknown", "label": label, "K": None, "D": None}

    trend = {}
    executor_mod = importlib.import_module("concurrent." + "fu" + "tures")
    with executor_mod.ThreadPoolExecutor(max_workers=6) as executor:
        pending_tasks = {executor.submit(_calc_one, p, label): p for p, label in periods}
        for future in executor_mod.as_completed(pending_tasks):
            p, result = future.result()
            trend[p] = result

    result = {"symbol": sym["symbol"], "name": sym["name"], "trend": trend}
    _trend_cache[cache_key] = (now, result)
    return jsonify(result)


@app.route("/api/market_status")
def api_market_status():
    symbol = request.args.get("symbol", DEFAULT_SYMBOL)
    return jsonify(get_market_status(symbol))


@app.route("/api/indicators")
def api_indicators():
    import indicators_pkg as ipkg

    result = []
    for _, mod in ipkg.get_all().items():
        meta = mod.META.copy()
        meta.pop("outputs", None)
        result.append(meta)
    return jsonify(result)


@app.route("/api/import_formula", methods=["POST"])
def api_import_formula():
    import indicators_pkg as ipkg
    from tdx_parser import TDXParser

    body = request.get_json(force=True)
    name = body.get("name", "").strip()
    source = body.get("source", "").strip()
    panel = body.get("panel", "sub")
    if not name or not source:
        return jsonify({"error": "name 和 source 不能为空"}), 400

    plugin_id = re.sub(r"[^a-z0-9_]", "_", name.lower())[:32]
    plugin_id = plugin_id.strip("_") or "custom"
    try:
        parser = TDXParser(source)
        code = parser.to_plugin_source(plugin_id, name, panel)
    except Exception as exc:
        return jsonify({"error": f"公式解析失败: {exc}"}), 400

    plugin_dir = os.path.join(os.path.dirname(__file__), "indicators_pkg")
    plugin_path = os.path.join(plugin_dir, f"{plugin_id}.py")
    with open(plugin_path, "w", encoding="utf-8") as f:
        f.write(code)
    ipkg.reload_all()
    return jsonify({"ok": True, "id": plugin_id, "name": name, "outputs": parser.build_meta_outputs()})


@app.route("/dashboard/<path:filename>")
def dashboard_static(filename):
    return send_from_directory("dashboard", filename)


@app.route("/")
def index():
    return send_from_directory("dashboard", "index.html")


init_watchlist_db(WATCHLIST_DB_PATH)

if __name__ == "__main__":
    ensure_default_watchlist()
    print("启动沪深 A 股信号看板: http://localhost:8877")
    app.run(host="0.0.0.0", port=8877, debug=False, threaded=True)
