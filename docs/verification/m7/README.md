# M7 local verification

Final source gate: two consecutive full make test runs passed on this Apple Silicon
machine in the isolated README clone. Each ran 140 Python tests (24 live Docker,
none skipped) and 26 Vitest/RTL tests across four files. Python durations were
355.71s and 383.50s; UI durations 2.68s and 1.68s. See final-test-1.txt and
final-test-2.txt. Lint/types passed (151 Python files formatted, 66 source files
strict mypy, ESLint/tsc). GitHub CI has NOT run; no push was performed.

The clone is /tmp/aipi-m7-release-clone.OfjsPE/aipi, project
 aipi-fresh-check-1792187061, with separate loopback ports
15432/15433/18000/18080/15173/14318/23133 and generated clone-only credentials.
It is a local clone of HEAD 9e9a840 plus the uncommitted non-ignored candidate,
so no phase commit preceded its gate. No existing .env, dependencies or volume
was copied. All 173 tested non-document files matched the working candidate.
README setup-env/setup/demo commands, native builds, health, real kill/recovery,
incident/investigation, recorded scoring and three golden gates passed; see
final-fresh-clone.txt. Older candidate passes are explicitly named candidate-*.

Final demo: incident 9eab8cfe-f38f-4b97-aa64-c74712bd0757;
investigation 0d1e3e90-4eb5-4575-841c-d6f7a8196aef;
evaluation b8aa2f3f-b18d-4869-8909-2fba6689a92b passed, 342/342 supported citation
pairs, unsupported=0. The historical n=3-per-scenario M5 experiment is unchanged.
Focused final live evidence replay: 1.21s / 0.31s requests, identical 50 IDs,
full-scope rules unchanged by selection; see batched-live-regression.txt.

The measured host has 8 GiB RAM. During diagnosis it used about 7.5 GiB swap and
the Docker VM held about 4.3 GiB file cache. One clean page-cache release reduced
that cache to about 0.7 GiB; no files/volumes were deleted and no persistent Docker
setting changed. The final two tests ran consecutively without another cache
release or source change. Bulk ingest and nominal background default 1 cycle/s
reduce pressure while foreground fault probes and every evidence/rule assertion
remain required. These are local mock measurements, not real-LLM accuracy figures.

Both final PG containers have init=true and wal_keep_size=512MB; crash-recovery
log event counts were 0 / 0 across both suites. All three project-built images
and the PostgreSQL/Collector/actionlint/gitleaks images inspected linux/arm64.
init-reproduction.jsonl records a separate network-none/tmpfs control: orphan
exit 2 caused one crash recovery without init and zero with init. An open-session
live test verifies real backend survival rather than postmaster start time.

Original .env checksum: unchanged. Original volumes were never reset/removed.
The explicitly authorized legacy cleanup matched only future (>now+1 day) exact
synthetic test signatures: logs 3523→0, events 1392→0, metrics 116→0, spans 28→0,
50 legacy UUID prefixes (legacy-cleanup.jsonl). Tests now remove exact source IDs
plus a unique marker in finally with admin permissions. A controlled failure
removed four owned rows and retained an unrelated same-window sentinel.

The original main standby is stopped/preserved: it lost a required WAL segment
and cannot catch up by waiting. No reseed was authorized/performed. This is an
existing-data recovery exception outside the requested isolated fresh-clone gate;
see PROGRESS F052 and replica-recovery-plan.md. Primary/evaluation data and .env
are retained. A replica-only reseed requires separate explicit authorization.

Tracked files above 5,000,000 bytes:

| File | Bytes | Why retained |
|---|---|---|
| tests/fixtures/scn-001.json | 7,523,593 | Complete recorded scoped telemetry and raw rule witnesses for replay/outside-bundle validation |
| tests/fixtures/poisoned-log.json | 7,524,096 | Same real kill window plus one clearly synthetic poisoned log; directly readable/replayable regression |

JSON stays uncompressed for review, direct schema validation and the existing
loader. Truth stays separate in *.truth.json. Maximum tracked/historical blob is
7,524,096 bytes; no historical blob is >=100 MB. .gitignore excludes .env variants
(except example), .venv, node_modules and caches; MIT LICENSE exists.
Full-history gitleaks uses git --log-opts=--all: 12 reachable pre-phase commits,
20.20 MB, no leaks. A candidate source scan supplements history; it never replaces
it. Local actionlint 1.7.7 passed; hosted CI remains unrun.
