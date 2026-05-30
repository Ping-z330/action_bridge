def test_list_meetings_includes_history_counts(client) -> None:
    create_response = client.post(
        "/api/meetings",
        json={
            "title": "History review",
            "transcript": "\n".join(
                [
                    "Discussed execution tracking.",
                    "Decision: use history page for meeting recall",
                    "Action: backend expose meeting action counts",
                    "Next step: frontend render history cards",
                ]
            ),
        },
    )
    meeting = create_response.json()

    response = client.get("/api/meetings")

    assert response.status_code == 200
    meetings = response.json()
    assert meetings[0]["id"] == meeting["id"]
    assert meetings[0]["action_count"] == 2
    assert meetings[0]["pending_count"] == 2
    assert meetings[0]["completed_count"] == 0
    assert meetings[0]["closure_status"] == "open"
