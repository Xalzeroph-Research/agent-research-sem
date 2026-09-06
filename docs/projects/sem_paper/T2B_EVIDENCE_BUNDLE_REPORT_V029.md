# T2B Evidence Bundle + T3 Unlock Guard Report — v0.29

## Status

- T0 deterministic contracts: PASS
- T1 synthetic small-DAG integration: PASS
- T2A Mineflayer integration harness: PASS
- T2B local vanilla gate harness: PASS
- T2B live vanilla world in hosted environment: BLOCKED_BY_ENVIRONMENT
- T3: LOCKED

## v0.29 changes

1. Evidence bundle schema upgraded from `t2b-evidence-v1` to `t2b-evidence-v2`.
2. Passing evidence export now requires and packages:
   - `server.properties`
   - `eula.txt`
   - persistent world `<level-name>/level.dat`
3. Bundle verifier cross-checks `level-name` and `server-port` against the recorded server identity, verifies `eula=true`, verifies non-empty `level.dat`, and hashes all physical members.
4. Added repository-local `T3_UNLOCK.json` workflow guard.
5. `T3_UNLOCK.json` can only be created from a T2B PASS evidence bundle that verifies against the exact current source-tree fingerprint.
6. Unlock verification rechecks bundle SHA256, gate run ID, source-tree fingerprint, server identity, Seed contract hashes, and unlock-record integrity.
7. The unlock mechanism is explicitly not remote attestation or scientific-result certification.

## Regression

```text
pytest -q                       PASS (52 tests)
python -m compileall -q .      PASS
node --check bridge.js         PASS
```

Hosted canonical gate remains blocked before server startup because Mineflayer 4.37.1 is not installed/resolvable in the execution container. A blocked gate cannot be exported as evidence and therefore cannot unlock T3.
