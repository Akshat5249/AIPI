# Dependency latency investigation
<!-- services: gateway,checkout-api,orders-api,pg-lag-probe -->

## Compare matching operations
Compare latency and failed-span rates with the early-window baseline for matching
operations and services. Review timeout error types and retry counts. Avoid mixing
healthy database operations with HTTP request latency in a single baseline.

## Preserve competing explanations
Timeouts and stale reads can arise after a process exit or replication delay.
Review lifecycle events, replay gauges and primary health before blaming network
or primary database availability. Missing evidence is uncertainty, not support.
