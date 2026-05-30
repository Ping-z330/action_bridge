def test_list_action_items_returns_meeting_context(client) -> None:
    create_response = client.post(
        "/api/meetings",
        json={
            "title": "Task review",
            "transcript": "\n".join(
                [
                    "Discussed launch readiness.",
                    "Decision: ship after QA signoff",
                    "Action: frontend team update landing page",
                    "Next step: product manager confirm launch notice",
                ]
            ),
        },
    )
    meeting = create_response.json()

    response = client.get("/api/action-items")

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert items[0]["meeting_id"] == meeting["id"]
    assert items[0]["meeting_title"] == "Task review"
    assert items[0]["status"] == "pending"
    assert "due_status" in items[0]
    assert "due_status_label" in items[0]


def test_patch_action_item_is_reflected_in_task_list_and_history_counts(client) -> None:
    create_response = client.post(
        "/api/meetings",
        json={
            "title": "Status persistence review",
            "transcript": "\n".join(
                [
                    "Discussed task persistence.",
                    "Decision: status changes must persist",
                    "Action: backend persist completed status",
                ]
            ),
        },
    )
    meeting = create_response.json()
    action_item = meeting["action_items"][0]

    patch_response = client.patch(
        f"/api/action-items/{action_item['id']}",
        json={
            "owner_name": action_item["owner_name"],
            "deadline": action_item["deadline"],
            "status": "completed",
        },
    )

    assert patch_response.status_code == 200

    task_response = client.get("/api/action-items")
    task = task_response.json()[0]
    assert task["status"] == "completed"
    assert task["due_status"] == "completed"

    history_response = client.get("/api/meetings")
    history = history_response.json()[0]
    assert history["completed_count"] == 1
    assert history["pending_count"] == 0
    assert history["due_today_count"] == 0
    assert history["overdue_count"] == 0
    assert history["closure_status"] == "closed"
