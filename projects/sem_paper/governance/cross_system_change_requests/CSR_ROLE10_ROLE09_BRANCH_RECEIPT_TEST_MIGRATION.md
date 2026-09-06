# CrossSystemChangeRequest — ROLE09 BranchReceipt contract migration

- request_id: `CSR-ROLE10-20260829-ROLE09-BRANCH-RECEIPT-TEST-MIGRATION`
- requester role/system: `ROLE 10 — SEM Composition / Experiment Integration`
- target owner/system: `ROLE 09 — SEM Method`
- status: `TARGET_OWNER_ACTION_REQUIRED`

## Problem

After ROLE 10 synchronized platform `master` at `27422060825f673ffc3d4b3d98b4da0f3a0338fb`, the integrated SEM matrix reports ten failures in `tests/test_sem_deluxe_evaluator_v1.py`.

The failures are not evaluator regressions. ROLE 04 moved malformed `BranchReceipt` rejection into the platform-owned `BranchReceipt.__post_init__` contract. The ROLE 09 tests still attempt to construct invalid receipts first and expect the SEM evaluator to reject them later.

## Required owner migration

Update the ROLE 09 method tests so malformed metric rows, invalid receipt identity fields, and non-finite/unsupported metric values assert rejection at the authoritative `BranchReceipt` construction boundary. Keep evaluator tests for valid receipts and evaluator-owned semantics only.

Do not weaken the new platform fail-closed contract and do not add downstream compatibility objects that bypass `BranchReceipt` validation.

## Acceptance

- `tests/test_sem_deluxe_evaluator_v1.py` passes against platform master `2742206` or a later accepted upstream master.
- Invalid `BranchReceipt` inputs are proven rejected at construction.
- Valid receipt evaluation behavior remains covered.
- ROLE 09 branch remains clean and pushed after the migration.
