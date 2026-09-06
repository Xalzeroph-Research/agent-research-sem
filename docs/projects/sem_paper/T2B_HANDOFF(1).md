# T2B Local Handoff and Evidence Bundle

This file is the canonical handoff for completing the **live vanilla Minecraft T2B gate** outside the hosted container.

## 1. Prerequisites

- Java 21+ (or the version required by the selected official Minecraft Java server)
- Node.js >= 22
- network access to npm during dependency installation
- official Minecraft Java Edition `server.jar`

Install the exact Mineflayer dependency:

```bash
./scripts/t2b_install_bridge_deps.sh
```

Run deterministic regression first:

```bash
pytest -q
python -m compileall -q .
node --check mc_runtime/mineflayer_bridge/bridge.js
```

## 2. Run the canonical live gate

```bash
python scripts/t2b_local_gate.py \
  --server-jar /absolute/path/to/server.jar \
  --workdir .t2b-local-server \
  --auth offline
```

A valid pass requires:

- one Java server process for both Seed-C and Seed-X;
- the same level directory for both seed runs;
- both live Mineflayer smokes pass;
- retrieved records have non-empty `source_refs`;
- all retrieved/materialized `source_refs` resolve only to canonical `J_mem` evidence;
- zero `J_audit` evidence reaches materialized memory;
- Meta / Evolution Monitor / Candidate Gate remain disabled.

The result must report:

```text
status = T2B_GATE_PASS
failure_class = NONE
same_server_process_for_both_seeds = true
```

## 3. Export the evidence bundle

Only a passing gate is exportable:

```bash
python scripts/t2b_export_evidence.py \
  --gate-result T2B_GATE_RESULT.json \
  --server-workdir .t2b-local-server \
  --output T2B_EVIDENCE_BUNDLE.zip
```

This produces:

```text
T2B_EVIDENCE_BUNDLE.zip
T2B_EVIDENCE_BUNDLE.zip.sha256
```

The v0.29 `t2b-evidence-v2` bundle contains:

- gate result;
- gate/server manifest;
- vanilla server log;
- exact `server.properties` and `eula.txt`;
- the persistent world `level.dat`;
- runtime/source provenance;
- source-tree fingerprint;
- Seed-C / Seed-X contract hashes;
- Node / Java / Mineflayer / Python versions;
- server.jar SHA256;
- grounding audit results.

## 4. Verify before T3 unlock

Against the exact checkout that produced the run:

```bash
python scripts/t2b_verify_evidence.py T2B_EVIDENCE_BUNDLE.zip
```

Expected:

```json
{"ok": true}
```

Use `--skip-repo-match` only to inspect an evidence bundle from a different checkout. That mode verifies bundle-internal integrity but intentionally does **not** claim that the local source tree matches the run. It must never be used to unlock T3.

## 5. Create the repository-local T3 unlock record

Only after the normal verifier returns `ok=true` **with repo matching enabled**:

```bash
python scripts/t3_unlock.py create T2B_EVIDENCE_BUNDLE.zip
python scripts/t3_unlock.py verify T2B_EVIDENCE_BUNDLE.zip
```

Expected record status:

```text
T3_UNLOCKED_BY_T2B
```

The unlock record binds the PASS bundle SHA256, gate run ID, exact T2 source-tree fingerprint, server identity and Seed contract hashes. A bundle from another checkout, a tampered unlock record, or any non-PASS bundle cannot create a valid unlock.

## Claim boundary

The evidence bundle is an **integrity and reproducibility artifact**. It is not trusted remote-execution attestation and does not prove that a malicious machine could not fabricate files. Its purpose is to prevent accidental run mixing, source/version drift, seed mismatch, provenance loss, and manual log interpretation.
