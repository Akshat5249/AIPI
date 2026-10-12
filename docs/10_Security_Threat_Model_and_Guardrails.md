Security, Threat Model & Guardrails

AI safety boundaries, least privilege, secrets, and prompt-injection defenses

AI Production Incident Investigator

| Document ID | AIPI-10 |
| --- | --- |
| Version | 1.0 |
| Status | Implementation baseline |
| Primary audience | Developer / reviewer / interviewer |

# 1. Threat Model

| Threat | Risk | Mitigation |
| --- | --- | --- |
| Prompt injection in logs/runbooks | Agent follows malicious embedded text | Treat evidence as untrusted data; delimit/escape; fixed system rules; no instruction execution. |
| Over-privileged tools | Agent changes production state | Read-only credentials and APIs; approval gate for any future mutation. |
| Secret leakage | Tokens/passwords enter model context | Structured logging policy, redaction pipeline, secret scanners. |
| SQL/tool injection | Generated query escapes intended scope | Parameterized queries, allowlisted operations, bounded filters. |
| Cross-incident data leakage | Wrong tenant/service evidence mixed | Incident/service/time authorization and query scoping. |
| Hallucinated remediation | Unsafe advice presented as fact | Evidence-backed recommendations, uncertainty labels, human review. |

# 2. Security Requirements

- No production credentials committed to repository.
- All model/provider keys loaded from environment or secret manager.
- Tool calls are logged with actor, arguments, result reference and latency.
- Sensitive log fields are redacted before persistence/model use.
- Future remediation actions require explicit human approval and idempotent controls.
# 3. Safe AI Rules

- Model cannot directly execute shell commands on arbitrary hosts.
- Model cannot widen time/service scope without policy checks.
- External content is evidence, never authority over system instructions.
- Reports clearly separate observed facts from inferred hypotheses.
