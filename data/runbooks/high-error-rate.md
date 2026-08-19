# Runbook: High Error Rate (5xx)

**Applies to alerts:** HighErrorRate
**Severity guidance:** critical if user-facing checkout/payment paths are affected.

## Symptoms
- 5xx error rate above 2% for 5+ minutes on a production service.
- Often accompanied by rising p95 latency and elevated upstream timeouts.

## Triage
1. Check the deploy timeline: was this service (or a direct upstream) deployed in the last 2 hours?
   A deploy within the hour is the root cause in roughly 60% of past HighErrorRate incidents.
2. Identify the failing endpoint(s) from logs — filter ERROR level for the service and group by logger/route.
3. Check whether errors are timeouts (upstream problem or too-tight deadlines) vs application exceptions (bad code path).
4. Compare the service's request rate against baseline — a retry storm shows up as request volume rising *with* the error rate.

## Mitigation
- **Recent deploy suspected:** roll back first, investigate second (see deploy-rollback runbook). Do not debug forward in prod.
- **Timeout misconfiguration:** if a client deadline was tightened below the upstream's actual latency, revert the timeout config; disable aggressive retries (retries without backoff amplify the outage).
- **Upstream dependency degraded:** engage the upstream team, enable circuit breaker / fallback path if available, and shed non-critical traffic.

## Escalation
- Page the owning team if error rate exceeds 10% or revenue-critical flows (checkout, payment) are failing.
- Open an incident channel and post the incident brief.

## Verification
- Error rate back under 1% for 15 consecutive minutes.
- No elevated retry volume against upstreams.
