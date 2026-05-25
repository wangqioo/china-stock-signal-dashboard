import sqlite3

import pandas as pd
import pytest

import server


def test_normalize_stock_code_accepts_common_a_share_inputs():
    assert server.normalize_stock_code("000001") == "000001"
    assert server.normalize_stock_code("sz000001") == "000001"
    assert server.normalize_stock_code("600519.SH") == "600519"
    assert server.normalize_stock_code(" SH.688981 ") == "688981"


@pytest.mark.parametrize("raw", ["", "P0", "12345", "900001", "120000", "abc123"])
def test_normalize_stock_code_rejects_non_a_share_inputs(raw):
    with pytest.raises(ValueError):
        server.normalize_stock_code(raw)


def test_stock_exchange_infers_mainland_exchange():
    assert server.infer_exchange("600519") == "SH"
    assert server.infer_exchange("688981") == "SH"
    assert server.infer_exchange("000001") == "SZ"
    assert server.infer_exchange("300750") == "SZ"
    assert server.infer_exchange("002594") == "SZ"


def test_default_watchlist_matches_requested_seed_stocks():
    expected = [
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
    assert server.DEFAULT_WATCHLIST == expected
    assert [server.infer_exchange(symbol) for symbol, _ in expected] == [
        "SZ",
        "SZ",
        "SH",
        "SZ",
        "SH",
        "SH",
        "SZ",
        "SH",
        "SZ",
        "SH",
    ]


def test_watchlist_crud_persists_unique_rows(tmp_path):
    db_path = tmp_path / "watchlist.db"
    server.init_watchlist_db(str(db_path))

    first = server.add_watchlist_item("000001", "平安银行", db_path=str(db_path))
    second = server.add_watchlist_item("SZ000001", "平安银行", db_path=str(db_path))
    server.add_watchlist_item("600519", "贵州茅台", db_path=str(db_path))

    assert first["symbol"] == "000001"
    assert second["symbol"] == "000001"

    items = server.list_watchlist(db_path=str(db_path))
    assert [item["symbol"] for item in items] == ["000001", "600519"]
    assert items[0]["exchange"] == "SZ"
    assert items[1]["exchange"] == "SH"

    assert server.remove_watchlist_item("000001", db_path=str(db_path)) is True
    assert server.remove_watchlist_item("000001", db_path=str(db_path)) is False
    assert [item["symbol"] for item in server.list_watchlist(db_path=str(db_path))] == ["600519"]

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("select count(*) from watchlist").fetchone()[0]
    assert count == 1


def test_stock_list_falls_back_to_code_name_source(monkeypatch):
    server._STOCK_LIST_CACHE.update({"ts": 0, "items": []})

    def fail_primary():
        raise RuntimeError("primary source unavailable")

    fallback_df = pd.DataFrame(
        [
            {"code": "000001", "name": "平安银行"},
            {"code": "600519", "name": "贵州茅台"},
            {"code": "920001", "name": "非沪深样本"},
        ]
    )
    monkeypatch.setattr(server, "_fetch_eastmoney_stock_list", fail_primary)
    monkeypatch.setattr(server, "_fetch_code_name_stock_list", lambda: server._stock_items_from_frame(fallback_df))
    monkeypatch.setattr(server, "_fetch_realtime_stock_list", fail_primary)

    items = server.get_stock_list(force=True)

    assert [item["symbol"] for item in items] == ["000001", "600519"]
    assert items[0]["name"] == "平安银行"
    assert server.resolve_stock_name("600519") == "贵州茅台"


def test_resolve_stock_uses_known_name_without_fetching_slow_remote_list(monkeypatch):
    def fail_if_remote_list_is_loaded(*args, **kwargs):
        raise AssertionError("resolving a known default/watchlist symbol should not fetch the remote stock list")

    monkeypatch.setattr(server, "get_stock_list", fail_if_remote_list_is_loaded)

    assert server.resolve_stock("000725") == {
        "symbol": "000725",
        "name": "京东方A",
        "exchange": "SZ",
        "sina_code": "sz000725",
    }


def test_daily_data_uses_secondary_source_when_primary_source_is_unavailable(monkeypatch):
    symbol_cfg = server.resolve_stock("000001", "平安银行")
    cache_key = f"daily_{symbol_cfg['symbol']}"
    server._daily_cache.pop(cache_key, None)

    def fail_primary(*args, **kwargs):
        raise RuntimeError("primary source unavailable")

    secondary_df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-05-20", "2026-05-21"]),
            "open": [10.0, 10.2],
            "high": [10.4, 10.6],
            "low": [9.9, 10.1],
            "close": [10.3, 10.5],
            "volume": [1000, 2000],
        }
    )
    monkeypatch.setattr(server, "_fetch_akshare_daily_data", fail_primary)
    monkeypatch.setattr(server, "_fetch_sina_daily_data", lambda cfg: secondary_df)
    monkeypatch.setattr(server, "_load_cache", lambda name: None)

    df = server.get_daily_data(symbol_cfg)

    assert list(df["close"]) == [10.3, 10.5]
    assert cache_key in server._daily_cache


def test_alert_and_pending_routes_are_not_registered():
    rules = {rule.rule for rule in server.app.url_map.iter_rules()}
    assert "/api/signals/pending" not in rules
    assert "/api/signals/push" not in rules
    assert "/api/settings/period" not in rules


def test_frontend_removes_reminder_and_notification_code():
    html = open("dashboard/index.html", encoding="utf-8").read()
    forbidden = [
        "showSignalToast",
        "showResonanceToast",
        "Notification",
        "scanAllWatchlist",
        "_consumePending",
        "popup-stack",
        "bell-badge",
        "提醒",
        "通知",
        "弹窗",
    ]
    for term in forbidden:
        assert term not in html


def test_repository_removes_futures_and_reminder_artifacts():
    """新项目不能残留期货对象或旧提醒/推送系统。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    forbidden = [
        "期货",
        "futures",
        "主力连续",
        "具体月份合约",
        "合约代码",
        "signals.db",
        "_pending_signals",
        "/api/signals",
        "Notification",
        "scanAllWatchlist",
        "showSignalToast",
        "showResonanceToast",
        "桌面通知",
        "信号弹窗",
        "未读队列",
        "推送",
        "提醒",
    ]
    skip_dirs = {".git", ".pytest_cache", "__pycache__", "data", "test"}
    text_suffixes = {".py", ".md", ".html", ".txt", ".yml", ".yaml", ""}
    offenders = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in skip_dirs for part in path.parts):
            continue
        if path.suffix not in text_suffixes and path.name not in {"Dockerfile"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for term in forbidden:
            if term in text:
                offenders.append(f"{path.relative_to(root)} contains {term}")
    assert offenders == []
