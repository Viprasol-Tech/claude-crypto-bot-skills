---
name: order-lifecycle
description: Manage the full life of exchange orders in trading bots without duplicates or lost state - client order IDs (Binance newClientOrderId, Bybit orderLinkId, OKX clOrdId, Coinbase client_order_id, Hyperliquid cloid), timeouts as unknown status, query-before-resend, partial fills, order state machines, user data streams (Binance listenKey removal in 2026 and userDataStream.subscribe), Binance futures algo orders for stops since December 2025, reduce-only exits, reconciliation with the exchange as source of truth, and kill switches. Use when building or reviewing order placement, retries, fills handling or position tracking, or when a bot double-ordered, lost track of positions or missed fills.
---

# Order lifecycle

The two most expensive bot bugs: sending the same order twice, and believing
a position is different from what the exchange holds. Give every order an ID
before you send it, treat timeouts as "unknown", and reconcile with the
exchange continuously. Facts checked against exchange docs in November 2026.

## Client order IDs

Generate an ID, **store it first**, then send:

| Venue | Field | Rules |
|---|---|---|
| Binance Spot | `newClientOrderId` | unique among open orders; duplicates rejected ("Duplicate order sent.") |
| Binance USD-M | `newClientOrderId` | 1-36 chars `[.A-Z:/a-z0-9_-]`, unique among open orders |
| Bybit v5 | `orderLinkId` | up to 36 chars, letters/digits/`-`/`_`, unique |
| OKX v5 | `clOrdId` | up to 32 alphanumeric chars, case-sensitive |
| Coinbase | `client_order_id` | required on create |
| Hyperliquid | `cloid` | 128-bit hex |

## Timeouts are "unknown", not "failed"

```text
send order (with client id) -> timeout / 5xx / -1007 "execution status unknown"
  -> wait until the request can no longer execute
     (Binance: request timestamp + recvWindow has passed; the engine re-checks it)
  -> check the user data stream for that client id
  -> query the order by client id (Binance: origClientOrderId) AND recent fills (myTrades)
       found / filled  -> track it, do not re-send
       still not found -> re-send with a NEW client id, recorded as a retry of the first
```

A query sent immediately after a timeout can return "not found" (-2013) while
the order is still in flight. And reusing the same client id does **not** protect
you: Binance only rejects a duplicate `newClientOrderId` among **open** orders,
so if the first order already filled or expired, the "same id" resend becomes a
second order. Use a short recvWindow so the wait is short.

Binance futures: a 503 "Unknown error" means the order may have executed; a 503
"Service Unavailable" is a definite failure. **Bybit order creation is
asynchronous** - a success response means accepted; confirm through the stream.

## State machine

`new -> partially_filled -> filled`, or `-> canceled / rejected / expired`, with
partial fills possible before cancel. Track cumulative filled quantity and average
price from **fill events** (trade IDs, deduplicated), not from your request.
Allow only forward transitions.

## User data streams

- **Binance Spot:** the listenKey endpoints (`POST/PUT/DELETE /api/v3/userDataStream`
  and the WebSocket `userDataStream.start/ping/stop` methods) **stopped working
  on 20 February 2026**. Use the WebSocket API `userDataStream.subscribe` after
  `session.logon` (Ed25519 key), or `userDataStream.subscribe.signature`.
- **Binance USD-M:** the futures listenKey flow still exists - keep it alive and
  handle expiry.
- On every (re)connect, **reconcile**: fetch open orders, recent fills and
  positions via REST, because events may have been missed while disconnected.

## Futures specifics

- **Binance USD-M:** since **9 December 2025**, STOP, STOP_MARKET, TAKE_PROFIT,
  TAKE_PROFIT_MARKET and TRAILING_STOP_MARKET must go to
  `POST /fapi/v1/algoOrder`; sending them to `/fapi/v1/order` returns `-4120`.
  Up to 200 conditional orders across symbols.
- Use **reduce-only** (one-way mode) or `closePosition` for exits so a late exit
  cannot open a new position. In hedge mode set `positionSide` (and reduce-only
  is not allowed there).
- Place protective stops **on the exchange**, so a crashed bot is still protected.

## Reconciliation and safety

- The exchange is the source of truth: reconcile open orders, positions and
  balances on start-up, on reconnect and periodically; alert on mismatch.
- Cancel-on-disconnect / dead-man's switch where offered (Hyperliquid
  `scheduleCancel`, exchange cancel-all-after features).
- Kill switch: cancel all orders and optionally flatten, tested on testnet.
- Limits in code: max order size, max position, max orders per minute, price
  sanity band versus the book.

## Review checklist

- [ ] Client order id generated and persisted before every send.
- [ ] Timeouts and 5xx treated as unknown; wait out recvWindow, then query orders and fills before any resend.
- [ ] Fills tracked from fill events, deduplicated; partial fills handled.
- [ ] Binance Spot uses `userDataStream.subscribe`, not listenKey.
- [ ] Binance futures conditional orders use `/fapi/v1/algoOrder`.
- [ ] Reduce-only or close-position exits; exchange-side stops.
- [ ] Reconciliation on start, reconnect and schedule; kill switch tested.
