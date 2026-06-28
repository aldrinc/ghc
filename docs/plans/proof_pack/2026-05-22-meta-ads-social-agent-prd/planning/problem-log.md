# Problem Log

Observable problems:

- The current Meta connection path is token-paste oriented and not suitable as the primary customer self-serve connection flow.
- mOS has partial Meta post-publish management and publish logic, but not a durable OAuth plus asset-grant layer for customer accounts.
- Hermes has runtime projection infrastructure, but no dedicated connected Meta/social manager profiles or tool authority contract.
- Paid ads management and social posting can share account, approval, action logging, and provider execution machinery, but would drift if designed as separate one-off integrations.
- Social posting raises a different write risk from ads: publishing public content on behalf of a brand. The PRD must make approval and audit first-class.
