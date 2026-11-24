---
name: dex-bots
description: Build and review bots that trade on Hyperliquid and Solana - Hyperliquid info vs. exchange endpoints, EIP-712 signing through the SDK, API (agent) wallets, nonce rules, asset IDs, 5-significant-figure price and szDecimals size precision, cloid client IDs, weight and address rate limits, dead-man's switch; Solana swaps with Jupiter Swap API V2 (order and execute, or build), slippage, priority fees, blockhash expiry and safe re-signing, and Jito bundles. Use when writing a Hyperliquid perps bot, a Jupiter swap or Solana trading bot, debugging signature, nonce or expired-transaction errors, or reviewing on-chain bot safety.
---

# DEX bots: Hyperliquid and Solana

On-chain and DEX venues fail in different ways from centralised exchanges:
signatures, nonces and expiring transactions replace API keys and request IDs.
Facts checked against Hyperliquid, Jupiter, Solana and Jito docs in **November
2026**; these APIs change, so confirm versions before coding.

## Hyperliquid

Docs: <https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api>

- **Endpoints:** `POST https://api.hyperliquid.xyz/info` (read-only, unsigned,
  `type` field) and `POST .../exchange` (signed `{action, nonce, signature,
  vaultAddress?, expiresAfter?}`). Testnet: `https://api.hyperliquid-testnet.xyz`.
- **Signing:** use an official or well-maintained SDK. Hand-rolled signing breaks
  on msgpack field order, trailing zeros in numbers and uppercase addresses; a
  bad signature often shows up as "User or API Wallet 0x... does not exist".
- **API (agent) wallets:** can sign trades but cannot withdraw or query; the
  account gets 1 unnamed + 3 named agents (+2 per subaccount), optional expiry up
  to 180 days. **Query info with the master or subaccount address**, not the agent
  address. Never reuse a pruned agent address (old signed actions could replay).
- **Nonces** are per signer: the 100 highest are kept; a new nonce must exceed the
  smallest of them, never repeat, and be within (block time - 2 days, + 1 day) in
  ms. Use one agent wallet per process and an atomic counter seeded from the clock.
- **Asset IDs:** perps = index in `meta` (BTC = 0); spot = 10000 + `spotMeta`
  index; builder (HIP-3) perps have their own range.
- **Precision:** prices up to **5 significant figures** (integers exempt) and at
  most `MAX_DECIMALS - szDecimals` decimals (MAX_DECIMALS 6 for perps, 8 for
  spot); sizes rounded to `szDecimals`; strip trailing zeros before signing.
- **Client IDs:** `cloid` is an optional 128-bit hex string; cancel or query by it.
- **Limits:** IP weight 1200/min (exchange actions 1 + floor(batch/40)); per-address
  request budget grows with traded volume; 1000 open orders base (more with volume,
  capped at 5000); WebSocket limits on connections and subscriptions.
- **Safety:** `scheduleCancel` is a dead-man's switch (at least 5 s ahead, max 10
  triggers a day) - set it so orders cancel if the bot dies. `expiresAfter`
  rejects stale actions (expired ones cost extra rate limit).
- Funding is **hourly** on the oracle price (see `perps-risk`).

## Solana swaps with Jupiter

Docs: <https://developers.jup.ag/docs/swap>

- **Swap API V2** (`https://api.jup.ag/swap/v2`, key in `x-api-key`):
  - `GET /order?inputMint&outputMint&amount&taker[&slippageBps]` -> an unsigned
    base64 transaction plus a `requestId`. An empty `transaction` means no
    executable order - check `errorCode`.
  - Sign and immediately `POST /execute` with the signed transaction and
    `requestId`; read the returned status and signature. Orders expire quickly,
    so never sign and hold.
  - `/build` returns raw instructions for your own pipeline (your own priority
    fees and bundles). Check the API reference for exact field names - this API
    is evolving.
- Respect plan rate limits (keyless traffic is heavily limited).

## Solana transactions

- A blockhash is valid for about **150 slots**; track `lastValidBlockHeight`.
- **Do not re-sign** a transaction with a new blockhash until the old one has
  expired, or the trade can execute twice. Re-sending the *same* signed
  transaction is safe; signing a new one is a new trade.
- Use priority fees (compute unit price) sized from recent fees; set compute
  limits; use durable nonces only for slow signing flows.
- Confirm with `confirmed`/`finalized` commitment and check the transaction's
  error field - "sent" is not "succeeded".
- **Jito bundles:** up to 5 transactions executed atomically in order; minimum tip
  1000 lamports to a random tip account (from `getTipAccounts`), tip inside the
  same transaction; low per-IP rate limits. MEV protection helps but is not
  guaranteed - keep slippage tight.

## Wallet and key safety

- Hot wallets hold only what the bot needs; sweep profits to cold storage.
- Private keys from a secret manager or encrypted keystore, never in code, env
  files committed to git, or logs.
- Separate wallets per strategy; allow-list programs and tokens the bot may touch.
- Simulate transactions before sending where the venue supports it.

## Review checklist

- [ ] SDK signing; lowercase addresses; numbers without trailing zeros.
- [ ] Hyperliquid: agent wallet per process, monotonic nonces, info queried by master address, dead-man's switch set.
- [ ] Prices and sizes rounded to venue precision before signing.
- [ ] Every order carries a client id (cloid) and is queried, not re-sent, after a timeout.
- [ ] Solana: no re-signing before blockhash expiry; confirmation checks the error field.
- [ ] Slippage bounded; priority fees and tips sized deliberately.
- [ ] Keys in a secret manager; hot-wallet balances capped.
