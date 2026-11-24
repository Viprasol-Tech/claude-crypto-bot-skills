---
name: order-precision
description: Stop exchange order rejections caused by precision and size rules - Binance PRICE_FILTER tickSize, LOT_SIZE and MARKET_LOT_SIZE stepSize, NOTIONAL minimums, PERCENT_PRICE_BY_SIDE bands, MAX_NUM_ORDERS; Bybit lotSizeFilter and priceFilter (qtyStep, tickSize, minNotionalValue, spot basePrecision and minOrderAmt); OKX tickSz, lotSz, minSz and contract value; Hyperliquid significant figures and szDecimals - using Decimal rounding in the safe direction. Includes a tested tool that reads Binance exchangeInfo. Use when orders fail with "Filter failure", LOT_SIZE, PRICE_FILTER, NOTIONAL, -1013 or "invalid quantity/price" errors, or when writing order-sizing code for any exchange.
allowed-tools: Bash(python ${CLAUDE_SKILL_DIR}/scripts/order_precision.py *)
---

# Order precision and size filters

Every exchange rejects orders whose price or quantity is not an exact multiple
of its increments, or that are too small. The fixes: read the filters from the
exchange, keep numbers as **Decimal**, round in the **safe direction**, and
re-check minimums **after** rounding. Facts checked November 2026.

## Tool

```bash
O=${CLAUDE_SKILL_DIR}/scripts/order_precision.py
python $O --side BUY --price 64123.456 --qty 0.0012345 --tick 0.01 --step 0.00001 --min-qty 0.00001 --min-notional 5
python $O --exchange-info exchangeInfo.json --symbol BTCUSDT --side SELL --price 64123.451 --qty 0.0012345
python $O --market --exchange-info exchangeInfo.json --symbol ETHUSDT --side BUY --qty 2.5
```

It rounds buy prices **down** and sell prices **up** to the tick (never more
aggressive than requested), rounds quantity **down** to the step (never more
size than requested), and reports exactly why an order would be rejected and
the quantity needed to reach the minimum notional. Exit code 1 = would be rejected.

## Binance (Spot)

| Filter | Rule |
|---|---|
| `PRICE_FILTER` | `minPrice <= price <= maxPrice`, `price % tickSize == 0` (0 disables a rule) |
| `LOT_SIZE` | `minQty <= qty <= maxQty`, `qty % stepSize == 0` |
| `MARKET_LOT_SIZE` | same, for MARKET orders |
| `NOTIONAL` | `minNotional <= price x qty <= maxNotional`; `applyMinToMarket` / `applyMaxToMarket` decide MARKET coverage (MARKET uses an average/reference price) |
| `PERCENT_PRICE_BY_SIDE` | price within a band around the average price, per side |
| `MAX_NUM_ORDERS` | open orders per symbol (normal + algo) |

Violations return messages like "Filter failure: LOT_SIZE", usually with code
`-1013`; matching-engine rejections use `-2010`. Live BTCUSDT (November 2026):
tickSize 0.01, stepSize 0.00001, min notional 5.

## Other venues

- **Bybit v5** (`/v5/market/instruments-info`): linear `lotSizeFilter`
  (`minOrderQty`, `maxOrderQty`, `maxMktOrderQty`, `qtyStep`, `minNotionalValue`)
  and `priceFilter.tickSize`; spot uses `basePrecision`, `quotePrecision`,
  `minOrderAmt` (quote amount) and `maxLimitOrderQty`/`maxMarketOrderQty`.
- **OKX v5:** `tickSz` (price), `lotSz` and `minSz` (contracts for derivatives,
  base currency for spot), `ctVal` (contract value) - convert base size to
  contracts first.
- **Hyperliquid:** prices up to 5 significant figures and at most
  `MAX_DECIMALS - szDecimals` decimals (6 perps / 8 spot); sizes to `szDecimals`
  (see `dex-bots`).

## Rules

- Never use floats for prices or sizes: `0.1 + 0.2` breaks `% stepSize`. Parse
  filter strings straight into Decimal.
- Format with the step's exact decimals and no exponent notation (`1E-5` is
  rejected by many venues).
- Check minimums after rounding - rounding down can drop below `minQty` or
  `minNotional`.
- Use `MARKET_LOT_SIZE` (Binance) or `maxMktOrderQty` (Bybit) for market orders.
- **Refresh filters** periodically (for example hourly and on rejection): they
  change without notice.
- Futures contracts may need size in contracts, not coins (OKX `ctVal`, inverse
  contracts).

## Review checklist

- [ ] Filters loaded from the exchange, cached briefly, refreshed on rejection.
- [ ] Decimal end to end; no float parsing of prices or sizes.
- [ ] Price rounded passively per side; quantity rounded down; minimums re-checked.
- [ ] Market orders use market-specific size limits; notional checked against a realistic price.
- [ ] Contract-size conversion for derivatives.
- [ ] Rejections logged with the filter name and the attempted values.
