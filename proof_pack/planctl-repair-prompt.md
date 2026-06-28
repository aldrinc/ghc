# Plan Repair Prompt

Goal: repair the implementation until the plan contract passes.

Plan ID: `ragflow-bge-m3-parallel-retrieval`
Contract: `/Users/aldrinclement/Documents/programming/marketi/docs/plans/2026-05-27-ragflow-bge-m3-parallel-retrieval-plan.md`
Repair JSON: `/Users/aldrinclement/Documents/programming/marketi/proof_pack/planctl-repair.json`

Rules:
- Read the original plan and contract before editing.
- Fix only the failing or brittle items.
- Update item status, artifacts, and notes in the contract.
- Run verification again with `planctl verify <contract> --run`.

Errors:
- none

Warnings:
- P01: no verify_commands
- P02: no verify_commands
- P03: no verify_commands
- P05: no verify_commands
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:619: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:619: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:619: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1589: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1589: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1589: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1589: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1589: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1589: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1619: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1619: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1619: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1619: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1619: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1619: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1635: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1635: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1635: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1635: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1635: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1635: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1670: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1670: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1670: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1670: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1670: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1670: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1691: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1691: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1691: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1691: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1691: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1691: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1711: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1711: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1711: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1711: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1711: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1711: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:619: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:619: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:619: brittle marker `placeholder`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1589: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1589: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1589: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1589: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1589: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1589: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1619: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1619: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1619: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1619: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1619: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1619: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1635: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1635: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1635: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1635: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1635: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1635: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1670: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1670: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1670: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1670: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1670: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1670: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1691: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1691: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1691: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1691: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1691: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1691: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1711: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1711: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1711: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1711: brittle marker `allow_estimate`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1711: brittle marker `agent_fabricated`
- /Users/aldrinclement/Documents/programming/marketi/proof_pack/index.html:1711: brittle marker `allow_estimate`
- P07: no verify_commands
- P08: no verify_commands
- P09: no verify_commands
- P10: no verify_commands
- P11: no verify_commands
- P12: no verify_commands
- P13: no verify_commands
- P14: no verify_commands
