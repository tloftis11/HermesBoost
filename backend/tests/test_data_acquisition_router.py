async def test_create_session_runs_first_turn(client):
    resp = await client.post(
        "/api/v1/data-acquisition-sessions",
        json={"problem_description": "I want to predict which counties are at risk of an outbreak"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["session"]["problem_description"].startswith("I want to predict")
    assert "Fake reply" in body["reply_message"]
    assert body["staged_dataset_ids"] == []


async def test_send_message_grows_history(client):
    create_resp = await client.post(
        "/api/v1/data-acquisition-sessions", json={"problem_description": "measles risk by county"}
    )
    session_id = create_resp.json()["session"]["id"]

    resp = await client.post(
        f"/api/v1/data-acquisition-sessions/{session_id}/messages",
        json={"message": "Can you look at Texas specifically?"},
    )
    assert resp.status_code == 200
    assert "Fake reply" in resp.json()["reply_message"]

    detail = (await client.get(f"/api/v1/data-acquisition-sessions/{session_id}")).json()
    # 2 turns x (user + assistant) = 4 display messages
    assert len(detail["messages"]) == 4
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]


async def test_unknown_session_404s(client):
    import uuid

    resp = await client.get(f"/api/v1/data-acquisition-sessions/{uuid.uuid4()}")
    assert resp.status_code == 404
