---
name: rate-limits
description: Stay inside crypto exchange rate limits and avoid IP bans - Binance request weight (6000 per minute per IP), order counts, X-MBX-USED-WEIGHT and order-count headers, 429 then 418 bans with Retry-After, zero-weight successful orders; Bybit IP limits, X-Bapi-Limit headers and retCode 10006; OKX per-instrument limits and 50011/50061; Coinbase and Hyperliquid limits; WebSocket connection and message limits; client-side token buckets, backoff and moving polling to streams. Use when a bot hits 429, 418, 403 "access too frequent" or "too many visits" errors, when scaling to many symbols, or when designing request scheduling.
---

# Rate limits

Exchanges escalate: throttle, then temporary bans, then longer bans. A bot that
ignores 429s can lose access for days - exactly when it needs to close
positions. Budget requests on the client side, read the headers, and move
polling to WebSocket streams. Figures checked November 2026; read live limits
from the APIs (Binance `exchangeInfo.rateLimits`) instead of hard-coding them.

## Binance Spot

- `REQUEST_WEIGHT` **6000 per minute per IP**; `ORDERS` 100 per 10 s and 200,000
  per day per account; raw requests 300,000 per 5 minutes.
- Since April 2026, **successful** orders on the listed order endpoints cost 0
  weight; failed ones still cost weight - another reason to validate filters first.
- Headers: `X-MBX-USED-WEIGHT-1M` (IP weight), `X-MBX-ORDER-COUNT-10S` and
  `X-MBX-ORDER-COUNT-1D` (account orders).
- **HTTP 429** = slow down now. Keep going and you get **HTTP 418** - an IP ban
  from 2 minutes up to 3 days. Both include `Retry-After` (seconds). A 403 can be
  a WAF block. Error codes `-1003` (too many requests), `-1015` (too many orders).
- WebSocket streams: 5 incoming messages per second, 1024 streams per
  connection, 300 connections per 5 minutes per IP; connections live 24 h.

USD-M futures use the same header and 429/418 pattern; read limits from its own
`exchangeInfo`.

## Other venues

- **Bybit v5:** 600 requests per 5 s per IP - exceeding it returns 403 "access too
  frequent" (stop for at least 10 minutes). Per-endpoint limits return
  `retCode 10006`; headers `X-Bapi-Limit-Status`, `X-Bapi-Limit`,
  `X-Bapi-Limit-Reset-Timestamp`. Order limits are per UID per endpoint.
- **OKX v5:** trading limits per instrument, shared between REST and WebSocket;
  sub-accounts 1000 orders per 2 s (`50061`); general throttling `50011`.
- **Coinbase Advanced Trade:** WebSocket 8 per second per IP for connections and
  unauthenticated messages; check the current REST limits in the docs.
- **Hyperliquid:** IP weight 1200 per minute plus address-based limits that grow
  with volume (see `dex-bots`).

## Design

- **Client-side limiter:** a token bucket per limit (IP weight, orders per 10 s,
  per day) that blocks before sending - not after the 429.
- **Read headers** on every response and adjust the bucket to the server's count.
- **On 429:** stop all non-essential requests, honour `Retry-After`, then resume
  slowly. **Never** retry in a tight loop.
- **Prioritise** order management (cancels, exits) over data requests when the
  budget is low.
- **Use streams** for market data, order updates and balances instead of polling.
- **Batch** where the API offers batch endpoints.
- Several bots on one IP share the IP budget: coordinate them or use separate IPs
  where the exchange allows it.
- Alert on 429/418 and on sustained high usage (for example over 70% of budget).

## Review checklist

- [ ] Token buckets for every documented limit; limits loaded from the exchange.
- [ ] Usage headers parsed; 429 handling honours Retry-After; no retry storms.
- [ ] Market data and order updates come from WebSocket streams, not polling.
- [ ] Cancels and exits prioritised when throttled.
- [ ] Filters validated client-side so failed orders don't burn weight.
- [ ] Alerts on 429, 418, 403 and high usage.
