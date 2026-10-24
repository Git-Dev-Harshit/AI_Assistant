import uuid

import pytest

REFUND_POLICY = {
    "title": "Refund Policy",
    "content": (
        "Customers can request a full refund within 30 days of purchase.\n\n"
        "Refunds are issued to the original payment method within 5 business days."
    ),
}


async def test_create_document_indexes_and_returns_id(client):
    response = await client.post("/documents", json=REFUND_POLICY)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "indexed"
    assert body["chunk_count"] == 1
    assert uuid.UUID(body["document_id"])
    assert response.headers["Location"] == f"/documents/{body['document_id']}"


async def test_get_document_returns_content(client):
    created = (await client.post("/documents", json=REFUND_POLICY)).json()

    response = await client.get(f"/documents/{created['document_id']}")

    assert response.status_code == 200
    assert response.json()["content"] == REFUND_POLICY["content"]


@pytest.mark.parametrize(
    "payload, field",
    [
        ({"title": "", "content": "body"}, "title"),
        ({"title": "   ", "content": "body"}, "title"),
        ({"title": "Title", "content": ""}, "content"),
        ({"title": "Title"}, "content"),
        ({"title": "x" * 201, "content": "body"}, "title"),
        ({"title": "Title", "content": "x" * 100_001}, "content"),
        ({"title": "Title", "content": "body", "unexpected": 1}, "unexpected"),
    ],
)
async def test_invalid_documents_are_rejected(client, payload, field):
    response = await client.post("/documents", json=payload)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert field in {detail["field"] for detail in error["details"]}


async def test_duplicate_content_returns_conflict_with_existing_id(client):
    first = (await client.post("/documents", json=REFUND_POLICY)).json()

    response = await client.post("/documents", json={**REFUND_POLICY, "title": "Copy"})

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "DOCUMENT_ALREADY_EXISTS"
    assert error["details"]["document_id"] == first["document_id"]


async def test_list_documents_is_paginated_newest_first(client):
    for i in range(3):
        await client.post("/documents", json={"title": f"Doc {i}", "content": f"Content number {i}"})

    page = (await client.get("/documents", params={"limit": 2, "offset": 0})).json()
    rest = (await client.get("/documents", params={"limit": 2, "offset": 2})).json()

    assert page["total"] == 3
    assert [d["title"] for d in page["items"]] == ["Doc 2", "Doc 1"]
    assert [d["title"] for d in rest["items"]] == ["Doc 0"]
    assert "content" not in page["items"][0]


async def test_list_documents_rejects_bad_pagination(client):
    response = await client.get("/documents", params={"limit": 0})

    assert response.status_code == 422


async def test_delete_document_removes_it(client):
    created = (await client.post("/documents", json=REFUND_POLICY)).json()

    deleted = await client.delete(f"/documents/{created['document_id']}")
    missing = await client.get(f"/documents/{created['document_id']}")

    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"
