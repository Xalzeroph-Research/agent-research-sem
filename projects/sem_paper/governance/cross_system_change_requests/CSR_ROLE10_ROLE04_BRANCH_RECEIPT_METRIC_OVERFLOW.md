# CrossSystemChangeRequest — ROLE04 BranchReceipt metric overflow

- request_id: `CSR-ROLE10-20260829-ROLE04-BRANCH-RECEIPT-METRIC-OVERFLOW`
- requester role/system: `ROLE 10 — SEM Composition / Experiment Integration`
- target owner/system: `ROLE 04 — Experimentation / Scientific`
- status: `TARGET_OWNER_ACTION_REQUIRED`

## Problem

On platform master `27422060825f673ffc3d4b3d98b4da0f3a0338fb`, constructing `BranchReceipt(metrics=(("utility", 10**10000), ...))` reaches `_require_metrics()` in `research_platform/experimentation/evaluation/api/contracts.py` and calls `math.isfinite(metric)`.

For sufficiently large Python integers this raises raw `OverflowError: int too large to convert to float` instead of the evaluation contract's defined fail-closed validation error.

## Required capability

Validate numeric finiteness/range without allowing conversion overflow to escape as an implementation exception. Preserve strict rejection of bools, strings, non-finite floats, malformed rows and duplicate metric names.

The fix belongs upstream in ROLE 04. ROLE 10 must not patch `research_platform/**` in the downstream fork.

## Acceptance tests

- Huge integers are rejected deterministically with the platform's documented validation exception class.
- `nan`, `+inf`, `-inf`, bool and string metric values remain rejected.
- Ordinary finite integer/float metrics remain accepted.
- Evaluation contract/component tests pass on Windows and required platform validation remains green.
