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
