# Runbook: Memory Growth / Suspected Leak

**Applies to alerts:** HighMemoryUsage

## Symptoms
- Container memory climbing steadily over hours with flat traffic; GC pause times increasing.
- Ends in OOM kill and restart if untreated — watch for a sawtooth restart pattern.

## Triage
1. Correlate the growth start time with deploys: an in-process cache or buffer added without eviction is the most common cause.
2. Check logs for object/entry counts (cache sizes, queue depths) that grow monotonically.
3. Confirm it is heap growth, not a legitimate working-set increase (compare traffic and batch sizes against baseline).
4. Check downstream consumers: producers buffering in memory while a consumer lags looks identical to a leak.

## Mitigation
- **Immediate:** schedule a rolling restart before OOM to reset heap without dropping traffic. This buys time; it is not a fix.
- **Cache without eviction:** ship a bounded cache (LRU + TTL) or disable the cache via feature flag; roll back the introducing commit if faster.
- **Consumer lag:** scale the consumer or apply backpressure at the producer.

## Escalation
- Escalate if restarts are needed more than once per day — that cadence means the leak is fast enough to risk correlated OOM across replicas.

## Verification
- Memory stable (±5%) over 6 hours at normal traffic after the fix.
