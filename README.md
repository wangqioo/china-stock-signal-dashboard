# 沪深 A 股信号看板

基于原看板的公式指标和 K 线面板重做的数据看板。后端使用 Flask，前端保持单文件 `dashboard/index.html`。数据对象改为中国大陆沪深 A 股，支持搜索并添加上交所、深交所股票；保留 QRG / 破浪 / 空仓 / 波段王 K/D、支撑压力位、多周期趋势和 TDX 公式导入；不包含主动打扰机制。

## 快速启动

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python server.py
# 访问 http://localhost:8877
```

Docker：

```bash
docker compose up -d --build
```

## 功能一览

| 功能 | 说明 |
|------|------|
| 沪深 A 股自选 | 支持 `000001`、`sz000001`、`600519.SH`、`SH.688981` 等写法，自动识别 SH/SZ，本地 SQLite 持久化 |
| 股票搜索 | 通过东方财富实时列表、AkShare 代码名称表等多源股票池按代码/名称搜索，点击即可加入自选 |
| 多周期 K 线 | 1/3/5/15/30/60/120 分钟、日线、周线；3 分钟由 1 分钟聚合，120 分钟由 60 分钟聚合 |
| 主图公式 | QRG、破浪黄点、空仓绿点、M1-M5、支撑线，沿用原项目计算逻辑 |
| 波段王副图 | K/D 动能色块柱，Canvas + lightweight-charts 渲染 |
| 关键价位 | 侧边栏显示支撑压力位和 MA5/10/20 |
| 多周期趋势 | 展示各周期 K/D 多空状态和共振概览 |
| TDX 公式导入 | 粘贴通达信/慧赢公式，生成 `indicators_pkg/` 插件并热加载 |

## 默认自选

| 代码 | 名称 | 交易所 |
|------|------|--------|
| 000001 | 平安银行 | SZ |
| 600519 | 贵州茅台 | SH |
| 300750 | 宁德时代 | SZ |
| 002594 | 比亚迪 | SZ |

## API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/data` | GET | K 线 + 指标数据。参数：`symbol`、`period`、`mode=full/update`、可选 `name` |
| `/api/symbols` | GET | 当前自选股列表 |
| `/api/watchlist` | GET/POST | 查询或添加自选股，POST JSON：`{"symbol":"600519","name":"贵州茅台"}` |
| `/api/watchlist/<symbol>` | DELETE | 删除自选股 |
| `/api/search?q=茅台` | GET | 搜索沪深 A 股代码/名称 |
| `/api/resolve?symbol=600519.SH` | GET | 校验并规范化股票代码 |
| `/api/trend?symbol=000001` | GET | 多周期 K/D 趋势 |
| `/api/market_status` | GET | A 股交易时段状态 |
| `/api/indicators` | GET | 已加载指标插件列表 |
| `/api/import_formula` | POST | 导入 TDX 公式，body: `{"name":"","source":"","panel":"sub"}` |

## 数据流

```text
前端 loadData(mode)
  -> GET /api/data?symbol=000001&period=30&mode=full
  -> server.py:get_data()
      ├─ get_minute_data()   # A 股分钟线，按周期 TTL 缓存
      ├─ get_daily_data()    # A 股日线，内存缓存 + CSV 回退
      ├─ get_weekly_data()   # 日线 resample('W-FRI')
      ├─ calc_main_signals() # QRG / 破浪 / 空仓 / M1-M5
      ├─ calc_bsd_wang()     # K/D 波段王
      └─ indicator_series[]  # 图表需要的完整序列
  -> 前端 renderAll(data) 或 updateBars(bars)
```

## 文件说明

| 文件 | 作用 |
|------|------|
| `server.py` | Flask API、A 股数据获取、缓存、自选股 SQLite、指标结果组装 |
| `dashboard/index.html` | 单文件前端：K 线主图、波段王副图、自选股、趋势面板、公式导入 |
| `indicators.py` | TDX 公式 Python 复现：QRG / 破浪 / 空仓 / 波段王 K/D |
| `data_fetcher.py` | 支撑压力位、资金流向计算 |
| `indicators_pkg/` | 指标插件目录，支持热加载 |
| `tdx_parser/` | TDX/慧赢公式解析器 |
| `data/` | 运行时 SQLite 和 CSV 缓存目录，不提交生成数据 |
| `test/` | 回归测试 |

## 验证

```bash
python -m pytest -q
python -m compileall -q .
python server.py
curl http://localhost:8877/api/symbols
curl "http://localhost:8877/api/resolve?symbol=600519.SH"
curl "http://localhost:8877/api/data?symbol=000001&period=30&mode=update"
```

AkShare 行情接口依赖实时网络和数据源状态；如果行情接口短暂不可用，先区分网络/源站问题与本项目代码问题。
