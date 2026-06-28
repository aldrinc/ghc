# DSV4 Step 4 Sidecar Verification

## Commands

- `uv run python -m py_compile app/config.py app/services/deerflow_foundational.py app/temporal/activities/strategy_v2_activities.py scripts/run_deerflow_foundational_step.py tests/test_strategy_v2_foundational_step01_provider.py tests/test_config_env_precedence.py` — PASS
- `uv run ruff check app/services/deerflow_foundational.py scripts/run_deerflow_foundational_step.py tests/test_strategy_v2_foundational_step01_provider.py --select E501,I001` — PASS
- Manual no-DB routing checks for GPT Step 4 provider, DSV4 Step 4 provider, and DSV4 validator — PASS
- `provcheck proof_pack/dsv4-step04-synthesis-smoke-2026-05-21/raw.md` — PASS with 7 warnings

## Pytest Blocker

`uv run pytest tests/test_strategy_v2_foundational_step01_provider.py tests/test_config_env_precedence.py` is blocked by local Postgres on `localhost:5433` refusing connections before tests load.

Using SQLite is not a valid substitute because Alembic migration `0001_init_schema.py` executes `CREATE EXTENSION IF NOT EXISTS "pgcrypto";`.

## Live DSV4 Smoke

Ran synthesis-only DSV4 smoke using already-paid Step 4 DeerFlow event evidence. No Serper calls.

- Status: PASS
- Input tokens: 44,167
- Output tokens: 16,737
- Total tokens: 60,904
- Estimated DeepSeek promo cost: $0.0338
- Estimated DeepSeek list cost: $0.1351
- Elapsed: 518.298s
- Content chars: 64,211
- Quote count: 69
- Source count: 69
