# AI Incident Response Agent

An autonomous incident-response platform. When a production alert fires, a LangGraph
agent investigates like an on-call SRE — pulling recent commits, logs, and metrics,
retrieving the matching runbook via RAG, checking similar past incidents, and running
an ML severity model — then ranks root-cause candidates **with explicit reasoning about
why it might be wrong**, posts a Slack incident brief, and writes the postmortem when
the incident resolves. Every step of the agent's reasoning is persisted as an
inspectable trace.

**Stack:** FastAPI · LangGraph · Anthropic Claude · ChromaDB + LangChain (RAG) ·
scikit-learn · PostgreSQL · React · Docker

## Evaluation results

| Metric | Result |
|---|---|
| **Root-cause attribution, top-1 accuracy** (12-case eval set with planted culprit commits) | **83.3%** (10/12) |
| **Root-cause candidate recall** (culprit appears in the agent's candidate list) | **100%** (12/12) |
| **ML severity model accuracy** (held-out test set, n=375) | **86.9%** |
| **ML severity model macro-F1** | **0.854** |

The eval set (`data/eval_incidents.json`) contains 12 synthetic incidents, each a
self-contained evidence world with one known bad commit, one decoy, and shared benign
commits — including two deliberately adversarial cases (a culprit with an
innocent-looking commit message, and a 30-hour-old slow-burn change) that the ranker
misses by design. Reproduce with:

```bash
cd backend && python -m app.ml.train && python -m app.ml.eval_agent
```

## Architecture

```
                 ┌──────────────────────────────────────────────────────────────┐
                 │                        docker compose                        │
                 │                                                              │
 Alertmanager-   │  ┌────────────┐   POST /alerts/webhook   ┌────────────────┐  │
 compatible ────────▶  FastAPI    ├─────────────────────────▶ incident_service│  │
 simulator       │  │  backend   │   dedupe by fingerprint  └───────┬────────┘  │
 (scripts/)      │  └─────┬──────┘                                  │           │
                 │        │ background task                         ▼           │
                 │        ▼                                  ┌─────────────┐    │
                 │  ┌───────────────────────────────┐        │ PostgreSQL  │    │
                 │  │   LangGraph triage agent      │◀──────▶│ incidents   │    │
                 │  │  ┌───────┐      ┌─────────┐   │ traces │ alert_events│    │
                 │  │  │ agent │◀────▶│  tools  │   │        │ agent_runs  │    │
                 │  │  └───┬───┘      └────┬────┘   │        │ trace_steps │    │
                 │  └──────┼───────────────┼────────┘        │ slack_msgs  │    │
                 │         │               │                 └─────────────┘    │
                 │   Claude API      commits/logs/metrics (data/)               │
                 │   (or MOCK_LLM)   ChromaDB runbook RAG (MiniLM, local)       │
                 │                   sklearn severity model · historical PG     │
                 │         │                                                    │
                 │         ▼                                                    │
                 │   Slack brief (Block Kit) ──▶ stored + optional webhook      │
                 │   Postmortem on resolve                                      │
                 │                                                              │
                 │  ┌────────────┐  /api proxy   ┌───────────┐                  │
                 │  │ React      │◀──────────────│  nginx    │  :3000           │
                 │  │ dashboard  │               └───────────┘                  │
                 │  └────────────┘                                              │
                 └──────────────────────────────────────────────────────────────┘
```

**Agent tools** (each call traced to Postgres): `get_recent_commits`, `search_logs`,
`query_metrics`, `retrieve_runbook` (ChromaDB semantic search, keyword fallback),
`find_similar_incidents`, `predict_severity` (trained sklearn model, heuristic
fallback), `rank_likely_commits`. Slack brief and postmortem generation run as
deterministic steps — every incident gets them.
