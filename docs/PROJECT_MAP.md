# 项目地图

这份地图用于从头到尾理解当前项目，不替代 README。README 面向使用和运行，这里面向维护和整理。

## 一句话主线

A 股行情数据进入 `server.py`，经过内置公式和插件公式计算，组装成前端可画的 `indicator_series`，再由 `dashboard/index.html` 画出主图、副图、最新状态和趋势。

## 运行主路径

1. 用户打开 `/`。
2. Flask 从 `dashboard/index.html` 返回单页前端。
3. 前端 `loadData(mode)` 请求 `/api/data?symbol=...&period=...`。
4. `server.py:get_data()` 根据周期选择分钟线、日线或周线。
5. `indicators.py` 计算主图状态和波段王副图。
6. `data_fetcher.py` 补充支撑压力位和资金流向。
7. 后端返回 `indicator_series`、`signals`、`meta`、`levels`、`history`。
8. 前端 `renderAll()` 或 `updateBars()` 绘制图表和侧边栏。

## 自选股主路径

1. 启动时 `init_watchlist_db()` 创建 `data/watchlist.db`。
2. `/api/symbols` 和 `/api/watchlist` 查询当前自选股。
3. `/api/search?q=` 调用 AkShare A 股现货列表，按代码/名称搜索。
4. `/api/watchlist` POST 规范化股票代码、推断 SH/SZ、写入 SQLite。
5. `/api/watchlist/<symbol>` DELETE 删除一条自选股。

## 公式主路径

内置公式在 `indicators.py`：

- `calc_main_signals()`：计算 M1-M5、支撑线、QRG、破浪、空仓。
- `calc_bsd_wang()`：计算 K/D 和波段王多空标记。
- `get_latest_signals()`：把最新一根 K 线转成 `signals` 和 `meta`。

插件公式在 `indicators_pkg/`：

- 每个插件提供 `META` 和 `compute(df)`。
- `indicators_pkg/__init__.py` 负责热加载。
- `tdx_parser/` 可以把 TDX/慧赢公式解析成插件源码。

## 主流程文件

整理主流程时，优先改 `server.py`、`dashboard/index.html`、`indicators.py`、`indicators_pkg/` 和 `tdx_parser/`。

## 当前整理优先级

1. 抽出行情数据模块：`server.py` 的数据获取、缓存、周线聚合可以形成更深的模块。
2. 扩充公式回归测试：继续增加真实行情切片，验证 `破浪`、`空仓`、`K/D` 输出。
3. 增加前端端到端测试：覆盖自选股添加、删除、搜索和周期切换。
