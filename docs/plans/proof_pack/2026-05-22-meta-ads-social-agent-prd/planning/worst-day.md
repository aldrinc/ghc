# Worst-Day Test

The PRD must protect against:

- wrong Meta account connected
- wrong ad account, Page, or Instagram business asset granted
- token expiry during sync or execution
- missing provider scopes
- Meta API rate limits
- Hermes proposing an unsafe external write
- duplicate social post publish
- missing media for scheduled post
- provider mutation succeeds but mOS writeback fails
- provider data disappears or changes shape

Safe failure rules:

- no silent fallback
- no fabricated metrics
- no direct Hermes access to raw tokens
- no unapproved external write
- clean error states and repair path
- idempotent provider writes where possible
- reconciliation can recover external truth
