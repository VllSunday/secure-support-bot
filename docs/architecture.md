# Security architecture

The model is not a trust boundary. The application assumes that user text or retrieved content may
successfully manipulate an LLM and limits what a compromised model can observe or cause.

## Trust boundaries

1. Telegram supplies the external user identifier.
2. The identity service resolves an immutable internal actor context.
3. Retrieval applies the company predicate before ranking documents.
4. Language-model components receive only the minimum data needed for their role.
   The optional answer model sees quarantined document facts as user data and has no tools.
5. The action gateway validates a strict allow-list and never accepts permissions from model output.
6. The refund service repeats authorization and balance checks immediately before its transaction.

## Refund decision lattice

- Any failed deterministic policy check results in `deny`.
- A risk timeout, unavailable checker, or explicit `review` result stops the operation for review.
- Execution is possible only when all mandatory checks return `allow`.

Confirmation is stored as an immutable pending action. Its HMAC fingerprint binds the actor,
company, order, amount, currency, request ID, and order version. The Telegram callback contains only
an opaque random token.

