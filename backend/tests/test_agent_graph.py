from app.agent.graph import run_agent_graph


def test_agent_graph_returns_agent_response(db_session) -> None:
    response = run_agent_graph(db_session, "help")

    assert response.handled is True
    assert response.intent is not None
    assert response.intent.name == "help"
