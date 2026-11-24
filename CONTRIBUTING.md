# Contributing

Thanks for helping developers build crypto bots that don't lose money to bugs. Fixes, new skills, better
checklists and corrections are all welcome.

## Ways to help

- **Fix a fact.** Exchange APIs change often (endpoints, filters, limits, signing). If a rule, limit
  or header is out of date, open a PR with a link to the official source.
- **Improve a skill.** Each skill is a folder in `plugins/crypto-bots/skills/`
  with a `SKILL.md` (YAML frontmatter `name` + `description`, then instructions).
- **Add a skill.** Same layout. Keep `SKILL.md` under 500 lines; put long
  reference material in a separate file linked from it.
- **Improve the scripts** in `order-precision/scripts`, `orderbook-sync/scripts` and `perps-risk/scripts`.
  They must stay standard-library only and keep their `--self-test` passing.

## Before you open a PR

```bash
python tests/validate_repo.py
python plugins/crypto-bots/skills/order-precision/scripts/order_precision.py --self-test
python plugins/crypto-bots/skills/orderbook-sync/scripts/book_sync.py --self-test
python plugins/crypto-bots/skills/perps-risk/scripts/perps_calc.py --self-test
```

Code samples must run as written, use test-mode keys only, and treat amounts as
testnet keys only; never real API keys, wallets or seed phrases.

## Ground rules

- Accuracy over volume: cite official docs for platform facts.
- Regulatory content is engineering guidance, not legal or tax advice; cite the exchange's official API documentation or changelog.
- Never include real API keys, account numbers or personal data.
