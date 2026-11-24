---
name: perps-risk
description: Compute and manage risk for perpetual futures bots - linear and inverse PnL, funding payments (who pays, intervals, Binance mark price vs. Hyperliquid oracle price), initial and maintenance margin with tiers, liquidation price with Binance's official one-way formula (isolated and cross) and Bybit's isolated formula, mark price vs. last price, ADL and insurance funds, leverage limits and liquidation buffers. Includes a tested calculator that reproduces the exchanges' published examples. Use when building or reviewing a futures or perps bot, sizing leveraged positions, checking how far liquidation is, or modelling funding costs in a backtest.
allowed-tools: Bash(python ${CLAUDE_SKILL_DIR}/scripts/perps_calc.py *)
---

# Perpetual futures risk

Most blown-up bots die from leverage and funding, not from bad signals.
Compute liquidation distance and funding cost before every position, using the
exchange's own formulas. Facts below come from Binance and Bybit help pages and
Hyperliquid docs (checked November 2026); exchanges change tiers and formulas,
so verify against the current docs for your symbols. Not financial advice.

## Calculator

```bash
python ${CLAUDE_SKILL_DIR}/scripts/perps_calc.py pnl --side long --qty 0.5 --entry 60000 --exit 61500
python ${CLAUDE_SKILL_DIR}/scripts/perps_calc.py pnl --side short --qty 100 --entry 50000 --exit 45500 --inverse --contract 100
python ${CLAUDE_SKILL_DIR}/scripts/perps_calc.py funding --side long --qty 2 --mark 3500 --rate 0.0001 --intervals-per-day 3
python ${CLAUDE_SKILL_DIR}/scripts/perps_calc.py margin --qty 1 --price 60000 --leverage 10 --mmr 0.004 --cum 0
python ${CLAUDE_SKILL_DIR}/scripts/perps_calc.py liq-binance --side long --qty 1 --entry 60000 --wallet 6000 --mmr 0.004 --cum 0
python ${CLAUDE_SKILL_DIR}/scripts/perps_calc.py liq-binance --side long --qty 3683.979 --entry 1456.84 --wallet 1535443.01 \
    --mmr 0.10 --cum 135365 --other-mm 71200.81144 --other-upnl -56354.57      # cross
python ${CLAUDE_SKILL_DIR}/scripts/perps_calc.py liq-bybit --side long --qty 1 --entry 40000 --leverage 50 --mmr 0.005 \
    --extra-margin 3000 --taker-fee 0.00055
```

`--self-test` checks it against Binance's and Bybit's published worked examples.

## Formulas

- **Linear PnL** (USDT/USDC-margined): `side x qty x (exit - entry)`.
- **Inverse PnL** (coin-margined): `side x contracts x contract_size x (1/entry - 1/exit)`, paid in the coin.
- **Funding:** `payment = position notional x funding rate`; a **positive rate
  means longs pay shorts**. Binance uses mark price, default every 8 h (some
  symbols 4 h or 1 h); Hyperliquid pays **every hour** at 1/8 of the 8-hour rate,
  on the **oracle** price; Bybit intervals vary by symbol (read `fundingInterval`
  from instrument info).
- **Initial margin** = notional / leverage.
- **Maintenance margin (Binance)** = notional x MMR - maintenance amount (`cum`)
  for the notional's bracket; brackets come from the leverage-bracket endpoint.
  Bybit computes MM on mark-price position value (since September 2025).
- **Liquidation price, Binance USD-M one-way:**
  `LP = (WB - TMM1 + UPNL1 + cum - Side x Pos x EP) / (Pos x MMR - Side x Pos)`
  with Side +1 long / -1 short; isolated uses the position's margin as WB and
  TMM1 = UPNL1 = 0; cross uses the cross wallet balance and the other positions'
  maintenance margin and unrealised PnL.
- **Liquidation price, Bybit isolated linear:**
  long `(EP x Size - EP x Size/Lev - ExtraMargin/(1 - TakerFee) - MMDeduction) / (Size - Size x MMR)`;
  short `(EP x Size + EP x Size/Lev + ExtraMargin/(1 + TakerFee) + MMDeduction) / (Size + Size x MMR)`.
- Liquidation triggers on **mark price** (an index of several spot venues), not
  the last traded price. When a liquidation loses more than the margin, the
  **insurance fund** covers it; if that is not enough, **auto-deleveraging (ADL)**
  closes profitable opposite positions.

## Risk rules for bots

- Size from the stop, not from leverage (see `claude-trading-skills`
  position-sizing if installed): leverage only decides margin usage.
- Keep the liquidation price well beyond the stop - a buffer of at least a few
  times the instrument's typical daily range.
- Recompute liquidation after every fill, margin change or funding payment;
  maintenance tiers change as notional grows.
- Model funding in backtests and live PnL; hourly funding on crowded trades can
  exceed the expected edge.
- Hedge mode vs. one-way mode changes order fields (`positionSide`) and the
  liquidation formula; pick one and assert it at start-up.
- Use `reduceOnly` (or close-position flags) for exits so a stale exit cannot
  open a new position the other way.
- Cap leverage and total exposure in code, independent of exchange settings.

## Review checklist

- [ ] Liquidation price computed with the exchange's formula and current bracket, on mark price.
- [ ] Stop loss sits well inside the liquidation price; margin buffer monitored and alerted.
- [ ] Funding included in PnL and backtests, at the symbol's real interval.
- [ ] Position mode (one-way/hedge) and margin mode (isolated/cross) asserted at start-up.
- [ ] Exits use reduce-only; leverage and exposure capped in code.
- [ ] All maths in Decimal; quantities rounded to exchange filters (`order-precision`).
