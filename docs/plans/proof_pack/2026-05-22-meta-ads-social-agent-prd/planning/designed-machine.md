# Designed Machine

Designed mOS machine:

1. User connects Meta through OAuth.
2. mOS stores encrypted token metadata and provider connection state.
3. mOS inventories businesses, ad accounts, Pages, Instagram business accounts, campaigns, ads, creatives, and posts.
4. Workspace/admin grants selected provider assets to a workspace/client.
5. mOS syncs raw provider payloads and normalized snapshots.
6. Hermes receives only mOS tools and snapshots.
7. Hermes creates diagnoses, drafts, and action proposals.
8. User approval gates every external write in v1.
9. mOS executes approved provider writes.
10. mOS records provider responses and reconciles provider truth.

This machine supports both paid ads management and social posting without duplicating auth, approval, and audit code.
