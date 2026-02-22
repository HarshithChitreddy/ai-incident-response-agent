from tests.factories import make_alert, make_webhook

WEBHOOK_URL = "/api/v1/alerts/webhook"


async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_firing_alert_creates_incident(client):
    resp = await client.post(WEBHOOK_URL, json=make_webhook())
    assert resp.status_code == 202
    body = resp.json()
    assert len(body["created"]) == 1
    assert body["updated"] == [] and body["resolved"] == [] and body["ignored"] == 0

    incident = (await client.get(f"/api/v1/incidents/{body['created'][0]}")).json()
    assert incident["alertname"] == "HighErrorRate"
    assert incident["service"] == "checkout-service"
    assert incident["severity"] == "critical"
    assert incident["status"] == "open"
    assert incident["fingerprint"] == "fp-checkout-5xx"
    assert len(incident["events"]) == 1
    assert incident["events"][0]["status"] == "firing"


async def test_duplicate_fingerprint_attaches_event_not_new_incident(client):
    first = (await client.post(WEBHOOK_URL, json=make_webhook())).json()
    second = (await client.post(WEBHOOK_URL, json=make_webhook())).json()

    assert second["created"] == []
    assert second["updated"] == first["created"]

    incidents = (await client.get("/api/v1/incidents")).json()
    assert len(incidents) == 1

    detail = (await client.get(f"/api/v1/incidents/{first['created'][0]}")).json()
    assert len(detail["events"]) == 2
