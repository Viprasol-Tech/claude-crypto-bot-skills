# Changelog

All notable changes are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-23

### Added
- `crypto-bots` Claude Code plugin with 7 skills: `exchange-api-auth`,
  `order-precision`, `rate-limits`, `orderbook-sync`, `order-lifecycle`,
  `perps-risk`, `dex-bots`.
- `order_precision.py`: tick/step rounding in the safe direction and
  minQty/minNotional checks, reading Binance exchangeInfo.
- `book_sync.py`: Binance spot and USD-M local order book sync with gap
  detection, crossed-book check and replay.
- `perps_calc.py`: linear/inverse PnL, funding, margin, and Binance and Bybit
  liquidation prices, reproducing the exchanges' published examples.
- Facts checked against Binance, Bybit, OKX, Coinbase, Kraken, Hyperliquid,
  Jupiter, Solana and Jito docs in November 2026.
