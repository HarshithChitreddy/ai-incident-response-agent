# Runbook: Database Connection Pool Exhaustion

**Applies to alerts:** DBConnectionPoolExhausted

## Symptoms
- Zero idle connections; requests queue waiting for a connection and eventually time out (503s).
- Latency grows unbounded while database CPU may look healthy — the bottleneck is the pool, not the database.

## Triage
1. Check whether pool configuration changed recently (pool size, overflow, timeout) — a "cost cleanup" that shrinks the pool is a classic cause.
2. Look for long-running transactions or queries holding connections: check pg_stat_activity for sessions in `idle in transaction` or long `active` states.
3. Check whether a new batch job, reporting query, or migration started around onset.
4. Confirm actual connection demand: pool waiters + in-use count vs configured size.

## Mitigation
- **Config change:** restore the previous pool size / overflow settings and redeploy or hot-reload.
- **Connection leak / long transactions:** terminate offending backends (pg_terminate_backend) after confirming they are safe to kill; fix the leaking code path.
- **Genuine demand growth:** raise pool size within database max_connections headroom, or add a pooler (pgbouncer) in transaction mode.

## Escalation
- Escalate to the database platform team if max_connections on the server itself is the limiting factor.

## Verification
- Idle connections consistently above zero and no pool-wait timeouts for 15 minutes.
