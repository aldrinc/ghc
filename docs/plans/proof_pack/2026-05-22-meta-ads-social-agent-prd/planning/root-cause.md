# Root-Cause Diagnosis

Root cause: mOS currently treats Meta connectivity as a campaign/config feature, not as a first-class connected-account platform.

That creates three design gaps:

- Identity gap: no customer-grade OAuth, asset grants, scope health, and reconnect loop.
- Data gap: provider truth is not normalized into shared social/ad snapshots with raw provenance.
- Authority gap: Hermes can reason, but the product needs a durable action proposal and approval ledger before external writes.

The fix is not "add another agent." The fix is a connected-account and action-control layer that agents use.
