---
name: orderbook-sync
description: Maintain a correct local order book from exchange WebSocket diff streams - Binance spot (snapshot plus depth updates, U and u update IDs, gap detection and resync) and USD-M futures (pu chaining, first-event rule), absolute quantities and zero-quantity deletes, crossed-book checks, reconnects, pings and 24-hour connection limits, and the same ideas for other venues. Includes a tested sync engine with replay. Use when building market making, arbitrage or execution bots that read depth, when a local book drifts from the exchange or shows crossed prices, or when reviewing WebSocket market-data code.
allowed-tools: Bash(python ${CLAUDE_SKILL_DIR}/scripts/book_sync.py *)
---

# Order book sync

A local order book is only correct if every update is applied in order after
a matching snapshot. Miss one message and the book silently drifts - and a bot
trading on a wrong book loses money. Detect gaps and resync; never "patch" a
book. Rules below are Binance's documented procedures (checked November 2026).

## Binance Spot

1. Open `<symbol>@depth` (or `@depth@100ms`) and **buffer** events; note the
   first event's `U`.
2. `GET /api/v3/depth?symbol=...&limit=5000`. If its `lastUpdateId` is lower than
   that first `U`, fetch the snapshot again.
3. Drop buffered events with `u <= lastUpdateId`.
4. For each next event: ignore it if `u` is below the local update id; if `U` is
   greater than local id + 1, **updates were missed - rebuild from a new
   snapshot**; otherwise apply it and set local id = `u`.
5. Quantities are **absolute** (replace the level); quantity 0 removes the level.
   Snapshots hold at most 5000 levels per side.

## Binance USD-M Futures

1. Buffer `<symbol>@depth` events; fetch `/fapi/v1/depth?limit=1000`.
2. Drop events with `u < lastUpdateId`.
3. The first applied event must satisfy `U <= lastUpdateId <= u`.
4. Every later event's `pu` must equal the previous event's `u`; otherwise resync.

(Futures WebSocket paths moved to `/public`, `/market` and `/private` in 2026.)

## Engine

```bash
python ${CLAUDE_SKILL_DIR}/scripts/book_sync.py replay snapshot.json events.jsonl --mode spot      # exit 3 = resync needed
python ${CLAUDE_SKILL_DIR}/scripts/book_sync.py replay snapshot.json events.jsonl --mode futures
python ${CLAUDE_SKILL_DIR}/scripts/book_sync.py --self-test
```

`LocalBook` in the script implements both rule sets with Decimal prices and
raises `GapError` on a gap; import it or port it.

## Connection hygiene

- Binance connections last 24 h. Spot streams ping every 20 s and drop you
  without a pong within 1 minute; USD-M futures streams ping every 3 minutes and
  drop you after 10 minutes without a pong. Reconnect before 24 h, and **every
  reconnect is a full resync** (new snapshot).
- Detect silence: no message for N seconds on an active symbol means the stream
  is dead even if the socket looks open.
- Check every applied update for a **crossed book** (best bid >= best ask) - a
  cheap signal that something is wrong.
- Keep processing off the socket thread (queue), or the buffer backs up and you
  fall behind.
- Timestamp events on receipt; alert when exchange-to-local lag grows.

## Other venues

Most venues use the same pattern - snapshot plus sequenced diffs - with their own
sequence fields (for example Bybit `u`/`seq` with periodic snapshots on reconnect;
OKX `seqId`/`prevSeqId` and checksums). Read each venue's book-maintenance page
and verify checksums where provided.

## Review checklist

- [ ] Events buffered before the snapshot; stale events discarded by update id.
- [ ] Gap detection per the venue's rules; resync on any gap or reconnect.
- [ ] Absolute quantities; zero removes the level; Decimal prices as keys.
- [ ] Crossed-book and staleness checks with alerts; trading halted while resyncing.
- [ ] Ping/pong handled; reconnect before the connection lifetime ends.
