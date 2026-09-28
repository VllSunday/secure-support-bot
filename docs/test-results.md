# Verification results

Last verified: 2026-09-28.

## Automated checks

- `pytest -q`: **31 passed**
- Ruff: **passed**
- Mypy: **passed**
- Bandit: **no findings**
- pip-audit: **no known vulnerabilities** (the editable local package is skipped by design)

The test suite covers tenant-scoped document retrieval, own-order access, malicious
document instructions, unknown tools, foreign-order refunds, insufficient balance,
mandatory confirmation, risk timeout, request-id replay, persistent idempotency, and
the educational prompt-injection explanation.

## Telegram smoke check

- Telegram `getMe`: **passed**
- Bot username: `@llm_security_support_bot`
- Polling startup: **passed**
- Local runtime database: created in SQLite and excluded from Git

## Manual checks still required

Send `/start` from the Telegram account used for the exercise, then check `/order`,
a document question, and the refund confirmation button. The authorized cross-bot
attack report is kept in `docs/red-team-report.md` and should be filled with exact
requests, responses, and audit evidence after two external bots are provided.
