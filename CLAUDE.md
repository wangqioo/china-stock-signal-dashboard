# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

沪深 A 股信号看板，慧赢（平安证券）风格。Flask 后端 + 单页前端，用于观察沪深 A 股 K 线、公式指标、自选股和多周期趋势。

## 运行与部署

```bash
# 本地运行（端口 8877）
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python server.py

# Docker 部署
docker compose up -d --build
```

基础验证：

```bash
python -m pytest -q
python -m compileall -q .
curl http://localhost:8877/api/symbols
curl "http://localhost:8877/api/resolve?symbol=600519.SH"
curl "http://localhost:8877/api/data?symbol=000001&period=30&mode=update"
```

## 架构

```text
server.py              Flask API + A 股数据获取 + 自选股 SQLite + 指标组装
indicators.py          TDX公式 Python 复现：QRG/破浪/空仓 + 波段王 K/D
data_fetcher.py        支撑压力位、资金流向计算
indicators_pkg/        可热加载指标插件，每个 .py 文件需有 META + compute(df)
tdx_parser/            TDX/通达信公式 -> Python 插件代码 的解析器
dashboard/index.html   单文件前端（CSS + JS 全嵌入）
data/                  运行时 SQLite 和 CSV 缓存目录
```

## 数据流

1. 前端按钮触发 -> `loadData()` -> `GET /api/data?period=&symbol=`
2. `server.py:get_data()` -> `get_minute_data()` 或 `get_daily_data()` (akshare)
3. `indicators.py:calc_main_signals()` + `calc_bsd_wang()` -> 附加指标列
4. 序列化为 JSON -> `indicator_series[]`（每根 K 线含 OHLCV + 所有指标值）
5. 前端 `renderAll()` -> lightweight-charts 渲染

## 关键细节

**股票代码识别**：`normalize_stock_code()` 接受六位代码和常见 SH/SZ 前后缀，并通过代码段推断交易所。

**120分钟 K 线**：akshare 无直接接口，拉 60 分钟后用 `pd.resample('120min')` 聚合（见 `server.py:get_minute_data()`）。

**周线**：拉日线数据后按自然周（`resample('W-FRI')`）聚合，已在 `server.py:get_weekly_data()` 实现。

**公式逻辑**：
- 做多：`破浪`=QRG 上穿 -10 且 K>30 且 K≥D
- 做空：`空仓`=QRG 跌至 -50（前值≥-30）且 K<80 且 K≤D
- `破浪_黄点` / `空仓_绿点` 保留主图单项条件，`做多` / `做空` 是最新 K 线状态。

**配色规范（慧赢风格）**：
- 阳线：红色 `#ef5350`，阴线：白色
- 多头：红色 (`var(--bull)` = `#ef5350`)，空头：绿色 (`var(--bear)` = `#26a69a`)
- M1~M5 均线：下降黄色 `#FFD700`，上升粉色 `#FF00FF`
- 波段王彩带：多头 `#CC0000`，空头 `#00AA00`

**插件热加载**：`POST /api/import_formula` -> TDX 公式 -> 写入 `indicators_pkg/<id>.py` -> `ipkg.reload_all()`

## 前端结构（dashboard/index.html）

- `initCharts()` — 初始化 lightweight-charts（主图 kChart + 副图 bsdChart）
- `renderAll(data)` — 全量渲染，切换股票/周期时调用
- `updateBars(bars)` — 增量刷新，定时刷新时调用（只更新最后 3 根 K 线）
- `drawBsdCanvas(bars)` — 用 Canvas 画波段王 STICKLINE 色块（K 到 D 之间）
- `loadWatchlist()` / `addWatchlist()` / `removeWatchlist()` — 自选股管理
- `loadTrendPanel()` — 多周期 K/D 趋势面板

## 注意事项

- 前端是单一 HTML 文件，不拆分。改 UI 就改 `dashboard/index.html`。
- `server.py` 既是数据获取层也是路由层，保持这种合并结构，不引入蓝图或新文件。
- 日线数据本地缓存（`data/` 目录），akshare 失败时自动回退缓存。
- 不添加主动消息或后台扫描机制；本项目保持看板形态。
