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
