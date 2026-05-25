import pandas as pd

import indicators


def _bars(length=40):
    dates = pd.date_range("2026-01-01 09:00", periods=length, freq="3min")
    close = pd.Series(range(100, 100 + length), dtype=float)
    return pd.DataFrame({
        "date": dates,
        "open": close - 0.5,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": 100,
    })


def test_latest_signals_apply_kd_filter_to_long(monkeypatch):
    def fake_main(df):
        result = df.copy()
        result["破浪"] = False
        result["空仓"] = False
        result["破浪"] = result["破浪"].astype(object)
        result.loc[result.index[-1], "破浪"] = True
        result["QRG"] = 10
        result["支撑"] = result["close"] - 5
        return result

    def fake_bsd(df):
        result = df.copy()
        result["K"] = 20
        result["D"] = 10
        return result

    monkeypatch.setattr(indicators, "calc_main_signals", fake_main)
    monkeypatch.setattr(indicators, "calc_bsd_wang", fake_bsd)

    signals, meta = indicators.get_latest_signals(_bars())

    assert signals["破浪_黄点"] is True
    assert signals["做多"] is False
    assert meta["K_gt30"] is False
    assert meta["K_ge_D"] is True


def test_latest_signals_apply_kd_filter_to_short(monkeypatch):
    def fake_main(df):
        result = df.copy()
        result["破浪"] = False
        result["空仓"] = False
        result["空仓"] = result["空仓"].astype(object)
        result.loc[result.index[-1], "空仓"] = True
        result["QRG"] = -50
        result["支撑"] = result["close"] - 5
        return result

    def fake_bsd(df):
        result = df.copy()
        result["K"] = 85
        result["D"] = 90
        return result

    monkeypatch.setattr(indicators, "calc_main_signals", fake_main)
    monkeypatch.setattr(indicators, "calc_bsd_wang", fake_bsd)

    signals, meta = indicators.get_latest_signals(_bars())

    assert signals["空仓_绿点"] is True
    assert signals["做空"] is False
    assert meta["K_lt80"] is False
    assert meta["K_le_D"] is True


def test_latest_signals_return_final_alert_when_all_conditions_match(monkeypatch):
    def fake_main(df):
        result = df.copy()
        result["破浪"] = False
        result["空仓"] = False
        result["破浪"] = result["破浪"].astype(object)
        result["空仓"] = result["空仓"].astype(object)
        result.loc[result.index[-1], "破浪"] = True
        result.loc[result.index[-1], "空仓"] = True
        result["QRG"] = 10
        result["支撑"] = result["close"] - 5
        return result

    def fake_bsd(df):
        result = df.copy()
        result["K"] = 50
        result["D"] = 50
        return result

    monkeypatch.setattr(indicators, "calc_main_signals", fake_main)
    monkeypatch.setattr(indicators, "calc_bsd_wang", fake_bsd)

    signals, meta = indicators.get_latest_signals(_bars())

    assert signals["破浪_黄点"] is True
    assert signals["空仓_绿点"] is True
    assert signals["做多"] is True
    assert signals["做空"] is True
    assert meta["K_gt30"] is True
    assert meta["K_lt80"] is True
    assert meta["K_ge_D"] is True
    assert meta["K_le_D"] is True
