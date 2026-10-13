# Service termination investigation
<!-- services: checkout-api,gateway -->

## Check process lifecycle
Compare runtime die, exit code, start and restart timestamps with failed requests.
A die event followed by start supports a terminated process that recovered.
Review container lifecycle observations and the reason for the exit. These checks
are read-only; do not restart, kill or change configuration during investigation.

## Test competing dependencies
Compare gateway ERROR logs, error traces and HTTP counters inside the incident
window. A downstream timeout is a symptom and does not establish a database or
network root cause. Inspect matching traces for where failure first appears.

## Establish recovery
Compare later successful requests and the start event. Recovery does not erase
prior termination. Request a human review of termination cause and restart policy.
