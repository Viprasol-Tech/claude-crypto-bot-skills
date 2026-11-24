# Security policy

## Reporting a vulnerability

Please report security problems privately through
[GitHub security advisories](https://github.com/Viprasol-Tech/claude-crypto-bot-skills/security/advisories/new)
or by email to [support@viprasol.com](mailto:support@viprasol.com). Do not open a public issue.
We aim to reply within 3 working days.

## Scope

- The bundled scripts (`order_precision.py`, `book_sync.py`, `perps_calc.py`): they
  read command-line values or local JSON files and print results. They make no network calls and run no
  shell commands.
- Skill instructions that could lead an assistant to weaken fund safety:
  withdrawal-enabled keys, unbounded retries, missing stops or leverage limits.

## Keep secrets and card data out of chats

These skills never need your keys or funds. Never paste exchange API keys,
secrets, wallet private keys or seed phrases into an issue, pull request or
chat. Use synthetic data and sandbox keys. If a key has been
exposed, rotate it with your provider immediately.
