"""Builders for Alertmanager-shaped payloads used across test modules."""

from datetime import datetime, timezone
from typing import Any


def make_alert(
    status: str = "firing",
    alertname: str = "HighErrorRate",
    service: str = "checkout-service",
    severity: str = "critical",
    fingerprint: str = "fp-checkout-5xx",
    summary: str | None = None,
    ends_at: str = "0001-01-01T00:00:00Z",
) -> dict[str, Any]:
    return {
        "status": status,
        "labels": {
            "alertname": alertname,
            "service": service,
            "severity": severity,
        },
        "annotations": {
            "summary": summary or f"{alertname} on {service}",
            "description": f"{alertname} fired for {service}",
        },
        "startsAt": datetime.now(timezone.utc).isoformat(),
        "endsAt": ends_at,
        "generatorURL": "http://prometheus:9090/graph",
        "fingerprint": fingerprint,
    }


def make_webhook(alerts: list[dict[str, Any]] | None = None, status: str = "firing") -> dict[str, Any]:
    alerts = alerts if alerts is not None else [make_alert()]
    return {
        "version": "4",
        "groupKey": '{}:{alertname="HighErrorRate"}',
        "status": status,
        "receiver": "incident-response-agent",
        "groupLabels": {"alertname": alerts[0]["labels"].get("alertname", "")},
        "commonLabels": alerts[0]["labels"],
        "commonAnnotations": alerts[0]["annotations"],
        "externalURL": "http://alertmanager:9093",
        "alerts": alerts,
    }
