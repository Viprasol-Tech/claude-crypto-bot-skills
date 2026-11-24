---
name: exchange-api-auth
description: Sign crypto exchange API requests correctly and debug signature and timestamp errors - Binance (HMAC, RSA, Ed25519, percent-encode before signing since 2026, recvWindow, -1021 and -1022), Binance WebSocket API session logon, Bybit v5 headers and sign string, OKX v5 signature and passphrase, Coinbase Advanced Trade ES256 JWTs (2-minute expiry, per-request uri claim), Kraken HMAC-SHA512 with nonces, clock sync and key permissions. Use when connecting a bot to an exchange, getting "invalid signature", "timestamp outside recvWindow" or "invalid nonce" errors, choosing key types, or reviewing API key handling.
---

# Exchange API authentication

Signature errors are almost always one of: signing different bytes than you
send, wrong encoding order, clock skew, or the wrong key type. Facts below were
checked against the official API docs in **November 2026**.

## Binance (Spot and USD-M Futures)

- **Key types:** HMAC, RSA and Ed25519. Binance recommends **Ed25519**, and the
  Spot **WebSocket API `session.logon` accepts only Ed25519** keys.
- **Payload to sign:** the query string concatenated with the request body (no separator).
- **Since about 15 January 2026, percent-encode the payload *before* signing**
  (REST); the wrong order gives `-1022 INVALID_SIGNATURE`. Test with non-ASCII
  symbols on testnet.
- Output: HMAC-SHA256 -> hex; RSA (PKCS#1 v1.5, SHA-256) and Ed25519 -> base64,
  then percent-encoded.
- **Time:** `timestamp` in ms (or µs with header `X-MBX-TIME-UNIT: MICROSECOND`);
  `recvWindow` default 5000 ms, max 60000, now with up to 3 decimals. The server
  rejects `timestamp >= serverTime + 1s` or older than `recvWindow` ->
  `-1021 INVALID_TIMESTAMP`. Since 2025 it re-checks just before matching, so
  keep `recvWindow` small and your clock synced (NTP, or offset from `/api/v3/time`).
- Futures (`https://fapi.binance.com`) documents HMAC and RSA keys.

## Bybit v5

- Headers: `X-BAPI-API-KEY`, `X-BAPI-TIMESTAMP` (ms), `X-BAPI-SIGN`,
  `X-BAPI-RECV-WINDOW` (default 5000).
- Sign `timestamp + apiKey + recvWindow + queryString` (GET) or `+ jsonBody`
  (POST); HMAC-SHA256 lowercase hex, or RSA-SHA256 base64. The signed string
  must be **byte-identical** to what you send (same JSON spacing and key order).
- Accepted when `serverTime - recvWindow <= timestamp < serverTime + 1000`.

## OKX v5

- Headers: `OK-ACCESS-KEY`, `OK-ACCESS-SIGN`, `OK-ACCESS-TIMESTAMP`, `OK-ACCESS-PASSPHRASE`.
- `sign = Base64(HMAC-SHA256(timestamp + METHOD + requestPath + body))`; for GET
  the query string is part of `requestPath` and the body is empty.
- Timestamp is ISO 8601 UTC with milliseconds (`2026-11-23T09:08:57.715Z`); more
  than 30 s skew gives error 50102.
- Demo trading: same host with header `x-simulated-trading: 1`.

## Coinbase Advanced Trade

- CDP API keys must be **ECDSA ES256 (P-256)** - Ed25519 keys are not supported.
- Each request needs its **own JWT**: header `kid` = key name and a random
  `nonce`; claims `iss: "cdp"`, `sub` = key name, `nbf` = now, `exp` = now + 120 s,
  and `uri` = `"GET api.coinbase.com/api/v3/brokerage/accounts"` (method, space,
  host + path, no scheme). Send `Authorization: Bearer <jwt>`.
- Base URL `https://api.coinbase.com/api/v3/brokerage`.

## Kraken Spot

- `API-Sign = Base64(HMAC-SHA512(key = Base64Decode(secret), msg = URIpath + SHA256(nonce + POSTdata)))`,
  URI path like `/0/private/AddOrder`, POST data including `nonce`.
- **Nonce must always increase per API key.** Sharing a key between processes or
  clock drift causes `EAPI:Invalid nonce` and, if repeated, temporary bans. Use
  one key per process.

## Key hygiene

- Trading-only permissions; **withdrawals disabled**; IP allow-list where offered.
- One key per bot/process (also avoids nonce races); separate testnet/demo keys.
- Keys from a secret manager, never in code, logs or error reports; rotate on
  any exposure.
- Prefer Ed25519 (Binance) or the exchange's recommended asymmetric keys over
  shared-secret HMAC where supported.

## Debugging checklist

- [ ] Signing exactly the bytes sent (encoding order, JSON spacing, query order).
- [ ] Correct output encoding (hex vs. base64) and URL-encoding of the signature.
- [ ] Clock synced; `recvWindow` small but realistic; server time offset applied.
- [ ] Right key type for the endpoint (Ed25519 for Binance WS logon; ES256 for Coinbase).
- [ ] Testnet/demo keys with testnet/demo hosts (and OKX demo header).
- [ ] Monotonic nonces per key (Kraken, Hyperliquid); one key per process.
