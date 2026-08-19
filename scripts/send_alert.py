#!/usr/bin/env python3
"""Synthetic alert simulator — the demo's stand-in for Prometheus Alertmanager.

Usage:
    python scripts/send_alert.py                       # fire high_error_rate
    python scripts/send_alert.py db_connection_pool    # fire another scenario
    python scripts/send_alert.py high_error_rate --resolve
    python scripts/send_alert.py --list
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

SCENARIOS_FILE = Path(__file__).resolve().parents[1] / "data" / "sample_alerts.json"
DEFAULT_URL = "http://localhost:8000/api/v1/alerts/webhook"


def as_resolved(payload: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        **payload,
        "status": "resolved",
        "alerts": [{**alert, "status": "resolved", "endsAt": now} for alert in payload["alerts"]],
    }


def main() -> int:
    scenarios = json.loads(SCENARIOS_FILE.read_text())

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario", nargs="?", default="high_error_rate", choices=sorted(scenarios))
    parser.add_argument("--resolve", action="store_true", help="send the resolved form of the alert")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--list", action="store_true", help="list scenarios and exit")
    args = parser.parse_args()

    if args.list:
        print("\n".join(sorted(scenarios)))
        return 0

    payload = scenarios[args.scenario]
    if args.resolve:
        payload = as_resolved(payload)

    try:
        resp = httpx.post(args.url, json=payload, timeout=10)
    except httpx.ConnectError:
        print(f"Could not reach {args.url} — is the backend running? (docker compose up)", file=sys.stderr)
        return 1

    print(f"{resp.status_code} {args.scenario}{' (resolved)' if args.resolve else ''}")
    print(json.dumps(resp.json(), indent=2))
    return 0 if resp.is_success else 1


if __name__ == "__main__":
    sys.exit(main())
