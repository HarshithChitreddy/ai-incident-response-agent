# Runbook: High p95 Latency

**Applies to alerts:** HighLatencyP95

## Symptoms
- p95 latency above SLO threshold for 10+ minutes while error rate stays low-to-moderate.
- CPU often climbs with latency; request rate may be flat (code regression) or elevated (traffic-driven).

## Triage
1. Determine whether latency rose gradually (data growth, cache decay, traffic ramp) or as a step change (deploy, config flip).
2. Check recent commits for changes to query construction, serialization, fan-out, or anything that multiplies downstream work per request.
3. Inspect downstream dependencies (database, search cluster, external APIs) — is the slowness local or inherited?
4. Look for slow-query or long-span warnings in logs; note payload/clause sizes if the service builds dynamic queries.

## Mitigation
- **Step change after deploy:** roll back the deploy.
- **Query amplification (e.g. unbounded expansion, N+1):** cap the expansion/fan-out via config if available, else roll back.
- **Traffic-driven:** scale out replicas, verify autoscaler thresholds, and enable rate limiting for abusive clients.
- **Downstream-driven:** shift to cached/fallback responses where supported and escalate to the downstream owner.

## Escalation
- Escalate to the owning team if p95 exceeds 3x SLO or timeouts start converting latency into 5xx errors.

## Verification
- p95 back under threshold for 15 minutes at normal traffic.
