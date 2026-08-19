import uuid

from tests.factories import make_alert, make_webhook

WEBHOOK_URL = "/api/v1/alerts/webhook"


async def test_list_incidents_filters_by_status(client):
    await client.post(WEBHOOK_URL, json=make_webhook(alerts=[make_alert(fingerprint="fp-1")]))
    created = (
        await client.post(WEBHOOK_URL, json=make_webhook(alerts=[make_alert(fingerprint="fp-2")]))
    ).json()["created"]
    await client.post(f"/api/v1/incidents/{created[0]}/resolve")

    open_incidents = (await client.get("/api/v1/incidents", params={"status": "open"})).json()
    resolved = (await client.get("/api/v1/incidents", params={"status": "resolved"})).json()

    assert len(open_incidents) == 1
    assert len(resolved) == 1
    assert resolved[0]["id"] == created[0]


async def test_get_unknown_incident_returns_404(client):
    resp = await client.get(f"/api/v1/incidents/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_manual_resolve_is_idempotent(client):
    created = (await client.post(WEBHOOK_URL, json=make_webhook())).json()["created"]

    first = (await client.post(f"/api/v1/incidents/{created[0]}/resolve")).json()
    second = (await client.post(f"/api/v1/incidents/{created[0]}/resolve")).json()

    assert first["status"] == "resolved"
    assert second["resolved_at"] == first["resolved_at"]
