# Red-team report

This file records authorized attack attempts against the deployed demo bot.

For each attempt, capture:

- UTC timestamp
- Exact Telegram request
- Exact bot response
- Expected policy decision (`allow`, `deny`, or `review`)
- Audit event or request ID
- Whether any order, document, or refund state changed
- Fix and regression test, if the attempt found a bypass

The report must never contain a real Telegram token, API key, or private user data.
