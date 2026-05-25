# 沪深 A 股信号看板 — Agent Guide

## Repository Intent

This repository contains a formula-driven mainland China stock dashboard. It turns AkShare A-share bars and TDX/Huiying-style formulas into chart panels, watchlist state, support/resistance levels, and multi-period trend status.

The core is the formula-to-panel pipeline, not trade execution.

Do not move live order placement, account login, broker APIs, payment/subscription flows, user systems, or execution risk controls into this repository.

## Domain Language

Prefer these terms in documentation and code-level explanations:

- **沪深 A 股信号看板** for the product.
- **股票代码** for six-digit SH/SZ symbols such as `000001`, `600519`, `688981`.
- **自选股** for persisted watchlist rows in `data/watchlist.db`.
- **公式指标** for TDX/Huiying-derived calculations.
- **主图信号** for QRG/破浪/空仓 output on the K-line chart.
- **波段王副图** for the K/D momentum panel.
- **多周期趋势** for K/D state across periods.

## Runtime Entry Points

| Entry point | Purpose |
| --- | --- |
| `python server.py` | Main local dashboard runtime on port 8877 |
| `docker compose up -d --build` | Container runtime |

Useful commands:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python server.py
python -m pytest -q
python -m compileall -q .
docker compose up -d --build
```

## Core Modules

| File | Responsibility |
| --- | --- |
| `server.py` | Flask API, A-share data fetch/cache, SQLite watchlist, indicator response assembly |
| `dashboard/index.html` | Single-file frontend for K-line chart, Wave King panel, watchlist, and trend panel |
| `indicators.py` | Built-in formula reproductions: QRG, 破浪, 空仓, 波段王 K/D |
| `indicators_pkg/` | Hot-loadable formula indicator plugins |
| `tdx_parser/` | TDX/Huiying formula parser and plugin source generator |
| `data_fetcher.py` | Pure support/resistance and capital-flow calculations |
| `data/` | Runtime cache and `watchlist.db`; do not commit generated data |

## Development Rules

- Keep the formula-to-panel pipeline readable: bars in, formula indicators out, chart-ready JSON returned.
- Do not change formula semantics casually. If an indicator formula changes, document the before/after rule in README or a dedicated note.
- Keep `server.py` and `dashboard/index.html` as the current all-in-one runtime shape unless doing an explicit refactor pass.
- Keep user-facing stock input tolerant: accept plain six-digit codes and common SH/SZ prefixes/suffixes.
- Do not add active background messaging code; the app should remain a passive dashboard.
- Do not commit secrets or generated runtime data.

## Verification

```bash
python -m pytest -q
python -m compileall -q .
curl http://localhost:8877/api/symbols
curl "http://localhost:8877/api/resolve?symbol=600519.SH"
curl "http://localhost:8877/api/data?symbol=000001&period=30&mode=update"
```

AkShare calls depend on live network/data-provider availability, so separate syntax errors from provider outages when reporting verification.
