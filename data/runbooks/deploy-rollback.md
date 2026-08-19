# Runbook: Deploy Rollback Procedure

**Applies to:** any incident where a recent deploy is the leading root-cause candidate.

## When to roll back
- Error rate, latency, or resource regression began within ~60 minutes of a deploy to the affected service or a direct upstream.
- Roll back first and investigate second — a rollback is cheap and reversible; debugging forward in production is neither.

## Procedure
1. Identify the currently running release and the previous known-good release:
   `kubectl -n prod get deploy <service> -o jsonpath='{.spec.template.spec.containers[0].image}'`
2. Announce the rollback in the incident channel with the target version.
3. Roll back: `kubectl -n prod rollout undo deploy/<service>` (or re-deploy the previous image tag through CI if undo history is unavailable).
4. Watch the rollout: `kubectl -n prod rollout status deploy/<service>` — confirm all replicas become ready.
5. Verify the triggering metric (error rate / latency / memory) returns toward baseline within 10–15 minutes.

## If rollback does not recover the metric
- The deploy was likely a trigger, not the cause (e.g. it restarted pods and reset caches). Re-examine dependencies and configuration changes.
- Do not roll back a second version blindly; escalate to the service owner.

## Post-rollback
- Keep the incident open until baseline holds for 15 minutes.
- File a ticket linking the offending commit; the fix must land with a test covering the regression.
