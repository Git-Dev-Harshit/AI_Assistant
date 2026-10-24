async def test_health_reports_status_and_device(client):
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["compute"]["device"] == "cpu"
    assert response.headers["X-Request-ID"]


async def test_request_id_is_propagated_when_supplied(client):
    response = await client.get("/health", headers={"X-Request-ID": "trace-123"})

    assert response.headers["X-Request-ID"] == "trace-123"


async def test_unknown_route_uses_error_envelope(client):
    response = await client.get("/does-not-exist")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["request_id"] == response.headers["X-Request-ID"]


async def test_oversized_body_is_rejected_with_413(client, settings):
    payload = "x" * (settings.max_request_bytes + 1)

    response = await client.post("/health", content=payload, headers={"Content-Type": "application/json"})

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


async def test_ready_reports_database_status(client):
    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok", "redis": "disabled"}
