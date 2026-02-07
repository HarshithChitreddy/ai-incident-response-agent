# AI Incident Response Agent

## Project Overview
Build an autonomous AI-powered incident response platform that reacts when a production alert fires. The system collects context from recent commits, logs, metrics, and runbooks, ranks the likely root cause, estimates user impact, posts a Slack-style incident brief, and generates a postmortem after the incident is resolved.

Build this as a production-style project, not a toy demo.

## Core Tech Stack
- Backend: Python + FastAPI
- Agent workflow: LangGraph
- RAG: LangChain + ChromaDB (persisted locally)
- LLM: Anthropic API
- ML: Scikit-learn / XGBoost for severity prediction or root-cause ranking
- Data processing: Pandas
- Database: PostgreSQL
- Frontend: React
- Alerting: synthetic alert webhook simulator as the primary path (Prometheus/Alertmanager-compatible schema, no real Prometheus infra)
- Notifications: Slack API or Slack-style mock webhook
- Deployment: Docker + docker-compose
- Testing: Pytest, written alongside each phase, not saved for the end
- Documentation: Clean README with setup, architecture, screenshots, resume bullet examples

## Main Flow
1. A production alert fires (synthetic simulator, Prometheus-compatible schema).
2. FastAPI receives the alert through a webhook endpoint.
3. FastAPI triggers a custom Incident Triage Agent built with LangGraph.
4. The agent collects context: recent GitHub commits, sample application logs, metrics (error rate, latency, request volume, CPU/memory), relevant runbooks via RAG, historical incidents from PostgreSQL.
5. ML model predicts incident severity and/or ranks likely root-cause commits.
6. LLM analyzes the collected evidence and generates: likely root cause with explicit reasoning about why it might be wrong (competing candidate commits, ambiguous evidence), confidence score, user impact estimate, recommended runbook steps, Slack incident brief.
7. Every agent step (tool called, input, output, reasoning for next step) is logged to PostgreSQL as an agent trace, alongside the incident, timeline, analysis, and status.
8. React dashboard displays: active incidents, alert details, recent commits, logs/metrics summary, retrieved runbook, AI analysis, step-by-step agent reasoning trace, Slack brief, generated postmortem.
9. When incident is marked resolved, generate a postmortem report with: summary, timeline, root cause, impact, resolution, action items, prevention steps.

## Build Priority (solo dev, limited time)
Treat Phases 1-3 + 5 as the non-negotiable core (alert -> agent reasoning -> RAG runbook match -> Slack brief). Phase 4 (ML) and Phase 6 (React) are high-value additions built only after the core loop works end-to-end. If time runs short, tell me explicitly what to cut and how to degrade gracefully (e.g., skip React and demo via API/Postman + terminal output; skip ML and use heuristic severity scoring) without breaking the core story.

## Phases
- Phase 1: Clean project structure. FastAPI backend. /alerts/webhook endpoint accepting realistic alert JSON (Prometheus-compatible schema). Store alert/incident in PostgreSQL. Seed data for alerts, logs, metrics, runbooks, commits. Docker setup. Basic Pytest coverage for the webhook endpoint.
- Phase 2: LangGraph Incident Triage Agent. Tools: get_recent_commits, search_logs, query_metrics, retrieve_runbook, predict_severity, rank_likely_commits, generate_slack_brief, generate_postmortem. Log every tool call and its output as an agent trace in Postgres. Keep the workflow readable and modular. Tests for each tool.
- Phase 3: RAG over runbooks using ChromaDB, persisted locally. Retrieve based on alert + logs. Tests for retrieval relevance.
- Phase 4: ML component. Train Scikit-learn/XGBoost on sample historical incident data to predict severity or rank root-cause commits. Feature engineering with Pandas. Evaluation metrics: accuracy, F1, precision/recall, confusion matrix or ranking quality. Save and load the trained model at runtime. Also build a small eval set (~10-15 synthetic incidents with known correct bad commits) to measure the agent's root-cause accuracy, not just the ML model's — report this number too.
- Phase 5: Slack-style integration — real Slack API or a mock webhook that stores/generates messages. Realistic incident update message format. Tests for message formatting.
- Phase 6: React dashboard — incident list, incident detail page, AI analysis panel, runbook panel, agent reasoning trace timeline, Slack brief preview, postmortem viewer.
- Phase 7: Final test pass to fill any gaps. README with architecture diagram (markdown), example API requests, screenshots placeholders, resume bullet examples, and both eval numbers (ML model + agent accuracy) featured prominently.

## Requirements
- No hardcoding — use environment variables for API keys/config.
- Modular, readable code with type hints where possible.
- Comments only where genuinely helpful, not line-by-line noise.
- Realistic sample data.
- Demo-friendly: runs locally with `docker compose up`.
- Give setup and testing commands at each phase, not just at the end.

## Folder Structure
backend/app/{main.py, api/, agents/, tools/, rag/, ml/, db/, models/, services/, schemas/}, backend/tests/, backend/requirements.txt, backend/Dockerfile
frontend/src/{components/, pages/, services/}, frontend/package.json, frontend/Dockerfile
data/{sample_alerts.json, sample_logs.json, sample_metrics.csv, sample_commits.json, runbooks/, historical_incidents.csv}
docker-compose.yml
README.md
