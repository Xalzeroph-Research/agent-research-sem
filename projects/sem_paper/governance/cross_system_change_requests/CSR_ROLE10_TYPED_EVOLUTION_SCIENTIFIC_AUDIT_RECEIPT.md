# CrossSystemChangeRequest ? Typed Evolution Scientific Audit Receipt

- request_id: `CSR-ROLE10-20260829-TYPED-EVOLUTION-SCIENTIFIC-AUDIT`
- requester_system: `ROLE 10 ? SEM Composition / Experiment Integration`
- target_system: `ROLE 09 ? SEM Method / Self-Evolving Memory`
- problem: Production composition has no authoritative producer for the pre-registered `ELCE`, `HPEF`, and `GAG` seed samples. Existing `ScientificAuxiliarySampleEvidence` instances are created only in tests.
- root cause: The method evaluation seam exposes `EvaluationProof.metrics: dict[str, float]` and `J_eval/J_audit` rows expose generic `JsonValue` payloads. They do not expose a typed, digest-bound receipt joining the accepted edit, evaluation checkpoint, disjoint GateSpec/AuditSpec, paired control/candidate outcomes, gate delta, held-out audit delta, and evidence refs.
- current contract: `EvaluationProof(comparability, metrics)` plus generic `AuditEvidence` / `EvalEvidence` payloads.
- required capability: A typed immutable scientific audit receipt emitted by the method evaluation authority for each audited accepted edit, with stable schema/version/digest and explicit gate/audit provenance.
- proposed contract: A receipt carrying `candidate_id/edit_id`, base/target generation, evaluation checkpoint/cut digest, GateSpec digest, AuditSpec digest, comparability digest, gate effect, held-out paired effect, accepted/adopted disposition, source evidence refs, and run/seed identity. The receipt must fail closed on missing or mixed provenance and must not be synthesized from observation logs.
- affected callers: ROLE 10 scientific auxiliary producer/finalizer, scientific closure, future held-out edit audit reporting.
- authority impact: Establishes the method evaluation authority as the sole producer of edit-local gate/audit causal receipts; ROLE 10 remains aggregation/finalization authority.
- persistence impact: Receipt must be durable or exported through an existing durable evidence authority before claim closure.
- failure/recovery impact: Resume must not duplicate, overwrite, or mix an audit receipt across candidate/checkpoint identities.
- scientific semantics impact: Required to implement the frozen held-out `ELCE`, `HPEF`, and `GAG` definitions without inference from untyped dictionaries or telemetry.
- breaking change: `YES`; replacing weak `dict[str, float]` / generic payload consumption for claim-eligible scientific audit data is preferred over a permanent compatibility shim.
